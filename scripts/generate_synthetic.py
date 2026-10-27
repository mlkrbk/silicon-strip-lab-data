#!/usr/bin/env python3
"""Generate a deterministic, explicitly simulated detector demonstration."""
import argparse
import csv
import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO_MARKER = 'silicon-strip-synthetic-demo-v1'
INPUT_NAMES = ('pedestal.csv', 'calibration.csv')
OUTPUT_NAMES = {*INPUT_NAMES, 'manifest.json', 'qc_report.json', 'qc_report.md'}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare_destination(destination):
    """Permit repeat runs only in our own demo directory, never mixed data."""
    destination = Path(destination)
    if destination.is_symlink():
        raise ValueError('Demo destination must not use symlinks')
    # macOS temporary paths legitimately traverse the system /var symlink.
    destination = destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        marker = destination / 'manifest.json'
        if not marker.is_file():
            raise ValueError('Refusing to overwrite a directory without a demo manifest')
        manifest = json.loads(marker.read_text(encoding='utf-8'))
        if (not isinstance(manifest, dict) or manifest.get('demo') != DEMO_MARKER
                or manifest.get('synthetic') is not True):
            raise ValueError('Refusing to overwrite a directory not marked synthetic')
        if any(p.name not in OUTPUT_NAMES or not p.is_file() or p.is_symlink()
               for p in destination.iterdir()):
            raise ValueError('Refusing to overwrite a directory containing unrelated files')
    destination.mkdir(parents=True, exist_ok=True)
    return destination


def generate(destination, seed=42, channels=32, events=256):
    if type(channels) is not int or channels < 2 or type(events) is not int or events < 3:
        raise ValueError('Need at least two channels and three pedestal events')
    if type(seed) is not int:
        raise ValueError('Seed must be an integer')
    destination = prepare_destination(destination)
    rng = random.Random(seed)
    charges = [0., 2., 4., 6., 8., 10.]
    repeats = 4
    with (destination / 'pedestal.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(['channel', 'event', 'adc'])
        for channel in range(channels):
            sigma = 6.0 if channel == channels - 1 else 1.2
            for event in range(events):
                writer.writerow([channel, event, f'{rng.gauss(100 + .2 * channel, sigma):.8f}'])
    with (destination / 'calibration.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(['channel', 'charge_fc', 'repeat', 'adc'])
        for channel in range(channels):
            for charge in charges:
                for repeat in range(repeats):
                    adc = 100 + .2 * channel + (7 + .03 * channel) * charge + rng.gauss(0, .65)
                    writer.writerow([channel, charge, repeat, f'{adc:.8f}'])
    manifest = {
        'demo': DEMO_MARKER, 'synthetic': True, 'schema_version': 1,
        'description': 'SIMULATED measurements; not laboratory observations or validated instrument exports.',
        'seed': seed, 'channels': channels, 'pedestal_events_per_channel': events,
        'charge_grid_fc': charges, 'calibration_repeats': repeats,
        'model': {'pedestal_mean_adc': '100 + 0.2 * channel',
                  'normal_noise_sigma_adc': 1.2, 'anomalous_channel': channels - 1,
                  'anomalous_noise_sigma_adc': 6.0,
                  'gain_adc_per_fc': '7 + 0.03 * channel', 'calibration_sigma_adc': .65},
        'inputs': {name: {'sha256': sha256(destination / name)} for name in INPUT_NAMES},
    }
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'demo_output')
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    try:
        print('Synthetic data:', generate(args.output, args.seed))
    except (ValueError, OSError) as error:
        parser.exit(2, f'ERROR: {error}\n')


if __name__ == '__main__':
    main()
