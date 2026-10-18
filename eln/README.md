# Local eLabFTW setup

The Compose file runs eLabFTW 6.0.8 with MySQL at `https://localhost:8443`. Image digests are pinned; records use persistent volumes. The local service uses a self-signed certificate.

## Configure

Create a separate runtime directory with `compose.yml` and a `.env` based on `.env.example`. Set independent database passwords and generate SECRET_KEY with the image's `bin/init tools:genkey`. Start with `docker compose up -d`.

Register an administrator, then owner, reviewer and outsider accounts. Store their IDs and write-capable API keys in a runtime JSON file:

```json
{
  "owner": {"id": 2, "api_key": "OWNER_KEY"},
  "reviewer": {"id": 3, "api_key": "REVIEWER_KEY"},
  "outsider": {"id": 4, "api_key": "OUTSIDER_KEY"}
}
```

Use the installation's assigned IDs. Write-capable keys let the test check record permissions independently of key restrictions. Runtime files stay outside the repository.

## Test

Copy the container's `/run/nginx/certs/server.pem` into the runtime directory, then run:

```bash
python3 scripts/exercise_eln.py --accounts /path/to/accounts.json --certificate /path/to/server.pem
```

The script creates a summary record and checks access, attachment hashes, corrections, locking and portable export. A source-data integration run passed 19 checks. The supplied payload attaches the aggregate calibration response; the same checks can be run on a new installation.

The loopback client trusts the copied certificate. Hostname matching is disabled because the generated certificate names the container; a restart regenerates it. Upload, export and cache volumes require UID/GID 1000 write access.

`docker compose stop` preserves records. Complete recovery needs the database, attachments and configuration. Production setup follows the [eLabFTW installation guide](https://doc.elabftw.net/docs/install/intro/); see also the [API](https://doc.elabftw.net/docs/usage/api/) and [backup guide](https://doc.elabftw.net/docs/install/backups/).
