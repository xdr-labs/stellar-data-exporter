# Stellar Data Exporter — Production Operations

## Architecture

Production traffic must not connect directly to Uvicorn.

```text
User
  -> HTTPS 443
  -> Nginx
       - TLS 1.2/1.3
       - HTTP Basic authentication
       - per-client API rate limiting
       - security headers
  -> 127.0.0.1:8787
  -> Stellar Data Exporter
       - Stellar Cyber API
       - S3/SFTP destinations
       - /var/lib/stellar-data-exporter persistent state
```

The bundled systemd unit binds Uvicorn only to `127.0.0.1:8787`. Do not change that to
`0.0.0.0` on an Internet-reachable host.

## 1. Host prerequisites

Install Python 3.12+, Nginx, OpenSSL, and `uv`. Create a dedicated service account and
application directory:

```bash
sudo useradd --system --home /nonexistent --shell /usr/sbin/nologin stellar-exporter
sudo mkdir -p /opt/stellar-data-exporter /etc/stellar-data-exporter/tls
sudo chown -R stellar-exporter:stellar-exporter /opt/stellar-data-exporter
sudo chmod 0755 /opt/stellar-data-exporter
sudo chmod 0700 /etc/stellar-data-exporter
```

Deploy the repository under `/opt/stellar-data-exporter`, then install dependencies:

```bash
cd /opt/stellar-data-exporter
sudo -u stellar-exporter uv sync --frozen --extra dev
```

The runtime does not require the `dev` extras; omit `--extra dev` on a minimal production
host if tests are executed in CI/preflight instead.

## 2. TLS certificate

Install the certificate and private key:

```text
/etc/stellar-data-exporter/tls/fullchain.pem
/etc/stellar-data-exporter/tls/privkey.pem
```

Protect the private key:

```bash
sudo chown root:root /etc/stellar-data-exporter/tls/privkey.pem
sudo chmod 0600 /etc/stellar-data-exporter/tls/privkey.pem
```

Use a CA-issued certificate for the production hostname. The repository's `.tls` development
certificate is not a production certificate.

## 3. Access boundary

Create an Nginx Basic Auth file. The password must not be stored in this repository:

```bash
read -rsp 'Exporter password: ' EXPORTER_PASSWORD; echo
HASH="$(openssl passwd -6 "$EXPORTER_PASSWORD")"
unset EXPORTER_PASSWORD
printf 'exporter:%s\n' "$HASH" | sudo tee /etc/stellar-data-exporter/htpasswd >/dev/null
sudo chmod 0600 /etc/stellar-data-exporter/htpasswd
sudo chown root:www-data /etc/stellar-data-exporter/htpasswd
```

If the distribution provides the `htpasswd` utility, it may be used instead.

## 4. Nginx

Copy both Nginx files:

```bash
sudo cp deploy/nginx/00-stellar-data-exporter-rate-limit.conf /etc/nginx/conf.d/
sudo cp deploy/nginx/stellar-data-exporter.conf /etc/nginx/conf.d/
```

Replace `exporter.example.com` with the production hostname. Then validate and reload:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

The API rate limit is 10 requests/second per client with a burst of 30. This leaves headroom for
progress polling while limiting abusive request floods. Nginx returns HTTP 429 when the limit is
exceeded.

Only TCP 80/443 should be reachable from clients. TCP 8787 must remain loopback-only.

## 5. Persistent state and schedule encryption key

systemd creates `/var/lib/stellar-data-exporter` with mode `0700`. Runtime state is:

```text
/var/lib/stellar-data-exporter/export-jobs.sqlite3
/var/lib/stellar-data-exporter/export-schedules.sqlite3
/var/lib/stellar-data-exporter/schedule.key
```

The schedule database stores its executable export payload encrypted with Fernet. The generated
`schedule.key` is mode `0600`. Losing this key makes saved scheduled-export payloads
undecryptable.

For an externally managed key, copy `deploy/systemd/exporter.env.example` to
`/etc/stellar-data-exporter/exporter.env`, set `STELLAR_EXPORTER_SCHEDULE_KEY`, and keep the
file root-owned mode `0600`.

## 6. systemd service

Install and start:

```bash
sudo cp deploy/systemd/stellar-data-exporter.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now stellar-data-exporter
sudo systemctl status stellar-data-exporter
```

The unit applies a restrictive filesystem/device/kernel sandbox, clears Linux capabilities, uses
`UMask=0077`, and allows only UNIX/IPv4/IPv6 socket families required by the exporter.

## 7. Production smoke test

Validate the loopback service from the host:

```bash
curl --fail http://127.0.0.1:8787/api/health
```

Validate the authenticated public endpoint:

```bash
curl --fail --user exporter https://exporter.example.com/api/health
```

Then verify in the browser:

1. Basic and Advanced modes load.
2. Connection Test succeeds against the intended Stellar Cyber instance.
3. Preview succeeds for a narrow range.
4. A small browser export succeeds.
5. S3/SFTP destination test succeeds.
6. A small remote export succeeds.
7. Export History survives a service restart.
8. If schedules are enabled, create one paused schedule, Run now once, verify the remote object,
   restart the service, verify schedule state, then delete the test schedule.

## 8. Upgrade

Before changing code:

```bash
sudo systemctl stop stellar-data-exporter
sudo cp -a /var/lib/stellar-data-exporter /var/lib/stellar-data-exporter.backup
```

Deploy the new exact release, then:

```bash
cd /opt/stellar-data-exporter
sudo -u stellar-exporter uv sync --frozen
uv run --extra dev pytest -q
systemd-analyze verify deploy/systemd/stellar-data-exporter.service
sudo systemctl start stellar-data-exporter
curl --fail http://127.0.0.1:8787/api/health
sudo nginx -t
```

Keep the state backup until the browser smoke test passes.

## 9. Backup and restore

Back up the three files together while the service is stopped:

```bash
sudo systemctl stop stellar-data-exporter
sudo tar -C /var/lib -czf /secure-backup/stellar-data-exporter-state.tgz stellar-data-exporter
sudo systemctl start stellar-data-exporter
```

A restore must include the same `schedule.key` (or the same externally managed Fernet key) used
to encrypt the schedule database.

## 10. Incident checks

```bash
sudo journalctl -u stellar-data-exporter --since '30 min ago'
sudo journalctl -u nginx --since '30 min ago'
sudo ss -ltnp | grep -E ':443|:8787'
sudo systemctl status stellar-data-exporter nginx
```

Expected exposure:

- Nginx: public `:443` (and optionally `:80` only for HTTPS redirect).
- Uvicorn: `127.0.0.1:8787` only.

If the schedule key cannot decrypt saved schedules, disable/delete those schedules and recreate
them with the intended key; do not bypass encryption or copy plaintext credentials into the
history database.
