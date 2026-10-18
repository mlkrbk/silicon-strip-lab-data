#!/usr/bin/env python3
"""Check the code-and-results package for excluded files and credentials."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORED_PARTS = {'local', '__pycache__', '.ipynb_checkpoints', '.git', '.venv', 'venv'}
TEXT_SUFFIXES = {'.py', '.md', '.json', '.yml', '.yaml', '.txt', '.csv', '.ipynb', '.svg'}


def check(root=ROOT):
    root = Path(root)
    errors = []
    count = total = 0
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if not path.is_file() or any(part in IGNORED_PARTS for part in relative.parts):
            continue
        if path.name == '.env' or (path.name.endswith('.env') and path.name != '.env.example') or path.name == '.DS_Store' or path.suffix in {'.pyc', '.zip', '.so', '.dylib', '.pdf', '.pem', '.key', '.sql'}:
            errors.append(f'Unexpected generated or binary file: {relative}')
            continue
        if path.name not in {'README.md', 'LICENSE', '.gitignore'} and not re.fullmatch(r'[a-z0-9_.-]+', path.name):
            errors.append(f'Nonstandard filename: {relative}')
        size = path.stat().st_size
        if size >= 100 * 1024 * 1024:
            errors.append(f'File exceeds ordinary GitHub file limit: {relative}')
        count += 1
        total += size
        if path.suffix in TEXT_SUFFIXES:
            text = path.read_text()
            if re.search(r'/(?:Users|home)/[^\s"\']+', text):
                errors.append(f'Machine-specific absolute path: {relative}')
            if re.search(r'(?:ghp_|github_pat_|sk_live_)[A-Za-z0-9]{16,}', text):
                errors.append(f'Possible credential: {relative}')
    allowed_results = {'calibration_mean_response.csv', 'pedestal_channel_statistics.csv',
                       'source_voltage_response.csv', 'large_source_adc_spectrum.csv',
                       'large_source_signal_summary.csv', 'large_source_observed_cluster_sizes.csv'}
    if any(p.is_file() for p in (root / 'data/source').rglob('*')):
        errors.append('Source measurements are excluded from the public package')
    for path in (root / 'data/derived').glob('*'):
        if path.is_file() and path.name not in allowed_results:
            errors.append('Unreviewed or point-level result table: ' + path.name)
    return errors, {'files_checked': count, 'total_bytes': total}


if __name__ == '__main__':
    errors, info = check()
    for error in errors:
        print('ERROR:', error)
    print(json.dumps(info, indent=2))
    print('Repository hygiene:', 'FAIL' if errors else 'PASS')
    raise SystemExit(bool(errors))
