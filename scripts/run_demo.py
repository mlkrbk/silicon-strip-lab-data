#!/usr/bin/env python3
"""Run synthetic generation, integrity validation, calibration and QC reporting."""
import argparse
from pathlib import Path

from generate_synthetic import ROOT, generate
from scientific_qc import Thresholds, analyze, write_reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'demo_output')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--max-noise-adc', type=float, default=3.)
    parser.add_argument('--max-residual-rms-adc', type=float, default=2.)
    parser.add_argument('--min-r-squared', type=float, default=.99)
    args = parser.parse_args()
    try:
        thresholds = Thresholds(args.max_noise_adc, args.max_residual_rms_adc, args.min_r_squared)
        directory = generate(args.output, seed=args.seed)
        report = analyze(directory, thresholds)
        write_reports(directory, report)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, f'ERROR: {error}\n')
    print('SIMULATED DATA: input validation passed.')
    print('Scientific QC:', report['status'], report['channel_counts'])
    print('Reports:', directory / 'qc_report.json', 'and', directory / 'qc_report.md')
    return int(report['status'] == 'failure')


if __name__ == '__main__':
    raise SystemExit(main())
