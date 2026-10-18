# Workflow

## Selection and provenance

The starting collection contained overlapping exports and notebook versions. Selected inputs were matched to the historical analysis, assigned stable source IDs and copied with formal names. The original collection stays separate from processing.

`metadata/source_manifest.json` records input identities, selection evidence, parent/excerpt hashes and extraction rules. `withheld` marks source files not included in this repository. `derived_manifest.json` records the six published tables; `data_dictionary.json` defines their columns and units. The PROV-O graph describes derivation between parent and excerpt bitstreams.

## Processing

The parsers handle paired curves, matrices, count exports and variable-length cluster rows. A cluster sum includes every contributing channel. Derived tables retain source IDs and input-line references where applicable.

Validation runs on the included summaries. To regenerate results, provide a project directory containing the source exports and the matching manifest with input status `available`:

```bash
python3 scripts/prepare_data.py --project-root /path/to/local_excerpt_project
python3 scripts/validate_project.py --project-root /path/to/local_excerpt_project --with-sources
python3 -m pip install -r requirements-figures.txt
python3 scripts/create_figures.py --project-root /path/to/local_excerpt_project
```

`--project-root` selects the directory used for input and output. The plotting command requires the complete set of analysis tables.

## Interpretation

Results describe the selected excerpts. The energy-equivalent column converts injected charge; it is not a validated inverse ADC calibration. The nominal zero-bias comparison reuses one channel curve. Historical noise exports and recomputed sample noise have different definitions and coverage. The ADC spectrum is presented without a particle-energy conversion.

## ELN and researcher walkthrough

Use the [ELN setup](../eln/README.md) and payload to create a structured record. Reference local sources by ID/hash and attach the aggregate calibration response. Keep acquisition and import dates separate.

| Role | Read restricted record | Edit |
|---|---|---|
| Owner | Yes | Yes |
| Named reviewer | Yes | No |
| Unassigned user | No | No |

A researcher walkthrough takes about 25 minutes: locate a source ID, check its units/checksum, create a record, attach the summary, make a correction with a reason, inspect the earlier version and export it. The reviewer checks the content and permissions. Record unclear fields and suggested changes as feedback.

For corrections, retain the affected record/source ID, issue owner, rationale, validation result and review outcome. The ELN integration tests cover access, attachments, change history, locking and export. Production or regulated use would require institution-specific qualification and recovery procedures.

## Preservation

```bash
python3 scripts/preserve_package.py --self-test
```

The test creates a temporary BagIt 1.0 package, verifies SHA-256 manifests, checks an independently restored copy and confirms that altered data are rejected. It packages the published tables and metadata. Preserve the matching software release and local source collection separately.

Use `--create /path/to/new_bag` and `--verify /path/to/new_bag` for a retained transfer. The layout follows [RFC 8493](https://www.rfc-editor.org/rfc/rfc8493).
