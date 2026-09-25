from __future__ import annotations

import argparse
import os

import uvicorn

from . import __version__


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
        default=os.environ.get("STELLAR_EXPORTER_HOST", "127.0.0.1"),
        help="Listen address (default: 127.0.0.1).",
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
        help="Optional TLS private-key path.",
    )
    parser.add_argument(
        "--ssl-certfile",
        default=os.environ.get("STELLAR_EXPORTER_SSL_CERTFILE"),
        help="Optional TLS certificate path.",
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

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        ssl_keyfile=args.ssl_keyfile,
        ssl_certfile=args.ssl_certfile,
        proxy_headers=args.proxy_headers,
        forwarded_allow_ips=args.forwarded_allow_ips if args.proxy_headers else None,
    )


if __name__ == "__main__":
    main()
