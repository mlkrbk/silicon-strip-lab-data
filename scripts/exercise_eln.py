#!/usr/bin/env python3
"""Check eLabFTW record permissions, attachments, revision history and export."""
import argparse
import datetime
import hashlib
import json
import io
import zipfile
import ssl
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def run(accounts_file, certificate, base_url):
    if base_url != 'https://localhost:8443':
        raise ValueError('This exercise is restricted to the dedicated loopback demonstration')
    accounts = json.loads(Path(accounts_file).read_text())
    context = ssl.create_default_context(cafile=str(certificate))
    # The container certificate uses its hostname rather than localhost.
    # The supplied CA file pins trust to that certificate.
    context.check_hostname = False
    evidence = {'executed_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'endpoint': base_url, 'checks': []}
    def request(role, path, method='GET', payload=None, raw=False, content_type='application/json'):
        headers = {'Authorization': accounts[role]['api_key']}
        if payload is not None:
            headers['Content-Type'] = content_type
            if not isinstance(payload, bytes):
                payload = json.dumps(payload).encode()
        req = urllib.request.Request(base_url + '/api/v2/' + path, data=payload, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, context=context, timeout=30) as response:
                body = response.read()
                return response.status, body if raw else json.loads(body) if body else None, dict(response.headers)
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode()[:300], {}
    def check(name, actual, expected):
        evidence['checks'].append({'name': name, 'actual': actual, 'expected': expected, 'passed': actual == expected})
    payload = json.loads((ROOT / 'eln/experiment_payload.json').read_text())
    status, body, headers = request('owner', 'experiments', 'POST', payload)
    check('create_structured_record', status, 201)
    if status != 201:
        raise RuntimeError(str(body))
    record_id = int(headers['Location'].rstrip('/').split('/')[-1])
    evidence['record_id'] = record_id
    path = f'experiments/{record_id}'
    status, body, _ = request('owner', path, 'PATCH', {'canread_base': 10, 'canwrite_base': 10,
        'canread': json.dumps({'teams': [], 'teamgroups': [], 'users': [accounts['reviewer']['id']]}),
        'canwrite': json.dumps({'teams': [], 'teamgroups': [], 'users': []})})
    check('set_explicit_restricted_permissions', status, 200)
    for role, expected in [('owner', 200), ('reviewer', 200), ('outsider', 403)]:
        status, body, _ = request(role, path)
        check(role + '_read', status, expected)
    for role in ('reviewer', 'outsider'):
        status, body, _ = request(role, path, 'PATCH', {'title': 'Unauthorized change should fail'})
        check(role + '_write_denied', status, 403)
    source = ROOT / 'metadata/source_manifest.json'
    content = source.read_bytes()
    boundary = 'siliconstripmigrationboundary'
    data = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="source_manifest.json"\r\nContent-Type: application/json\r\n\r\n'.encode()
            + content + f'\r\n--{boundary}--\r\n'.encode())
    status, body, headers = request('owner', path + '/uploads', 'POST', data, content_type='multipart/form-data; boundary=' + boundary)
    check('attach_source_manifest', status, 201)
    evidence['attached_source_manifest_sha256'] = hashlib.sha256(content).hexdigest()
    status, record, _ = request('owner', path)
    calibration = (ROOT / 'data/derived/calibration_mean_response.csv').read_bytes()
    csv_data = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="calibration_mean_response.csv"\r\nContent-Type: text/csv\r\n\r\n'.encode()
                + calibration + f'\r\n--{boundary}--\r\n'.encode())
    status, _, _ = request('owner', path + '/uploads', 'POST', csv_data, content_type='multipart/form-data; boundary=' + boundary)
    check('attach_calibration_table', status, 201)
    status, record, _ = request('owner', path)
    check('calibration_server_checksum_matches', any(u.get('hash') == hashlib.sha256(calibration).hexdigest() for u in record.get('uploads', [])), True)
    evidence['uploads_metadata'] = record.get('uploads', [])
    check('attachment_server_checksum_matches', any(u.get('hash') == hashlib.sha256(content).hexdigest() and u.get('hash_algorithm') == 'sha256' for u in record.get('uploads', [])), True)
    revised = payload['body'] + '\nCorrection: the record creation date is the import date; acquisition date remains unknown.'
    status, body, _ = request('owner', path, 'PATCH', {'body': revised})
    check('owner_documented_correction', status, 200)
    status, record, _ = request('owner', path)
    check('corrected_body_persisted', record.get('body') == revised, True)
    check('structured_scope_persisted', record['metadata_decoded']['extra_fields']['scope']['value'], 'public_summary_results')
    evidence['changelog'] = record.get('changelog', [])
    check('body_change_attributed_in_changelog', any(c.get('target') == 'body' and c.get('userid') == accounts['owner']['id'] for c in evidence['changelog']), True)
    status, revisions, _ = request('owner', path + '/revisions')
    evidence['revision_read_status'] = status
    evidence['revision_count'] = len(revisions) if isinstance(revisions, list) else None
    status, _, _ = request('owner', path, 'PATCH', {'action': 'forcelock'})
    check('owner_locks_record', status, 200)
    status, record, _ = request('owner', path)
    check('lock_state_persisted', record.get('locked'), 1)
    status, archive, _ = request('owner', path + '?format=eln', raw=True)
    evidence['portable_export_http_status'] = status
    if status == 200 and isinstance(archive, bytes) and zipfile.is_zipfile(io.BytesIO(archive)):
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            names = z.namelist()
            check('portable_export_has_ro_crate_metadata', any(n.endswith('ro-crate-metadata.json') for n in names), True)
            check('portable_export_calibration_bytes_preserved', any(z.read(n) == calibration for n in names if not n.endswith('/')), True)
            evidence['portable_export_sha256'] = hashlib.sha256(archive).hexdigest()
            evidence['portable_export_bytes'] = len(archive)
    else:
        evidence['portable_export_verified'] = False
    evidence['all_recorded_checks_passed'] = all(c['passed'] for c in evidence['checks'])
    report = ROOT / 'reports/eln_runtime_validation.json'
    report.write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({'record_id': record_id, 'checks': evidence['checks'], 'all_recorded_checks_passed': evidence['all_recorded_checks_passed']}, indent=2))
    return evidence

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--accounts', type=Path, required=True)
    parser.add_argument('--certificate', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.accounts, args.certificate, 'https://localhost:8443')
    raise SystemExit(not result['all_recorded_checks_passed'])
