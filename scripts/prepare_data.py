#!/usr/bin/env python3
"""Create traceable analysis tables from the selected, formally named source copies."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_pairs(path):
    """Read a headerless curve or a two-line Alibava histogram export."""
    lines = path.read_text().splitlines()
    headered = bool(lines and lines[0].startswith('1D '))
    start = 2 if headered else 0
    if headered and not lines[1].startswith('"X"\t'):
        raise ValueError(f'Unrecognized column header in {path.name}')
    rows = []
    for line_number, text in enumerate(lines[start:], start + 1):
        values = [float(value.replace(',', '.')) for value in text.split('\t')]
        if len(values) != 2 or not all(math.isfinite(x) for x in values):
            raise ValueError(f'Invalid numeric pair in {path.name}:{line_number}')
        rows.append((line_number, *values))
    if not rows or any(b[1] <= a[1] for a, b in zip(rows, rows[1:])):
        raise ValueError(f'Empty or non-increasing curve in {path.name}')
    if headered and len(rows) != int(lines[0].split()[1]):
        raise ValueError(f'Histogram bin count mismatch in {path.name}')
    return rows


def read_matrix(path, separator, shape):
    rows = [[float(value) for value in line.split(separator)]
            for line in path.read_text().splitlines()]
    if len(rows) != shape[0] or any(len(row) != shape[1] for row in rows):
        raise ValueError(f'Matrix shape mismatch in {path.name}; expected {shape}')
    if not all(math.isfinite(value) for row in rows for value in row):
        raise ValueError(f'Nonfinite matrix value in {path.name}')
    return rows


def iter_clusters(path):
    """Each data line is one cluster; fields are contributing channel ADC signals."""
    with path.open() as handle:
        if not handle.readline().startswith('Je Cluster'):
            raise ValueError(f'Unknown cluster header in {path.name}')
        for line_number, text in enumerate(handle, 2):
            values = [float(value) for value in text.split()]
            if not values or not all(math.isfinite(value) for value in values):
                raise ValueError(f'Invalid cluster in {path.name}:{line_number}')
            yield line_number, values


def read_counts(path):
    with path.open() as handle:
        if not handle.readline().startswith('#'):
            raise ValueError(f'Missing count header in {path.name}')
        values = [float(line.strip()) for line in handle]
    if len(values) != 128 or any(not math.isfinite(v) or v < 0 or v != int(v) for v in values):
        raise ValueError(f'Expected 128 nonnegative integer counts in {path.name}')
    return [int(v) for v in values]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_tables(root=ROOT):
    """Return deterministic tables without modifying input files or metadata."""
    root = Path(root)
    manifest = json.loads((root / 'metadata/source_manifest.json').read_text())
    available = [item for item in manifest['inputs'] if item['status'] == 'available']
    by_kind = {}
    for item in available:
        if sha256(root / item['path']) != item['sha256']:
            raise ValueError(f'Source integrity failure: {item["id"]}')
        by_kind.setdefault(item['kind'], []).append(item)
    tables = {}
    calibration = []
    for item in by_kind['calibration']:
        for number, charge, signal in read_pairs(root / item['path']):
            calibration.append({
                'measurement_id': f'{item["id"]}-{number:04d}',
                'source_id': item['id'], 'source_line': number,
                'channel_label': item['channel'], 'injected_charge_electrons': charge,
                'equivalent_energy_kev': charge * 3.6 / 1000,
                'signal_adc': signal, 'included_in_historical_fit': int(charge != 0),
            })
    tables['calibration_measurements.csv'] = calibration
    curves = {}
    for row in calibration:
        curves.setdefault(row['injected_charge_electrons'], []).append(row['signal_adc'])
    tables['calibration_mean_response.csv'] = [
        {'injected_charge_electrons': charge, 'equivalent_energy_kev': charge * 3.6 / 1000,
         'mean_signal_adc': sum(signals) / len(signals), 'channel_count': len(signals),
         'included_in_historical_fit': int(charge != 0)}
        for charge, signals in sorted(curves.items())
    ]
    if any(row['channel_count'] != 5 for row in tables['calibration_mean_response.csv']):
        raise ValueError('The five selected calibration curves have different charge grids')
    item = by_kind['pedestal_matrix'][0]
    samples = read_matrix(root / item['path'], ';', (128, 100))
    pedestal = [sum(row) / len(row) for row in samples]
    common = [sum(samples[i][k] - pedestal[i] for i in range(128)) / 128 for k in range(100)]
    tables['pedestal_channel_statistics.csv'] = []
    for i, row in enumerate(samples):
        raw_noise = math.sqrt(sum((x - pedestal[i]) ** 2 for x in row) / 99)
        corrected = math.sqrt(sum((row[k] - pedestal[i] - common[k]) ** 2 for k in range(100)) / 99)
        tables['pedestal_channel_statistics.csv'].append({
            'channel_index': i, 'event_count': 100, 'pedestal_adc': pedestal[i],
            'uncorrected_sample_noise_adc': raw_noise,
            'common_mode_corrected_sample_noise_adc': corrected,
            'source_id': item['id'], 'source_line': i + 1,
        })
    tables['recomputed_common_mode.csv'] = [
        {'event_index': k, 'common_mode_adc': value, 'source_id': item['id'], 'source_column': k + 1}
        for k, value in enumerate(common)
    ]
    for kind, name in [('common_mode_export', 'historical_common_mode.csv'),
                       ('noise_export', 'historical_channel_noise.csv'),
                       ('laser_delay', 'laser_synchronization_scan.csv')]:
        item = by_kind[kind][0]
        coordinate = 'delay_ns' if kind == 'laser_delay' else 'export_bin_center'
        quantity = 'signal_adc' if kind == 'laser_delay' else 'value_adc'
        tables[name] = [{coordinate: x, quantity: y, 'source_id': item['id'], 'source_line': number}
                        for number, x, y in read_pairs(root / item['path'])]
    item = by_kind['laser_matrix'][0]
    laser = read_matrix(root / item['path'], '\t', (35, 128))
    tables['laser_position_scan.csv'] = [
        {'position_index': i, 'relative_offset_mm': round(i * .01, 2),
         'channel_index': j, 'signal_adc': value, 'source_id': item['id'],
         'source_line': i + 1, 'source_column': j + 1}
        for i, row in enumerate(laser) for j, value in enumerate(row)
    ]
    source_voltage = []
    for item in sorted(by_kind['source_voltage'], key=lambda item: item['bias_voltage_v']):
        first_sum = total_sum = channel_sum = count = 0
        for _, values in iter_clusters(root / item['path']):
            count += 1
            first_sum += values[0]
            total_sum += sum(values)
            channel_sum += len(values)
        if not count:
            raise ValueError('Empty source-voltage export')
        source_voltage.append({
            'bias_voltage_v': item['bias_voltage_v'], 'cluster_count': count,
            'contributing_channel_count': channel_sum,
            'historical_mean_first_channel_adc': first_sum / count,
            'mean_cluster_sum_adc': total_sum / count, 'source_id': item['id'],
        })
    if [r['bias_voltage_v'] for r in source_voltage] != list(range(0, 201, 10)):
        raise ValueError('Incomplete source-voltage series')
    for field in ['historical_mean_first_channel_adc', 'mean_cluster_sum_adc']:
        low = min(row[field] for row in source_voltage)
        high = max(row[field] for row in source_voltage)
        if high == low:
            raise ValueError('Constant source response cannot be normalized')
        for row in source_voltage:
            row['normalized_' + field] = (row[field] - low) / (high - low)
    tables['source_voltage_response.csv'] = source_voltage
    for kind, name, index in [('hitmap', 'large_source_hit_counts.csv', 'channel_index'),
                              ('cluster_size', 'large_source_cluster_size_counts.csv', 'export_bin_index'),
                              ('event_clusters', 'large_source_event_cluster_counts.csv', 'export_bin_index')]:
        item = by_kind[kind][0]
        tables[name] = [{index: i, 'count': count, 'source_id': item['id'], 'source_line': i + 2}
                        for i, count in enumerate(read_counts(root / item['path']))]
    item = by_kind['large_clusters'][0]
    count = channel_count = 0
    mean = m2 = 0.0
    minimum = float('inf')
    maximum = float('-inf')
    sizes = {}
    for _, values in iter_clusters(root / item['path']):
        total = sum(values)
        count += 1
        channel_count += len(values)
        delta = total - mean
        mean += delta / count
        m2 += delta * (total - mean)
        minimum, maximum = min(minimum, total), max(maximum, total)
        sizes[len(values)] = sizes.get(len(values), 0) + 1
    if count < 2 or maximum == minimum:
        raise ValueError('Large-source spectrum requires a nonconstant cluster sample')
    bins = [0] * 150
    width = (maximum - minimum) / len(bins)
    for _, values in iter_clusters(root / item['path']):
        index = min(int((sum(values) - minimum) / width), len(bins) - 1)
        bins[index] += 1
    tables['large_source_adc_spectrum.csv'] = [
        {'bin_index': i, 'lower_edge_adc': minimum + i * width,
         'upper_edge_adc': minimum + (i + 1) * width, 'count': value,
         'source_id': item['id']} for i, value in enumerate(bins)
    ]
    tables['large_source_signal_summary.csv'] = [{
        'cluster_count': count, 'contributing_channel_count': channel_count,
        'mean_cluster_sum_adc': mean,
        'sample_standard_deviation_adc': math.sqrt(m2 / (count - 1)),
        'standard_error_mean_adc': math.sqrt(m2 / (count - 1) / count),
        'minimum_cluster_sum_adc': minimum, 'maximum_cluster_sum_adc': maximum,
        'source_id': item['id'],
    }]
    tables['large_source_observed_cluster_sizes.csv'] = [
        {'channel_count': size, 'count': value, 'source_id': item['id']}
        for size, value in sorted(sizes.items())
    ]
    item = by_kind['current_voltage_transcription'][0]
    with (root / item['path']).open() as handle:
        tables['current_voltage_measurements.csv'] = list(csv.DictReader(handle))
    return tables


def write_tables(root=ROOT):
    root = Path(root)
    tables = make_tables(root)
    manifest = []
    for name, rows in tables.items():
        path = root / 'data/derived' / name
        with path.open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        manifest.append({'path': str(path.relative_to(root)), 'rows': len(rows),
                         'columns': list(rows[0]), 'sha256': sha256(path)})
    (root / 'metadata/derived_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Prepared {len(tables)} tables from the selected source copies.')
    return tables


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Rebuild all analysis tables from a local excerpt collection')
    parser.add_argument('--project-root', type=Path, default=ROOT,
                        help='Local project containing source files and the matching source manifest')
    args = parser.parse_args()
    manifest = json.loads((args.project_root / 'metadata/source_manifest.json').read_text())
    missing = [item['id'] for item in manifest['inputs'] if not (args.project_root / item['path']).is_file()]
    if missing:
        parser.exit(2, 'Source measurements are kept locally. Use --project-root with the complete local excerpt project.\n')
    if any(item['status'] != 'available' for item in manifest['inputs']):
        parser.exit(2, 'Use the available-input manifest from the complete local excerpt project.\n')
    write_tables(args.project_root)

