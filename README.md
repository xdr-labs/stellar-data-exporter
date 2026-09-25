# Stellar Data Exporter

A lightweight web UI for exporting Stellar Cyber query results as CSV or JSON.

## Current MVP

The first working slice is intentionally small:

- no application login or user database
- Stellar Cyber host + account email + root-scope All-Access Token supplied per browser session
- automatic exchange of the All-Access Token for a short-lived JWT
- automatic JWT refresh before expiry and one retry after HTTP 401
- user-supplied Elasticsearch DSL
- explicit start/end time range
- query validation and 100-record preview
- adaptive time slicing for large ranges
- streamed CSV or JSON output
- optional gzip compression
- browser download
- S3-compatible upload (AWS S3, Cloudflare R2, MinIO) with multipart streaming
- SFTP upload with password or SSH private-key authentication
- in-memory background job status for remote destinations

## Data flow

```text
Browser
  -> host / email / All-Access Token / index / DSL / time range
  -> FastAPI
  -> POST /connect/api/v1/access_token using Basic(email:token)
  -> short-lived JWT
  -> GET /connect/api/data/{index}/_search using Bearer JWT
  -> adaptive non-overlapping time slices
  -> CSV or JSON stream
  -> one-time browser download
```

The exporter injects the requested time range around the user's query. A slice is counted first.
If the slice exceeds the configured target record count, it is bisected and retried until a safe
slice is reached. Ranges use half-open boundaries `[start, end)`, avoiding overlap duplicates.

Time slicing limits records returned per request, but it does not by itself reduce Elasticsearch
shard fan-out from a broad index such as `aella-wineventlog-*`. For long ranges, use a date-scoped
or date-math index expression when that Stellar index family supports it; the UI warns on open
wildcards spanning more than 24 hours.

## Security boundary

- credentials are not persisted to disk or a database
- credentials are held only in process memory for request handling and one-time export jobs
- one-time download job identifiers expire after 10 minutes
- TLS verification is enabled by default
- there is currently no multi-user isolation layer; deploy this MVP only in a trusted environment
- never expose the service directly to the public Internet in its current development state

## Stellar Cyber API authentication

Raw Elasticsearch index queries are intended for Super Admin users with root scope and an
All-Access Token. Scoped API keys are not supported by the raw `/connect/api/data` endpoint.

The adapter exchanges the account email and All-Access Token at
`/connect/api/v1/access_token`, caches the returned JWT for less than its documented
10-minute lifetime, and refreshes automatically during long-running exports. A 401 from
the data API forces one immediate JWT refresh and retry.

## Run on dev-atlas

```bash
cd /home/aella/stellar-data-exporter
uv sync --extra dev
uv run uvicorn app.main:app --host 0.0.0.0 --port 8787
```

Health check:

```bash
curl http://127.0.0.1:8787/api/health
```

## Tests

```bash
uv run --extra dev pytest -q
node --check static/app.js
```

## Next implementation slices

1. live Stellar Cyber lab verification of auth behavior, dense slices, API limits, and long-running exports.
2. persistent export history without persisting source/destination credentials.
3. resumable remote-destination jobs and checkpoint metadata.
4. optional scheduled exports after the one-shot flow is validated.
5. production hardening: reverse proxy, access boundary, rate limits, deployment/runbook.
