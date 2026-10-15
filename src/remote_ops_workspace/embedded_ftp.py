"""Authenticated pyftpdlib runner; credentials never appear in process argv."""
from __future__ import annotations

import argparse
import importlib
import ipaddress
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from . import command_safety as safe


def validate_ftp_environment(environment: Mapping[str, str]) -> tuple[str, str, bool, str, str]:
    username = environment.get("ROW_FTP_USERNAME", "")
    password = environment.get("ROW_FTP_PASSWORD", "")
    if not username or username.lower() == "anonymous" or not password:
        raise ValueError("FTP requires a non-anonymous ROW_FTP_USERNAME and ROW_FTP_PASSWORD")
    safe.clean_text(username, "FTP username")
    tls_required = environment.get("ROW_FTP_TLS_REQUIRED", "0") == "1"
    certificate = environment.get("ROW_FTP_TLS_CERT", "")
    private_key = environment.get("ROW_FTP_TLS_KEY", "")
    if tls_required:
        if not certificate or not private_key:
            raise ValueError("FTPS requires ROW_FTP_TLS_CERT and ROW_FTP_TLS_KEY")
        if not Path(certificate).is_file() or not Path(private_key).is_file():
            raise ValueError("FTPS certificate and key must be existing files")
    return username, password, tls_required, certificate, private_key


def create_ftp_server(host: str, port: int, root: Path, *, environment: Mapping[str, str]) -> Any:
    """Bind one authenticated server, requiring TLS for control and data when enabled."""
    username, password, tls_required, certificate, private_key = validate_ftp_environment(environment)
    host = safe.host(host, "FTP bind host")
    try:
        public_bind = not ipaddress.ip_address(host).is_loopback
    except ValueError:
        public_bind = host.lower() != "localhost"
    if public_bind and not tls_required:
        raise ValueError("non-loopback FTP requires TLS on both control and data connections")
    port = safe.port(port, "FTP port")
    directory = root.resolve(strict=True)
    if not directory.is_dir():
        raise ValueError("FTP root must be a directory")
    authorizers = importlib.import_module("pyftpdlib.authorizers")
    handlers = importlib.import_module("pyftpdlib.handlers")
    servers = importlib.import_module("pyftpdlib.servers")
    authorizer = authorizers.DummyAuthorizer()
    permissions = "elradfmwMT" if environment.get("ROW_FTP_WRITE", "0") == "1" else "elr"
    authorizer.add_user(username, password, str(directory), perm=permissions)
    handler_type = handlers.TLS_FTPHandler if tls_required else handlers.FTPHandler
    # Each server receives its own handler class; tests or multiple instances
    # cannot mutate a global pyftpdlib handler's authorization state.
    attributes: dict[str, Any] = {"authorizer": authorizer, "banner": "Remote Ops Workspace authenticated FTP"}
    if tls_required:
        attributes.update(certfile=certificate, keyfile=private_key, tls_control_required=True, tls_data_required=True)
    handler: Any = type("RowFTPHandler", (handler_type,), attributes)
    if tls_required:
        openssl = importlib.import_module("OpenSSL.SSL")
        context = handler.get_ssl_context()
        context.set_min_proto_version(openssl.TLS1_2_VERSION)
        context.check_privatekey()
    server = servers.FTPServer((host, port), handler)
    server.max_cons = 32
    server.max_cons_per_ip = 8
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args(argv)
    environment = dict(os.environ)
    # Do not pass the secret through any processes this daemon might start.
    os.environ.pop("ROW_FTP_PASSWORD", None)
    server = create_ftp_server(args.host, args.port, args.root, environment=environment)
    try:
        server.serve_forever()
    finally:
        server.close_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
