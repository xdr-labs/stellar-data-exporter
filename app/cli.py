from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import ipaddress
import os
from pathlib import Path
import socket

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
import uvicorn

from . import __version__
from .paths import default_state_dir, ensure_private_directory


PACKAGE_DIR = Path(__file__).resolve().parent


def _env_true(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _local_tls_paths() -> tuple[Path, Path]:
    tls_dir = default_state_dir(PACKAGE_DIR) / "tls"
    return tls_dir / "local-server.key", tls_dir / "local-server.crt"


def _certificate_alt_names(host: str) -> list[x509.GeneralName]:
    names: list[x509.GeneralName] = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
        x509.IPAddress(ipaddress.ip_address("::1")),
    ]
    hostnames = {socket.gethostname(), socket.getfqdn()}
    for hostname in hostnames:
        hostname = hostname.strip()
        if hostname and hostname not in {"localhost", "localhost.localdomain"}:
            names.append(x509.DNSName(hostname))
        if not hostname:
            continue
        try:
            addresses = socket.getaddrinfo(hostname, None)
        except OSError:
            addresses = []
        for address_info in addresses:
            address_text = address_info[4][0]
            try:
                address = ipaddress.ip_address(address_text)
            except ValueError:
                continue
            if not address.is_unspecified:
                names.append(x509.IPAddress(address))

    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("192.0.2.1", 9))
            detected_ip = ipaddress.ip_address(probe.getsockname()[0])
            if not detected_ip.is_unspecified:
                names.append(x509.IPAddress(detected_ip))
        finally:
            probe.close()
    except OSError:
        pass

    candidate = host.strip()
    if candidate and candidate not in {"0.0.0.0", "::", "127.0.0.1", "localhost"}:
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            names.append(x509.DNSName(candidate))
        else:
            if not address.is_unspecified:
                names.append(x509.IPAddress(address))

    unique: list[x509.GeneralName] = []
    seen: set[tuple[str, str]] = set()
    for item in names:
        key = (type(item).__name__, str(item.value))
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def ensure_local_tls_certificate(host: str) -> tuple[str, str]:
    key_path, cert_path = _local_tls_paths()
    if key_path.is_file() and cert_path.is_file():
        return str(key_path), str(cert_path)

    ensure_private_directory(key_path.parent)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "Stellar Data Exporter Local")]
    )
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=825))
        .add_extension(
            x509.SubjectAlternativeName(_certificate_alt_names(host)),
            critical=False,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=None,
                decipher_only=None,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .sign(private_key, hashes.SHA256())
    )
    key_bytes = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    key_fd = os.open(
        key_path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600,
    )
    with os.fdopen(key_fd, "wb") as handle:
        handle.write(key_bytes)
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.chmod(0o600)
    cert_path.chmod(0o644)
    return str(key_path), str(cert_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stellar-data-exporter",
        description="Run the Stellar Data Exporter web service.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("STELLAR_EXPORTER_HOST", "0.0.0.0"),
        help="Listen address (default: 0.0.0.0; all IPv4 interfaces).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=os.environ.get("STELLAR_EXPORTER_PORT", "8787"),
        help="Listen port (default: 8787).",
    )
    parser.add_argument(
        "--ssl-keyfile",
        default=os.environ.get("STELLAR_EXPORTER_SSL_KEYFILE"),
        help="TLS private-key path. If omitted, a persistent local certificate is generated automatically.",
    )
    parser.add_argument(
        "--ssl-certfile",
        default=os.environ.get("STELLAR_EXPORTER_SSL_CERTFILE"),
        help="TLS certificate path. If omitted, a persistent local certificate is generated automatically.",
    )
    parser.add_argument(
        "--no-tls",
        action="store_true",
        default=_env_true("STELLAR_EXPORTER_TLS_DISABLED"),
        help="Disable HTTPS. Intended only for a loopback backend behind a TLS reverse proxy.",
    )
    parser.add_argument(
        "--proxy-headers",
        action="store_true",
        default=False,
        help="Trust proxy headers from explicitly allowed proxy addresses.",
    )
    parser.add_argument(
        "--forwarded-allow-ips",
        default=os.environ.get("STELLAR_EXPORTER_FORWARDED_ALLOW_IPS", "127.0.0.1"),
        help="Comma-separated proxy IPs trusted when --proxy-headers is enabled.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if bool(args.ssl_keyfile) != bool(args.ssl_certfile):
        parser.error("--ssl-keyfile and --ssl-certfile must be supplied together")
    if args.no_tls and (args.ssl_keyfile or args.ssl_certfile):
        parser.error("TLS cannot be disabled when explicit certificate files are supplied")

    ssl_keyfile = args.ssl_keyfile
    ssl_certfile = args.ssl_certfile
    if not args.no_tls and not ssl_keyfile:
        ssl_keyfile, ssl_certfile = ensure_local_tls_certificate(args.host)

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        ssl_keyfile=ssl_keyfile,
        ssl_certfile=ssl_certfile,
        proxy_headers=args.proxy_headers,
        forwarded_allow_ips=args.forwarded_allow_ips if args.proxy_headers else None,
    )


if __name__ == "__main__":
    main()
