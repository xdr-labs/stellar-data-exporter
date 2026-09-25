# Stellar Data Exporter

A lightweight web UI for exporting Stellar Cyber query results as CSV or JSON.

## Current MVP

The first working slice is intentionally small:

- no application login or user database
- Stellar Cyber host + API token supplied per browser session
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
  -> host / token / index / DSL / time range
  -> FastAPI
  -> Stellar Cyber /connect/api/data/{index}/_search
  -> adaptive non-overlapping time slices
  -> CSV or JSON stream
  -> one-time browser download
```

The exporter injects the requested time range around the user's query. A slice is counted first.
If the slice exceeds the configured target record count, it is bisected and retried until a safe
slice is reached. Ranges use half-open boundaries `[start, end)`, avoiding overlap duplicates.

## Security boundary

- credentials are not persisted to disk or a database
- credentials are held only in process memory for request handling and one-time export jobs
- one-time download job identifiers expire after 10 minutes
- TLS verification is enabled by default
- there is currently no multi-user isolation layer; deploy this MVP only in a trusted environment
- never expose the service directly to the public Internet in its current development state

## Known API assumption

The current adapter treats the supplied Stellar credential as a bearer token and sends:

```http
Authorization: Bearer <token>
POST /connect/api/data/<index>/_search
```

This matches the All-Access Token path used for Stellar Cyber raw index queries. If a deployment
requires API-key-to-token exchange, that should be added as a separate authentication adapter.

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
