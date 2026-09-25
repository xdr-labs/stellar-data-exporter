# Stellar Data Exporter

A lightweight web UI for exporting Stellar Cyber query results as CSV or JSON.

## Current MVP

The first working slice is intentionally small:

- no application login or user database
- Stellar Cyber host + account email + root-scope All-Access Token supplied per browser session
- automatic exchange of the All-Access Token for a short-lived JWT
- automatic JWT refresh before expiry and one retry after HTTP 401
- user-friendly multi-select data sources mapped internally to Stellar Cyber indices
- user-supplied query conditions plus a live effective Elasticsearch request/DSL preview
- explicit start/end time range reflected immediately in the effective DSL
- readable connection/authentication/permission errors
- query validation and 100-record preview
- adaptive time slicing for large ranges
- streamed CSV, JSON Array, or NDJSON output
- CSV advanced options: delimiter, optional header, UTF-8 BOM, and nested-object flattening
- optional gzip compression
- optional max file size with numbered split files such as `export-0001.csv.gz`
- browser download; multiple split parts are bundled as a ZIP
- S3-compatible upload (AWS S3, Cloudflare R2, MinIO) with multipart streaming
- SFTP upload with password or SSH private-key authentication
- split S3/SFTP exports write each numbered part separately
- live in-memory export execution state plus SQLite-backed persistent export history for browser, S3-compatible, and SFTP destinations
- live progress metrics: records, transferred bytes, files, current slice, queries, retries, rate, and elapsed time
- cooperative cancellation with S3 multipart abort and SFTP partial-file cleanup
- durable completed-part checkpoints for split S3/SFTP exports with filename, size, SHA-256, and remote result URI
- resume/retry for failed, cancelled, or restart-interrupted remote jobs; verified completed split parts are skipped and credentials are re-entered rather than persisted
- record-level duplicate suppression only when Stellar/Elasticsearch returns a stable `_index` + `_id`; records without stable identity are preserved to avoid false data loss
- explicit overlap policy for matching export pipelines: manual exports default to `allow`, while Advanced mode can `reject` intersecting time ranges; adjacent half-open ranges remain valid
- optional scheduled S3/SFTP exports with encrypted-at-rest query/account/destination configuration, Run now/Pause/Enable/Delete controls, timestamped output filenames, and contiguous windows from the last successful run
- relative time presets (15m, 1h, 24h, 7d) plus custom relative ranges
- saved export profiles in browser localStorage with credentials explicitly excluded
- browser-local query history and favorites

## Data flow

```text
Browser
  -> host / email / All-Access Token / index / DSL / time range
  -> FastAPI
  -> POST /connect/api/v1/access_token using Basic(email:token)
  -> short-lived JWT
  -> GET /connect/api/data/{index}/_search using Bearer JWT
  -> adaptive non-overlapping time slices
  -> CSV / JSON Array / NDJSON stream
  -> one-time browser download
```

The exporter injects the requested time range around the user's query. A slice is counted first.
If the slice exceeds the configured target record count, it is bisected and retried until a safe
slice is reached. Ranges use half-open boundaries `[start, end)`, avoiding slice-boundary duplicates. When stable document identity is present, repeated `_index` + `_id` hits are skipped and counted in the live `Duplicates skipped` metric. No source-content hash fallback is used when identity is absent, because that could discard legitimately distinct records.

Time slicing limits records returned per request, but it does not by itself reduce Elasticsearch
shard fan-out from a broad index such as `aella-wineventlog-*`. For long ranges, use a date-scoped
or date-math index expression when that Stellar index family supports it; the UI warns on open
wildcards spanning more than 24 hours.

## Security boundary

- credentials are not persisted to disk, a database, or browser localStorage
- saved profiles persist only non-secret configuration; account token, S3 keys, SFTP passwords, and private keys are excluded
- credentials are held only in process memory for request handling and one-time export jobs
- persistent job history stores sanitized metadata only; API tokens, raw queries, account email, S3 credentials, and SFTP passwords/private keys are excluded
- active jobs interrupted by an exporter restart are recorded as `interrupted`; remote jobs can then be resumed after the operator re-enters the original export settings and credentials
- resume identity is stored only as a SHA-256 fingerprint of export-affecting non-credential settings plus the query content; the raw query is not persisted
- completed split parts are re-generated and SHA-256 verified before they are skipped, so changed query/output data fails closed instead of silently producing mixed exports
- one-time download job identifiers expire after 10 minutes, while their sanitized history remains available
- TLS verification is enabled by default
- there is currently no multi-user isolation layer; deploy this MVP only in a trusted environment
- never expose the service directly to the public Internet in its current development state

Persistent job history defaults to `.data/export-jobs.sqlite3` with owner-only file permissions. Set `STELLAR_EXPORTER_JOB_DB` to override the database path. The store contains sanitized job metadata, resume fingerprint, completed-part checkpoints, and progress/result fields only; executable payloads and credentials remain memory-only. Split remote exports resume at verified part boundaries. A non-split remote job has no completed part boundary, so Resume retries that single file from the beginning.

Scheduled exports use a separate `.data/export-schedules.sqlite3` store plus `.data/schedule.key`, both owner-only (`0600`). The full scheduled export payload — including query, Stellar account token, and S3/SFTP credentials — is Fernet-encrypted before it is written. For production, inject the master key through `STELLAR_EXPORTER_SCHEDULE_KEY`; `STELLAR_EXPORTER_SCHEDULE_DB`, `STELLAR_EXPORTER_SCHEDULE_KEY_FILE`, and `STELLAR_EXPORTER_SCHEDULE_POLL_SECONDS` override the default paths/poll interval. Scheduled exports support S3/SFTP only, always use overlap rejection, and continue the next successful window from the previous success end so scheduler delays do not create gaps.

## Stellar Cyber API authentication

Raw Elasticsearch index queries are intended for Super Admin users with root scope and an
All-Access Token. Scoped API keys are not supported by the raw `/connect/api/data` endpoint.

The adapter exchanges the account email and All-Access Token at
`/connect/api/v1/access_token`, caches the returned JWT for less than its documented
10-minute lifetime, and refreshes automatically during long-running exports. A 401 from
the data API forces one immediate JWT refresh and retry.

## Run on dev-atlas

The development server is served directly over HTTPS on port 8787.

Create or refresh the development certificate:

```bash
cd /home/aella/stellar-data-exporter
./scripts/generate-dev-cert.sh
```

Start the HTTPS service:

```bash
./scripts/run-dev-https.sh
```

URLs:

```text
https://dev-atlas:8787
https://221.139.249.116:8787
```

Health check for the current self-signed development certificate:

```bash
curl -k https://127.0.0.1:8787/api/health
```

The development certificate includes SAN entries for `dev-atlas`, `localhost`,
`127.0.0.1`, and the current dev-atlas IP. It is self-signed, so browsers that do not
trust the certificate will show a certificate warning. For an Internet-facing deployment,
replace it with a certificate issued for the production DNS name by a trusted CA.

## Tests

```bash
uv run --extra dev pytest -q
node --check static/app.js
```

## Roadmap status

P0 query/export usability and P1 user productivity are implemented and browser-verified.

P2 operationalization, after one-shot export is stable:
1. persistent job store and export history without plaintext credentials — implemented
2. checkpoint/resume and retry-from-checkpoint for remote destinations — implemented at durable split-part boundaries; non-split retries from the beginning
3. overlap/dedup strategy for resumed or scheduled exports — implemented with half-open ranges, stable document-identity dedup, and explicit allow/reject overlap policy
4. optional scheduled exports with encrypted credential persistence — implemented for S3/SFTP with protected payload storage, contiguous windows, manual Run now, Pause/Enable, Delete, and restart persistence
5. production hardening: reverse proxy, access boundary, rate limits, deployment/runbook
