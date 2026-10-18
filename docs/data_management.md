# Data management

This case-study plan follows the six sections of the DFG research-data checklist. The public release contains code, six aggregate tables and seven plots; source measurements are stored separately.

## 1. Data description

The analysis uses 36 detector exports covering calibration, pedestal/noise, laser scans, source scans and current-voltage measurements. Processing produces 16 tables; six aggregate tables are published. Formats are TXT/CSV, JSON and SVG, with a Python notebook. The selected excerpts contain 100 pedestal events per channel, 200 clusters per bias setting and 2,000 large-source clusters. Their first-observation selection is deterministic rather than random.

## 2. Documentation and quality

Source IDs, units, line references and SHA-256 manifests preserve traceability. Summary validation covers table schemas, finite values, source links and checksums. Parser fixtures exercise valid and malformed exports. Source validation also verifies input hashes and regenerates the tables. Missing acquisition dates and instrument settings remain recorded as unknown.

## 3. Storage and backup

Originals, historical notebooks and private mappings are stored separately from derived results. Software changes are tracked with Git. ELN recovery requires its database, attachments and configuration. The preservation tool verifies transfer and restore of the published tables and metadata; it is separate from a full laboratory backup.

## 4. Attribution and access

Source files, reference documents and credentials are excluded from version control. The ELN example separates owner editing, reviewer reading and denial for an unassigned user. MIT applies to the code.

## 5. Reuse and preservation

Open formats, the dictionary, provenance and processing code support interpretation and reuse. Regeneration requires access to the source exports. Institutional retention, repository deposit and any additional data-reuse terms are decisions for the laboratory. A repository with persistent identifiers would support long-term discovery.

## 6. Responsibilities

The contributor verifies scientific context; the steward maintains schemas and quality checks; the laboratory lead decides access and retention; the administrator manages accounts and recovery. These roles describe a possible institutional workflow. Storage, staff time and repository costs would be budgeted before adoption.

## FAIR and Horizon Europe mapping

| Area | Implementation | Next step for institutional use |
|---|---|---|
| Findable | Stable source IDs and manifests | Persistent repository identifier |
| Accessible | Public summaries and figures; locally held sources | Document source-access arrangements |
| Interoperable | Defined units, open formats, PROV-O graph | Review domain vocabulary |
| Reusable | Code, dictionary, provenance and tests | Confirm retention and data-reuse terms |
| Resources | Responsibilities above | Assign owners and budget |
| Security and ethics | Restricted source collection and role-based ELN access | Apply institutional policies |

Sources: [DFG checklist](https://www.dfg.de/resource/blob/174736/92691e48e89bf4ac88c8eb91b8f783b0/forschungsdaten-checkliste-en-data.pdf), [Horizon Europe DMP template](https://ec.europa.eu/info/funding-tenders/opportunities/docs/2021-2027/horizon/temp-form/report/data-management-plan_he_en.docx).
