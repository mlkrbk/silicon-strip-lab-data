#!/usr/bin/env python3
"""Create and verify BagIt 1.0 transfers with SHA-256 manifests."""
import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def inventory(root, prefix):
    return sorted(p for p in (root / prefix).rglob('*') if p.is_file())

def manifest(root, paths):
    return ''.join(f'{digest(p)}  {p.relative_to(root).as_posix()}\n' for p in paths)

def create(target, project=ROOT):
    target, project = Path(target), Path(project)
    if target.resolve().is_relative_to(project.resolve()):
        raise ValueError('Transfer destination must be outside the project')
    target.mkdir(parents=True, exist_ok=False)
    for name in ('data', 'metadata'):
        shutil.copytree(project / name, target / 'data' / name)
    (target / 'bagit.txt').write_text('BagIt-Version: 1.0\nTag-File-Character-Encoding: UTF-8\n', encoding='utf-8')
    files = inventory(target, 'data')
    (target / 'bag-info.txt').write_text(f'Bag-Software-Agent: silicon-strip-preservation-demo\nPayload-Oxum: {sum(p.stat().st_size for p in files)}.{len(files)}\n', encoding='utf-8')
    (target / 'manifest-sha256.txt').write_text(manifest(target, files), encoding='utf-8')
    tags = [target / n for n in ('bagit.txt', 'bag-info.txt', 'manifest-sha256.txt')]
    (target / 'tagmanifest-sha256.txt').write_text(manifest(target, tags), encoding='utf-8')
    return verify(target)

def verify(root):
    root = Path(root)
    if (root / 'bagit.txt').read_text() != 'BagIt-Version: 1.0\nTag-File-Character-Encoding: UTF-8\n':
        raise ValueError('Unexpected BagIt declaration')
    for filename, payload in [('manifest-sha256.txt', True), ('tagmanifest-sha256.txt', False)]:
        seen = set()
        for line in (root / filename).read_text().splitlines():
            expected, rel = line.split('  ', 1)
            p = root / rel
            if p.is_symlink() or not p.resolve().is_relative_to(root.resolve()) or rel in seen:
                raise ValueError('Unsafe or duplicate manifest path')
            if len(expected) != 64 or not p.is_file() or digest(p) != expected:
                raise ValueError('Missing or changed transfer member: ' + rel)
            seen.add(rel)
        required = {p.relative_to(root).as_posix() for p in inventory(root, 'data')} if payload else {'bagit.txt', 'bag-info.txt', 'manifest-sha256.txt'}
        if seen != required:
            raise ValueError('Manifest coverage differs from transfer contents')
    files = inventory(root, 'data')
    oxum = f'Payload-Oxum: {sum(p.stat().st_size for p in files)}.{len(files)}'
    if oxum not in (root / 'bag-info.txt').read_text().splitlines():
        raise ValueError('Payload-Oxum mismatch')
    return {'payload_files': len(files), 'payload_bytes': sum(p.stat().st_size for p in files), 'integrity_verified': True}

def self_test(project=ROOT):
    with tempfile.TemporaryDirectory() as tmp:
        bag, restored = Path(tmp) / 'bag', Path(tmp) / 'restored'
        result = create(bag, project)
        shutil.copytree(bag, restored)
        verify(restored)
        changed = inventory(restored, 'data')[0]
        changed.write_bytes(changed.read_bytes() + b'\nchanged\n')
        rejected = False
        try:
            verify(restored)
        except ValueError:
            rejected = True
        if not rejected:
            raise AssertionError('Corruption was accepted')
        return dict(result, independent_copy_restore_verified=True, payload_corruption_rejected=True,
                    scope='file-transfer payload only; not an ELN database restore', independent_validator_used=False)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--create', type=Path)
    action.add_argument('--verify', type=Path)
    action.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    result = self_test() if args.self_test else create(args.create) if args.create else verify(args.verify)
    if args.self_test:
        (ROOT / 'reports/preservation_validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
