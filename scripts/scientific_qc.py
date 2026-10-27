#!/usr/bin/env python3
"""Validate synthetic inputs and evaluate illustrative scientific QC rules."""
import argparse
import csv
import json
import math
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path

from fit_calibration import fit_linear
from generate_synthetic import DEMO_MARKER, INPUT_NAMES, ROOT, sha256


@dataclass(frozen=True)
class Thresholds:
    max_noise_adc: float = 3.0
    max_residual_rms_adc: float = 2.0
    min_r_squared: float = .99

    def __post_init__(self):
        if (not all(math.isfinite(v) for v in asdict(self).values())
                or self.max_noise_adc <= 0 or self.max_residual_rms_adc <= 0
                or not 0 <= self.min_r_squared <= 1):
            raise ValueError('Thresholds must be finite, with positive maxima and R squared in [0, 1]')


def _integer(value, label, minimum):
    if type(value) is not int or value < minimum:
        raise ValueError(f'{label} must be an integer >= {minimum}')
    return value


def _rows(path, columns):
    with path.open(newline='', encoding='utf-8') as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != columns:
            raise ValueError(f'Unexpected schema: {path.name}')
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f'Malformed CSV row: {path.name}')
            try:
                parsed = {key: (int(value) if key in {'channel', 'event', 'repeat'} else float(value))
                          for key, value in row.items()}
            except (ValueError, TypeError) as error:
                raise ValueError(f'Invalid numeric value: {path.name}') from error
            if not all(math.isfinite(v) for v in parsed.values()):
                raise ValueError(f'Nonfinite value: {path.name}')
            yield parsed


def analyze(directory, thresholds=None):
    thresholds = thresholds or Thresholds()
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if (not isinstance(manifest, dict) or manifest.get('synthetic') is not True or manifest.get('demo') != DEMO_MARKER
            or manifest.get('schema_version') != 1):
        raise ValueError('Only explicitly marked synthetic demo inputs are accepted')
    if type(manifest.get('seed')) is not int:
        raise ValueError('Manifest seed must be an integer')
    channels = _integer(manifest.get('channels'), 'channels', 2)
    events = _integer(manifest.get('pedestal_events_per_channel'), 'events', 3)
    repeats = _integer(manifest.get('calibration_repeats'), 'repeats', 1)
    grid = manifest.get('charge_grid_fc')
    if (not isinstance(grid, list) or len(grid) < 3
            or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in grid)
            or len(set(grid)) != len(grid) or 0 not in grid):
        raise ValueError('Charge grid must include zero and at least three distinct finite nonnegative values')
    if not isinstance(manifest.get('inputs'), dict) or set(manifest['inputs']) != set(INPUT_NAMES):
        raise ValueError('Manifest must identify exactly the two synthetic input tables')
    for name in INPUT_NAMES:
        spec = manifest['inputs'][name]
        if not isinstance(spec, dict) or sha256(directory / name) != spec.get('sha256'):
            raise ValueError(f'Input checksum mismatch: {name}')
    pedestal = {ch: {} for ch in range(channels)}
    calibration = {ch: {} for ch in range(channels)}
    for row in _rows(directory / 'pedestal.csv', ['channel', 'event', 'adc']):
        ch, event = row['channel'], row['event']
        if ch not in pedestal or not 0 <= event < events or event in pedestal[ch]:
            raise ValueError('Invalid or duplicate pedestal channel/event')
        pedestal[ch][event] = row['adc']
    for row in _rows(directory / 'calibration.csv', ['channel', 'charge_fc', 'repeat', 'adc']):
        ch, charge, repeat = row['channel'], row['charge_fc'], row['repeat']
        key = charge, repeat
        if (ch not in calibration or charge not in grid or not 0 <= repeat < repeats
                or key in calibration[ch]):
            raise ValueError('Invalid or duplicate calibration channel/charge/repeat')
        calibration[ch][key] = row['adc']
    results = []
    for ch in range(channels):
        if len(pedestal[ch]) != events or len(calibration[ch]) != len(grid) * repeats:
            raise ValueError(f'Incomplete measurements for channel {ch}')
        noise = statistics.stdev(pedestal[ch].values())
        fit = fit_linear([(charge, adc) for (charge, _), adc in sorted(calibration[ch].items())])
        checks = [
            {'rule': 'pedestal_noise', 'status': 'warning' if noise > thresholds.max_noise_adc else 'pass',
             'reason': f'Sample noise {noise:.3f} ADC; warning above {thresholds.max_noise_adc:g} ADC.'},
            {'rule': 'calibration_residual',
             'status': 'warning' if fit['residual_rms_adc'] > thresholds.max_residual_rms_adc else 'pass',
             'reason': f"Residual RMS {fit['residual_rms_adc']:.3f} ADC; warning above {thresholds.max_residual_rms_adc:g} ADC."},
            {'rule': 'positive_gain', 'status': 'pass' if fit['gain_adc_per_fc'] > 0 else 'failure',
             'reason': 'Gain must be positive for this simulated positive-response model.'},
            {'rule': 'linear_response',
             'status': 'pass' if fit['r_squared'] is not None and fit['r_squared'] >= thresholds.min_r_squared else 'warning',
             'reason': f"R squared {fit['r_squared']}; warning below {thresholds.min_r_squared:g} or if undefined."},
        ]
        status = max((check['status'] for check in checks), key={'pass': 0, 'warning': 1, 'failure': 2}.get)
        results.append({'channel': ch, 'status': status, 'pedestal_mean_adc': statistics.mean(pedestal[ch].values()),
                        'pedestal_noise_adc': noise, 'pedestal_event_count': events, 'calibration': fit, 'checks': checks})
    counts = {status: sum(r['status'] == status for r in results) for status in ('pass', 'warning', 'failure')}
    return {'synthetic': True, 'demo': DEMO_MARKER, 'schema_version': 1,
            'input_validation': 'pass', 'manifest_sha256': sha256(directory / 'manifest.json'),
            'inputs': manifest['inputs'], 'seed': manifest['seed'], 'thresholds': asdict(thresholds),
            'status': 'failure' if counts['failure'] else 'warning' if counts['warning'] else 'pass',
            'channel_counts': counts, 'channels': results}


def write_reports(directory, report):
    directory = Path(directory)
    for name in ('qc_report.json', 'qc_report.md'):
        if (directory / name).is_symlink():
            raise ValueError('Report destination must not be a symlink')
    (directory / 'qc_report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    lines = ['# Synthetic detector QC report', '',
             '**SIMULATED DATA — not laboratory measurements.**', '',
             f"Input validation: {report['input_validation']}. Scientific QC: **{report['status']}**.",
             f"Channel counts: {report['channel_counts']}. Seed: {report['seed']}.", '',
             'Thresholds: `' + json.dumps(report['thresholds'], sort_keys=True) + '`.', '',
             'ADC = intercept + gain × injected charge (fC). Errors are fit standard errors (1 sigma),',
             'conditional on exact charges and independent equal-variance ADC errors. Systematics are excluded.',
             'This fit does not validate inverse ADC-to-energy conversion.', '',
             '| Channel | Status | Noise (ADC) | Gain ± SE (ADC/fC) | Residual RMS (ADC) |',
             '| --- | --- | --- | --- | --- |']
    for row in report['channels']:
        fit = row['calibration']
        lines.append(f"| {row['channel']} | {row['status']} | {row['pedestal_noise_adc']:.3f} | "
                     f"{fit['gain_adc_per_fc']:.4f} ± {fit['gain_standard_error_adc_per_fc']:.4f} | {fit['residual_rms_adc']:.3f} |")
    lines += ['', '## Flagged checks', '']
    flagged = [f"- Channel {row['channel']}: {check['status']} — {check['rule']}: {check['reason']}"
               for row in report['channels'] for check in row['checks'] if check['status'] != 'pass']
    lines += flagged or ['No measurements flagged.']
    lines += ['', '## Input provenance', '', f"Manifest SHA-256: `{report['manifest_sha256']}`.", '']
    lines += [f"- `{name}`: `{spec['sha256']}`" for name, spec in sorted(report['inputs'].items())]
    (directory / 'qc_report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'demo_output')
    parser.add_argument('--max-noise-adc', type=float, default=3.)
    parser.add_argument('--max-residual-rms-adc', type=float, default=2.)
    parser.add_argument('--min-r-squared', type=float, default=.99)
    args = parser.parse_args()
    try:
        report = analyze(args.input, Thresholds(args.max_noise_adc, args.max_residual_rms_adc, args.min_r_squared))
        write_reports(args.input, report)
        print('Synthetic QC:', report['status'], report['channel_counts'])
        return int(report['status'] == 'failure')
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, f'ERROR: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
