#!/usr/bin/env python3
"""Render detector calibration, noise, scan and cluster-spectrum figures."""
import argparse
import csv
from pathlib import Path
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, String, Line, Group
from reportlab.graphics import renderSVG
from reportlab.lib.colors import HexColor

ROOT = Path(__file__).resolve().parents[1]
COLORS = ['#176B9A', '#CE671E', '#23836B', '#8054A1', '#6E7380', '#111827']


def read(name):
    with (ROOT / 'data/derived' / name).open() as handle:
        return list(csv.DictReader(handle))


def plot(filename, title, series, x_label, y_label, subtitle='', x_limits=None, y_limits=None):
    drawing = Drawing(640, 440)
    drawing.add(String(35, 414, title, fontName='Helvetica-Bold', fontSize=16, fillColor=HexColor('#152C3D')))
    drawing.add(String(35, 395, subtitle, fontName='Helvetica', fontSize=9, fillColor=HexColor('#52616C')))
    chart = LinePlot()
    chart.x, chart.y, chart.width, chart.height = 75, 72, 520, 270
    chart.data = [points for _, points in series]
    chart.xValueAxis.labels.fontName = chart.yValueAxis.labels.fontName = 'Helvetica'
    chart.xValueAxis.labels.fontSize = chart.yValueAxis.labels.fontSize = 9
    chart.xValueAxis.strokeColor = chart.yValueAxis.strokeColor = HexColor('#A7B3BA')
    chart.yValueAxis.visibleGrid = True
    chart.yValueAxis.gridStrokeColor = HexColor('#E1E7EB')
    if x_limits:
        chart.xValueAxis.valueMin, chart.xValueAxis.valueMax = x_limits
    if y_limits:
        chart.yValueAxis.valueMin, chart.yValueAxis.valueMax = y_limits
    for i, (label, _) in enumerate(series):
        chart.lines[i].strokeColor = HexColor(COLORS[i % len(COLORS)])
        chart.lines[i].strokeWidth = 1.5
        x, y = 75 + (i % 3) * 175, 377 - (i // 3) * 16
        drawing.add(Line(x, y, x + 18, y, strokeColor=HexColor(COLORS[i % len(COLORS)]), strokeWidth=2))
        drawing.add(String(x + 23, y - 3, label, fontSize=8))
    drawing.add(chart)
    drawing.add(String(335, 30, x_label, textAnchor='middle', fontSize=10))
    group = Group(String(0, 0, y_label, textAnchor='middle', fontSize=10))
    group.rotate(90)
    group.translate(207, -19)
    # Explicit transform places the vertical axis label at the left of the plot.
    group.transform = (0, 1, -1, 0, 20, 207)
    drawing.add(group)
    drawing.add(String(35, 8, 'Silicon-strip laboratory measurements', fontSize=7, fillColor=HexColor('#647580')))
    destination = ROOT / 'reports/figures' / filename
    renderSVG.drawToFile(drawing, str(destination))
    return drawing


def main():
    figures = {}
    rows = read('calibration_measurements.csv')
    series = []
    for ch in [3, 29, 65, 83, 107]:
        series.append((f'Channel {ch}', [(float(r['injected_charge_electrons']), float(r['signal_adc'])) for r in rows if int(r['channel_label']) == ch]))
    means = read('calibration_mean_response.csv')
    series.append(('Five-channel mean', [(float(r['injected_charge_electrons']), float(r['mean_signal_adc'])) for r in means]))
    figures['calibration_response.svg'] = plot('calibration_response.svg', 'Silicon-strip charge calibration', series, 'Injected charge (electrons)', 'Signal (ADC counts)', 'Five channel curves; initial zero-charge samples retained.', (0, 260096), (0, 300))
    rows = read('pedestal_channel_statistics.csv')
    figures['pedestal_response.svg'] = plot('pedestal_response.svg', 'Pedestal offsets across the sensor', [('Channel mean', [(float(r['channel_index']), float(r['pedestal_adc'])) for r in rows])], 'Channel index (zero-based)', 'Pedestal (ADC counts)', '128 channels; 100 events per channel.', (0, 127))
    original = read('historical_channel_noise.csv')
    figures['noise_comparison.svg'] = plot('noise_comparison.svg', 'Noise quantities retained separately', [('Historical export', [(float(r['export_bin_center']), float(r['value_adc'])) for r in original]), ('Corrected noise (100 events)', [(float(r['channel_index']), float(r['common_mode_corrected_sample_noise_adc'])) for r in rows])], 'Channel coordinate (see data dictionary)', 'Noise (ADC counts)', 'Historical noise export and corrected sample noise (100 events per channel).', (0, 128), (0, 7))
    rows = read('laser_position_scan.csv')
    series = [(f'Channel {ch}', [(float(r['relative_offset_mm']), float(r['signal_adc'])) for r in rows if int(r['channel_index']) == ch]) for ch in [42, 43, 44, 45]]
    figures['laser_position_response.svg'] = plot('laser_position_response.svg', 'Laser position scan across four channels', series, 'Relative laser offset (mm)', 'Mean signal (ADC counts)', '35 positions at 0.01 mm spacing.', (0, .34))
    rows = read('source_voltage_response.csv')
    series = [('Historical first channel', [(float(r['bias_voltage_v']), float(r['historical_mean_first_channel_adc'])) for r in rows]), ('Sum over each cluster', [(float(r['bias_voltage_v']), float(r['mean_cluster_sum_adc'])) for r in rows])]
    figures['source_voltage_response.svg'] = plot('source_voltage_response.svg', 'Source response versus detector bias', series, 'Detector bias (V)', 'Mean signal (ADC counts)', '200 complete clusters per setting; all contributing channel signals summed.', (0, 200), (0, 110))
    rows = read('large_source_adc_spectrum.csv')
    points = [((float(r['lower_edge_adc']) + float(r['upper_edge_adc'])) / 2, float(r['count'])) for r in rows if (float(r['lower_edge_adc']) + float(r['upper_edge_adc'])) / 2 <= 250]
    figures['large_source_adc_spectrum.svg'] = plot('large_source_adc_spectrum.svg', 'Large-source cluster signal spectrum', [('Summed cluster ADC', points)], 'Cluster signal (ADC counts)', 'Clusters per bin', '150 equal-width bins over the complete observed range; displayed region 0-250 ADC.', (0, 250))
    rows = read('current_voltage_measurements.csv')
    figures['current_voltage_response.svg'] = plot('current_voltage_response.svg', 'Current-voltage characteristic', [('Notebook transcription', [(float(r['bias_voltage_v']), float(r['leakage_current_ua'])) for r in rows])], 'Detector bias (V)', 'Leakage current (microampere)', 'Current-voltage series from the historical analysis; 20 bias settings.', (0, 190))
    print(f'Created {len(figures)} SVG figures.')
    return figures


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Render figures from the complete local analysis tables')
    parser.add_argument('--project-root', type=Path, default=ROOT)
    args = parser.parse_args()
    ROOT = args.project_root.resolve()
    required = ['calibration_measurements.csv', 'calibration_mean_response.csv',
                'pedestal_channel_statistics.csv', 'historical_channel_noise.csv',
                'laser_position_scan.csv', 'source_voltage_response.csv',
                'large_source_adc_spectrum.csv', 'current_voltage_measurements.csv']
    if any(not (ROOT / 'data/derived' / name).is_file() for name in required):
        parser.exit(2, 'Plot regeneration requires the complete local tables. Use --project-root with the local excerpt project.\n')
    main()

