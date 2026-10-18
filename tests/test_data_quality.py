import csv
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from prepare_data import read_pairs, iter_clusters
from validate_project import validate


class DataQualityTests(unittest.TestCase):
    def test_instrument_header_and_zero_charge_sample(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'charge_response.txt'
            path.write_text('1D 2 -0,5 1,5\t[nbin xmin xmax]\n"X"\t"Function_0"\n0,0\t1,25\n1,0\t2,50\n')
            self.assertEqual(read_pairs(path), [(3, 0., 1.25), (4, 1., 2.5)])
            path.write_text('0.0\t1.25\n1.0\t2.5\n')
            self.assertEqual(read_pairs(path)[0], (1, 0., 1.25))

    def test_incomplete_and_nonfinite_exports_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'invalid_response.txt'
            for text in ['1D 2 0 2\t[nbin xmin xmax]\n"X"\t"Function_0"\n0\t1\n', '0\tnan\n']:
                path.write_text(text)
                with self.assertRaises(ValueError):
                    read_pairs(path)

    def test_cluster_boundaries_and_all_channel_signals_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cluster_signals.txt'
            path.write_text('Je Cluster eine Zeile\n10\t20\n5\n')
            clusters = list(iter_clusters(path))
            self.assertEqual(clusters, [(2, [10., 20.]), (3, [5.])])
            self.assertEqual(sum(sum(values) for _, values in clusters) / len(clusters), 17.5)
            self.assertNotEqual(17.5, (10 + 5) / 2)

    def test_real_voltage_scan_has_correct_pairing(self):
        with (ROOT / 'data/derived/source_voltage_response.csv').open() as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual([int(row['bias_voltage_v']) for row in rows], list(range(0, 201, 10)))
        self.assertEqual(int(rows[0]['cluster_count']), 200)
        self.assertAlmostEqual(float(rows[0]['mean_cluster_sum_adc']), 12.119491875000001)
        self.assertAlmostEqual(float(rows[-1]['mean_cluster_sum_adc']), 97.02056490036149)

    def test_corrupted_published_summary_is_detected(self):
        import validate_project
        original_hash=validate_project.sha256
        target=ROOT/'data/derived/source_voltage_response.csv'
        with patch.object(validate_project,'sha256',side_effect=lambda p:'0'*64 if p==target else original_hash(p)):
            errors,_=validate()
        self.assertTrue(any('Derived checksum mismatch' in error for error in errors))

    def test_published_summaries_validate_without_source_measurements(self):
        self.assertFalse((ROOT/'data/source').exists())
        self.assertEqual(validate()[0],[])

    def test_local_reconstruction_requires_actual_source_files(self):
        errors,_=validate(recompute=True,require_sources=True)
        self.assertTrue(any('Local source files required' in error for error in errors))

    def test_nonfinite_summary_is_rejected_even_with_matching_checksum(self):
        import shutil,hashlib
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            shutil.copytree(ROOT/'metadata',root/'metadata')
            shutil.copytree(ROOT/'data',root/'data')
            path=root/'data/derived/source_voltage_response.csv'
            with path.open(newline='') as handle:
                reader=csv.DictReader(handle);fieldnames=reader.fieldnames;rows=list(reader)
            rows[0]['mean_cluster_sum_adc']='nan'
            with path.open('w',newline='') as handle:
                writer=csv.DictWriter(handle,fieldnames=fieldnames);writer.writeheader();writer.writerows(rows)
            manifest_path=root/'metadata/derived_manifest.json';manifest=json.loads(manifest_path.read_text())
            for item in manifest:
                if item['path']=='data/derived/source_voltage_response.csv':
                    item['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest))
            errors,_=validate(root)
            self.assertTrue(any('Nonfinite value' in error for error in errors))

    def test_repository_rejects_accidental_source_or_point_level_files(self):
        import check_repository
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'data/source').mkdir(parents=True)
            (root/'data/source/measurement.txt').write_text('fixture')
            (root/'data/derived').mkdir();(root/'data/derived/calibration_measurements.csv').write_text('fixture')
            errors,_=check_repository.check(root)
            self.assertTrue(any('Source measurements are excluded' in error for error in errors))
            self.assertTrue(any('point-level result table' in error for error in errors))


if __name__ == '__main__':
    unittest.main()
