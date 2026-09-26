from pathlib import Path
import tomllib

from cryptography import x509
import pytest

from app import __version__, cli


ROOT = Path(__file__).resolve().parents[1]


def test_package_exposes_console_entry_point():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert config["project"]["scripts"]["stellar-data-exporter"] == "app.cli:main"


def test_cli_reports_package_version(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(["--version"])

    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"stellar-data-exporter {__version__}"


def test_cli_defaults_to_all_interfaces_and_safe_proxy_handling(monkeypatch):
    for name in (
        "STELLAR_EXPORTER_HOST",
        "STELLAR_EXPORTER_PORT",
        "STELLAR_EXPORTER_SSL_KEYFILE",
        "STELLAR_EXPORTER_SSL_CERTFILE",
        "STELLAR_EXPORTER_TLS_DISABLED",
        "STELLAR_EXPORTER_FORWARDED_ALLOW_IPS",
    ):
        monkeypatch.delenv(name, raising=False)

    args = cli.build_parser().parse_args([])

    assert args.host == "0.0.0.0"
    assert args.port == 8787
    assert args.proxy_headers is False
    assert args.forwarded_allow_ips == "127.0.0.1"
    assert args.ssl_keyfile is None
    assert args.ssl_certfile is None
    assert args.no_tls is False


def test_cli_honors_environment_defaults(monkeypatch):
    monkeypatch.setenv("STELLAR_EXPORTER_HOST", "0.0.0.0")
    monkeypatch.setenv("STELLAR_EXPORTER_PORT", "9443")
    monkeypatch.setenv("STELLAR_EXPORTER_FORWARDED_ALLOW_IPS", "10.0.0.10")

    args = cli.build_parser().parse_args([])

    assert args.host == "0.0.0.0"
    assert args.port == 9443
    assert args.forwarded_allow_ips == "10.0.0.10"


def test_cli_runs_uvicorn_with_explicit_proxy_boundary(monkeypatch):
    calls = []

    monkeypatch.setattr(cli.uvicorn, "run", lambda *args, **kwargs: calls.append((args, kwargs)))

    cli.main(
        [
            "--host",
            "127.0.0.1",
            "--port",
            "9000",
            "--proxy-headers",
            "--forwarded-allow-ips",
            "127.0.0.1",
            "--no-tls",
        ]
    )

    assert calls == [
        (
            ("app.main:app",),
            {
                "host": "127.0.0.1",
                "port": 9000,
                "ssl_keyfile": None,
                "ssl_certfile": None,
                "proxy_headers": True,
                "forwarded_allow_ips": "127.0.0.1",
            },
        )
    ]


def test_cli_requires_tls_key_and_certificate_as_pair():
    with pytest.raises(SystemExit):
        cli.main(["--ssl-keyfile", "/tmp/key.pem"])

    with pytest.raises(SystemExit):
        cli.main(["--ssl-certfile", "/tmp/cert.pem"])


def test_cli_enables_generated_https_on_all_interfaces_by_default(monkeypatch):
    calls = []
    generated_for = []
    generated = ("/tmp/generated-local.key", "/tmp/generated-local.crt")
    for name in ("STELLAR_EXPORTER_HOST", "STELLAR_EXPORTER_TLS_DISABLED"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        cli,
        "ensure_local_tls_certificate",
        lambda host: generated_for.append(host) or generated,
    )
    monkeypatch.setattr(cli.uvicorn, "run", lambda *args, **kwargs: calls.append((args, kwargs)))

    cli.main(["--port", "9443"])

    assert generated_for == ["0.0.0.0"]
    assert calls[0][1]["ssl_keyfile"] == generated[0]
    assert calls[0][1]["ssl_certfile"] == generated[1]
    assert calls[0][1]["host"] == "0.0.0.0"
    assert calls[0][1]["port"] == 9443


def test_cli_generates_persistent_local_certificate(tmp_path, monkeypatch):
    monkeypatch.setenv("STELLAR_EXPORTER_STATE_DIR", str(tmp_path))
    key_path, cert_path = cli.ensure_local_tls_certificate("127.0.0.1")
    key = Path(key_path)
    cert = Path(cert_path)
    assert key.is_file()
    assert cert.is_file()
    assert key.stat().st_mode & 0o777 == 0o600
    assert cert.stat().st_mode & 0o777 == 0o644

    parsed = x509.load_pem_x509_certificate(cert.read_bytes())
    sans = parsed.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert "localhost" in sans.get_values_for_type(x509.DNSName)
    assert "127.0.0.1" in {str(value) for value in sans.get_values_for_type(x509.IPAddress)}

    first_key = key.read_bytes()
    assert cli.ensure_local_tls_certificate("127.0.0.1") == (key_path, cert_path)
    assert key.read_bytes() == first_key


def test_cli_rejects_explicit_certificate_with_no_tls():
    with pytest.raises(SystemExit):
        cli.main(
            [
                "--no-tls",
                "--ssl-keyfile",
                "/tmp/key.pem",
                "--ssl-certfile",
                "/tmp/cert.pem",
            ]
        )


def test_all_interface_certificate_sans_include_detected_host_ip(monkeypatch):
    monkeypatch.setattr(cli.socket, "gethostname", lambda: "exporter-host")
    monkeypatch.setattr(cli.socket, "getfqdn", lambda: "exporter-host.local")
    monkeypatch.setattr(
        cli.socket,
        "getaddrinfo",
        lambda hostname, port: [
            (None, None, None, None, ("192.168.50.10", 0)),
        ],
    )

    names = cli._certificate_alt_names("0.0.0.0")
    addresses = {
        str(item.value)
        for item in names
        if isinstance(item, x509.IPAddress)
    }

    assert "127.0.0.1" in addresses
    assert "192.168.50.10" in addresses
