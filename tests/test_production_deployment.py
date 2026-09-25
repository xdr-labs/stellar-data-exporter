from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def read(relative):
    return (ROOT / relative).read_text()


def test_systemd_service_is_loopback_only_and_hardened():
    unit = read("deploy/systemd/stellar-data-exporter.service")

    assert "--host 127.0.0.1" in unit
    assert "--host 0.0.0.0" not in unit
    assert "--forwarded-allow-ips=127.0.0.1" in unit
    assert "StateDirectory=stellar-data-exporter" in unit
    assert "StateDirectoryMode=0700" in unit
    assert "UMask=0077" in unit
    assert "NoNewPrivileges=true" in unit
    assert "ProtectSystem=strict" in unit
    assert "ProtectHome=true" in unit
    assert "PrivateDevices=true" in unit
    assert "RestrictNamespaces=true" in unit
    assert "RemoveIPC=true" in unit
    assert "SystemCallArchitectures=native" in unit
    assert "MemoryDenyWriteExecute=true" in unit
    assert "CapabilityBoundingSet=\n" in unit
    assert "AmbientCapabilities=\n" in unit


def test_nginx_enforces_tls_auth_rate_limit_and_loopback_proxy():
    rate = read("deploy/nginx/00-stellar-data-exporter-rate-limit.conf")
    site = read("deploy/nginx/stellar-data-exporter.conf")

    assert "limit_req_zone $binary_remote_addr" in rate
    assert "rate=10r/s" in rate

    assert "listen 443 ssl http2;" in site
    assert "ssl_protocols TLSv1.2 TLSv1.3;" in site
    assert 'auth_basic "Stellar Data Exporter";' in site
    assert "auth_basic_user_file /etc/stellar-data-exporter/htpasswd;" in site
    assert "limit_req zone=stellar_exporter_api burst=30 nodelay;" in site
    assert "limit_req_status 429;" in site
    assert site.count("proxy_pass http://127.0.0.1:8787;") == 2
    assert "proxy_pass http://0.0.0.0:8787;" not in site
    assert 'add_header Strict-Transport-Security "max-age=31536000" always;' in site
    assert 'add_header X-Frame-Options "DENY" always;' in site
    assert "proxy_buffering off;" in site


def test_web_assets_are_packaged_with_the_application():
    config = tomllib.loads(read("pyproject.toml"))
    package_data = config["tool"]["setuptools"]["package-data"]

    assert "static/*" in package_data["app"]
    for filename in ("index.html", "app.js", "styles.css", "stellar-cyber-logo.svg"):
        assert (ROOT / "app" / "static" / filename).is_file()


def test_production_runbook_preserves_encryption_key_and_private_backend():
    runbook = read("docs/PRODUCTION.md")

    assert "TCP 8787 must remain loopback-only" in runbook
    assert "schedule.key" in runbook
    assert "Losing this key" in runbook
    assert "same `schedule.key`" in runbook
    assert "nginx -t" in runbook
    assert "systemd-analyze verify" in runbook
