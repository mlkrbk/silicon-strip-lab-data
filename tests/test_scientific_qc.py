import csv
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from fit_calibration import fit_linear
from generate_synthetic import generate, sha256
from scientific_qc import Thresholds, analyze, write_reports


class SyntheticQCTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.data = generate(self.base / 'demo')

    def change_table(self, name, change):
        """Re-sign edited fixtures so semantic checks run after integrity checks."""
        path = self.data / name
        with path.open(newline='', encoding='utf-8') as handle:
            reader = csv.DictReader(handle)
            fields, rows = reader.fieldnames, list(reader)
        change(rows)
        with path.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        manifest = json.loads((self.data / 'manifest.json').read_text())
        manifest['inputs'][name]['sha256'] = sha256(path)
        (self.data / 'manifest.json').write_text(json.dumps(manifest))

    def test_reproducible_generation_and_seed_effect(self):
        same = generate(self.base / 'same')
        other = generate(self.base / 'other', seed=43)
        for name in ('pedestal.csv', 'calibration.csv', 'manifest.json'):
            self.assertEqual((self.data / name).read_bytes(), (same / name).read_bytes())
        self.assertNotEqual((self.data / 'pedestal.csv').read_bytes(), (other / 'pedestal.csv').read_bytes())

    def test_known_fit_and_analytic_standard_errors(self):
        # Orthogonal residual vector (1, -2, 1) gives gain=2, intercept=1,
        # SSE=6, dof=1, Sxx=2; hence SE(gain)=sqrt(3).
        fit = fit_linear([(0., 2.), (1., 1.), (2., 6.)])
        self.assertAlmostEqual(fit['gain_adc_per_fc'], 2.)
        self.assertAlmostEqual(fit['intercept_adc'], 1.)
        self.assertAlmostEqual(fit['gain_standard_error_adc_per_fc'], math.sqrt(3))
        self.assertAlmostEqual(fit['intercept_standard_error_adc'], math.sqrt(5))
        self.assertAlmostEqual(fit['residual_rms_adc'], math.sqrt(2))
        self.assertAlmostEqual(fit['r_squared'], 4 / 7)

    def test_degenerate_and_nonfinite_fits_rejected(self):
        for points in ([(0, 1), (1, 2)], [(1, 1), (1, 2), (1, 3)],
                       [(0, 1), (1, float('nan')), (2, 3)]):
            with self.subTest(points=points), self.assertRaises(ValueError):
                fit_linear(points)

    def test_expected_anomaly_and_simulated_gain_recovery(self):
        report = analyze(self.data)
        self.assertEqual(report['input_validation'], 'pass')
        self.assertEqual(report['channel_counts'], {'pass': 31, 'warning': 1, 'failure': 0})
        self.assertEqual(report['channels'][31]['checks'][0]['status'], 'warning')
        for row in report['channels']:
            self.assertAlmostEqual(row['calibration']['gain_adc_per_fc'], 7 + .03 * row['channel'], delta=.15)
            self.assertGreater(row['calibration']['gain_standard_error_adc_per_fc'], 0)
        write_reports(self.data, report)
        self.assertEqual(json.loads((self.data / 'qc_report.json').read_text()), report)
        self.assertIn('Channel 31: warning', (self.data / 'qc_report.md').read_text())

    def test_configurable_thresholds_and_invalid_thresholds(self):
        self.assertEqual(analyze(self.data, Thresholds(max_noise_adc=10))['status'], 'pass')
        for values in ({'max_noise_adc': 0}, {'min_r_squared': 1.1},
                       {'max_residual_rms_adc': float('nan')}, {'max_noise_adc': float('inf')}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                Thresholds(**values)

    def test_checksum_mismatch_rejected(self):
        with (self.data / 'pedestal.csv').open('a') as handle:
            handle.write('0,999,100\n')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            analyze(self.data)

    def test_semantic_invalid_data_rejected_with_matching_checksum(self):
        for value in ('nan', 'inf', '-inf', 'bad'):
            with self.subTest(value=value):
                self.change_table('pedestal.csv', lambda rows: rows[0].update(adc=value))
                with self.assertRaises(ValueError):
                    analyze(self.data)

    def test_missing_and_duplicate_measurements_rejected(self):
        self.change_table('calibration.csv', lambda rows: rows.pop())
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            analyze(self.data)
        generate(self.data)
        self.change_table('pedestal.csv', lambda rows: rows.append(dict(rows[0])))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            analyze(self.data)

    def test_invalid_channel_and_charge_rejected(self):
        self.change_table('pedestal.csv', lambda rows: rows[0].update(channel='32'))
        with self.assertRaisesRegex(ValueError, 'Invalid'):
            analyze(self.data)
        generate(self.data)
        self.change_table('calibration.csv', lambda rows: rows[0].update(charge_fc='-1'))
        with self.assertRaisesRegex(ValueError, 'Invalid'):
            analyze(self.data)

    def test_negative_gain_failure_and_nonlinearity_warning(self):
        def negative(rows):
            for row in rows:
                if row['channel'] == '0':
                    row['adc'] = str(100 - 5 * float(row['charge_fc']))
        self.change_table('calibration.csv', negative)
        self.assertEqual(analyze(self.data)['channels'][0]['status'], 'failure')
        generate(self.data)
        def nonlinear(rows):
            for row in rows:
                if row['channel'] == '0':
                    row['adc'] = str(100 + float(row['charge_fc']) ** 2)
        self.change_table('calibration.csv', nonlinear)
        checks = {check['rule']: check['status'] for check in analyze(self.data)['channels'][0]['checks']}
        self.assertEqual(checks['calibration_residual'], 'warning')
        self.assertEqual(checks['linear_response'], 'warning')

    def test_synthetic_label_required_and_existing_files_preserved(self):
        marker = self.data / 'manifest.json'
        manifest = json.loads(marker.read_text())
        manifest['synthetic'] = False
        marker.write_text(json.dumps(manifest))
        before = {p.name: p.read_bytes() for p in self.data.iterdir()}
        for operation in (analyze, generate):
            with self.assertRaises(ValueError):
                operation(self.data)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.data.iterdir()})
        real = self.base / 'real'
        real.mkdir()
        (real / 'measurement.csv').write_text('keep this')
        with self.assertRaises(ValueError):
            generate(real)
        self.assertEqual((real / 'measurement.csv').read_text(), 'keep this')

    def test_unrelated_file_and_symlink_not_overwritten(self):
        unrelated = self.data / 'notes.md'
        unrelated.write_text('preserve')
        with self.assertRaises(ValueError):
            generate(self.data)
        target = self.base / 'target'
        target.write_text('preserve')
        link = self.data / 'qc_report.md'
        link.symlink_to(target)
        with self.assertRaises(ValueError):
            write_reports(self.data, analyze(self.data))
        self.assertEqual(target.read_text(), 'preserve')

    def test_invalid_manifest_and_csv_schema_rejected(self):
        marker = self.data / 'manifest.json'
        original = marker.read_text()
        marker.write_text('[]')
        for operation in (analyze, generate):
            with self.assertRaises(ValueError):
                operation(self.data)
        marker.write_text(original)
        path = self.data / 'pedestal.csv'
        path.write_text(path.read_text().replace('channel,event,adc', 'channel,event,voltage', 1))
        manifest = json.loads(original)
        manifest['inputs']['pedestal.csv']['sha256'] = sha256(path)
        marker.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'schema'):
            analyze(self.data)

    def test_cli_runs_outside_repository_and_repeats(self):
        output = self.base / 'cli'
        command = [sys.executable, str(ROOT / 'scripts/run_demo.py'), '--output', str(output)]
        for _ in range(2):
            result = subprocess.run(command, cwd=self.base, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((output / 'qc_report.md').is_file())
        bad = subprocess.run(command + ['--max-noise-adc', '-1'], capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)

    def test_qc_cli_failure_has_nonzero_exit_and_report(self):
        def negative(rows):
            for row in rows:
                row['adc'] = str(100 - 5 * float(row['charge_fc']))
        self.change_table('calibration.csv', negative)
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/scientific_qc.py'),
                                 '--input', str(self.data)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads((self.data / 'qc_report.json').read_text())['status'], 'failure')


if __name__ == '__main__':
    unittest.main()
