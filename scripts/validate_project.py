#!/usr/bin/env python3
"""Validate published summary tables, with optional local source checks."""
import argparse
import csv
import io
import json
import math
from pathlib import Path
from prepare_data import ROOT, make_tables, sha256


def validate(root=ROOT, recompute=False, require_sources=False):
    root=Path(root)
    errors,warnings=[],[]
    try:
        manifest=json.loads((root/'metadata/source_manifest.json').read_text())
        ids=[item['id'] for item in manifest['inputs']]
        if len(ids)!=len(set(ids)):
            errors.append('Duplicate source identifier')
        seen=set(ids)
        check_sources=require_sources or recompute
        missing=[]
        if check_sources:
            for item in manifest['inputs']:
                path=root/item['path']
                if not path.is_file():
                    missing.append(item['id']);continue
                if sha256(path)!=item['sha256']:
                    errors.append('Source checksum mismatch: '+item['id'])
                if path.stat().st_size!=item['bytes']:
                    errors.append('Source size mismatch: '+item['id'])
            if missing:
                errors.append('Local source files required: '+', '.join(missing))
        derived=json.loads((root/'metadata/derived_manifest.json').read_text())
        for spec in derived:
            path=root/spec['path']
            if sha256(path)!=spec['sha256']:
                errors.append('Derived checksum mismatch: '+spec['path'])
            with path.open(newline='') as handle:
                reader=csv.DictReader(handle)
                if reader.fieldnames!=spec['columns']:
                    errors.append('Column schema mismatch: '+spec['path'])
                rows=list(reader)
            if len(rows)!=spec['rows']:
                errors.append('Row count mismatch: '+spec['path'])
            identifiers=[row['measurement_id'] for row in rows if 'measurement_id' in row]
            if len(identifiers)!=len(set(identifiers)):
                errors.append('Duplicate measurement identifier')
            for row in rows:
                for column,value in row.items():
                    if column in ['source_id','notebook_id','measurement_id']:
                        if column=='source_id' and value not in seen:
                            errors.append('Unknown source identifier')
                    elif not math.isfinite(float(value)):
                        errors.append('Nonfinite value in '+spec['path'])
        if recompute and not errors:
            if any(item['status']!='available' for item in manifest['inputs']):
                errors.append('Local reconstruction requires the available-input manifest from the complete excerpt project')
            else:
                tables=make_tables(root)
                for spec in derived:
                    name=Path(spec['path']).name;rows=tables[name]
                    buffer=io.StringIO(newline='')
                    writer=csv.DictWriter(buffer,fieldnames=list(rows[0]))
                    writer.writeheader();writer.writerows(rows)
                    if buffer.getvalue().encode()!=(root/spec['path']).read_bytes():
                        errors.append('Source-to-derived reproduction failure: '+name)
    except (OSError,ValueError,KeyError,TypeError,IndexError) as exception:
        errors.append('Validation failed: '+str(exception))
    return errors,warnings


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root',type=Path,default=ROOT)
    parser.add_argument('--with-sources',action='store_true',help='Check local source hashes and regenerate tables for comparison')
    parser.add_argument('--require-complete',action='store_true',help='Require local source files; alias for --with-sources')
    args=parser.parse_args()
    local=args.with_sources or args.require_complete
    errors,warnings=validate(args.project_root,recompute=local,require_sources=local)
    specs=json.loads((args.project_root/'metadata/derived_manifest.json').read_text())
    report={'status':'FAIL' if errors else 'PASS','scope':'local_source_and_results' if local else 'published_summary_results',
            'source_checks_performed':local,'recomputation_performed':local and not errors,
            'summary_tables_checked':len(specs),'errors':errors,'warnings':warnings}
    (args.project_root/'reports/validation_report.json').write_text(json.dumps(report,indent=2)+'\n')
    for error in errors:print('ERROR:',error)
    print(report['status'])
    raise SystemExit(bool(errors))
