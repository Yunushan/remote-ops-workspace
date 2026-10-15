from __future__ import annotations

import runpy
import sys
from types import SimpleNamespace

import pytest

from remote_ops_workspace import embedded_ftp


@pytest.fixture
def ftp_modules(monkeypatch):
    class Authorizer:
        def __init__(self):
            self.users = []

        def add_user(self, username, password, root, *, perm):
            self.users.append((username, password, root, perm))

    class Handler:
        pass

    class TLSHandler:
        @classmethod
        def get_ssl_context(cls):
            return SimpleNamespace(set_min_proto_version=lambda _version: None, check_privatekey=lambda: None)

    class Server:
        def __init__(self, address, handler):
            self.address = address
            self.handler = handler
            self.closed = False
            self.served = False

        def serve_forever(self):
            self.served = True

        def close_all(self):
            self.closed = True

    modules = {
        "pyftpdlib.authorizers": SimpleNamespace(DummyAuthorizer=Authorizer),
        "pyftpdlib.handlers": SimpleNamespace(FTPHandler=Handler, TLS_FTPHandler=TLSHandler),
        "pyftpdlib.servers": SimpleNamespace(FTPServer=Server),
        "OpenSSL.SSL": SimpleNamespace(TLS1_2_VERSION=771),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    return modules


def environment(**updates):
    return {"ROW_FTP_USERNAME": "audit-user", "ROW_FTP_PASSWORD": "FAKE-UNIT-PASSWORD", **updates}


@pytest.mark.parametrize("settings", [{}, {"ROW_FTP_USERNAME": "anonymous", "ROW_FTP_PASSWORD": "x"}, {"ROW_FTP_USERNAME": "user"}, {"ROW_FTP_USERNAME": "bad\nuser", "ROW_FTP_PASSWORD": "x"}])
def test_auth_credentials_must_be_present_non_anonymous_and_valid(settings):
    with pytest.raises(ValueError):
        embedded_ftp.validate_ftp_environment(settings)


@pytest.mark.parametrize("certificate,key", [("", ""), ("missing-certificate", "missing-key"), ("exists", "missing-key")])
def test_required_tls_refuses_missing_certificate_or_private_key(tmp_path, certificate, key):
    present = tmp_path / "exists"
    present.write_bytes(b"fixture")
    certificate = str(present) if certificate == "exists" else certificate
    with pytest.raises(ValueError, match="FTPS"):
        embedded_ftp.validate_ftp_environment(environment(ROW_FTP_TLS_REQUIRED="1", ROW_FTP_TLS_CERT=certificate, ROW_FTP_TLS_KEY=key))


@pytest.mark.parametrize("host", ["0.0.0.0", "192.0.2.10", "public.example"])
def test_runner_itself_prevents_plaintext_public_ftp_even_without_planner(tmp_path, host):
    with pytest.raises(ValueError, match="TLS"):
        embedded_ftp.create_ftp_server(host, 2121, tmp_path, environment=environment())


def test_root_must_be_directory(tmp_path):
    target = tmp_path / "file"
    target.write_bytes(b"file")
    with pytest.raises(ValueError, match="directory"):
        embedded_ftp.create_ftp_server("127.0.0.1", 2121, target, environment=environment())


@pytest.mark.parametrize("host,write,tls", [("127.0.0.1", False, False), ("localhost", True, False), ("0.0.0.0", False, True)])
def test_exact_listener_authenticator_write_policy_and_both_tls_channels(tmp_path, ftp_modules, host, write, tls):
    cert, key = tmp_path / "cert", tmp_path / "key"
    cert.write_bytes(b"fixture-cert")
    key.write_bytes(b"fixture-key")
    settings = environment(ROW_FTP_WRITE="1" if write else "0", ROW_FTP_TLS_REQUIRED="1" if tls else "0", ROW_FTP_TLS_CERT=str(cert), ROW_FTP_TLS_KEY=str(key))
    server = embedded_ftp.create_ftp_server(host, 2121, tmp_path, environment=settings)
    assert server.address == (host, 2121)
    assert server.handler.authorizer.users == [("audit-user", "FAKE-UNIT-PASSWORD", str(tmp_path), "elradfmwMT" if write else "elr")]
    assert len(server.handler.authorizer.users) == 1
    assert server.max_cons == 32 and server.max_cons_per_ip == 8
    if tls:
        assert server.handler.tls_control_required is True
        assert server.handler.tls_data_required is True
        assert server.handler.certfile == str(cert) and server.handler.keyfile == str(key)


def test_each_server_authorizer_is_isolated(tmp_path, ftp_modules):
    first = embedded_ftp.create_ftp_server("127.0.0.1", 2121, tmp_path, environment=environment())
    second = embedded_ftp.create_ftp_server("127.0.0.1", 2122, tmp_path, environment=environment(ROW_FTP_USERNAME="second-user"))
    assert first.handler is not second.handler
    assert first.handler.authorizer.users[0][0] == "audit-user"


def test_main_removes_password_from_inherited_environment_and_closes_server(tmp_path, monkeypatch):
    monkeypatch.setenv("ROW_FTP_PASSWORD", "FAKE-UNIT-PASSWORD")
    server = SimpleNamespace(serve_forever=lambda: None, close_all=lambda: None)
    observed = []

    def create(host, port, root, *, environment):
        assert "ROW_FTP_PASSWORD" not in embedded_ftp.os.environ
        assert environment["ROW_FTP_PASSWORD"] == "FAKE-UNIT-PASSWORD"
        observed.append((host, port, root))
        return server

    monkeypatch.setattr(embedded_ftp, "create_ftp_server", create)
    assert embedded_ftp.main(["--host", "127.0.0.1", "--port", "2121", "--root", str(tmp_path)]) == 0
    assert observed == [("127.0.0.1", 2121, tmp_path)]


def test_module_entrypoint_runs_authenticated_server(tmp_path, monkeypatch, ftp_modules):
    monkeypatch.setenv("ROW_FTP_USERNAME", "audit-user")
    monkeypatch.setenv("ROW_FTP_PASSWORD", "FAKE-UNIT-PASSWORD")
    monkeypatch.setattr(sys, "argv", ["embedded_ftp", "--host", "127.0.0.1", "--port", "2121", "--root", str(tmp_path)])
    with pytest.warns(RuntimeWarning), pytest.raises(SystemExit) as exited:
        runpy.run_module("remote_ops_workspace.embedded_ftp", run_name="__main__")
    assert exited.value.code == 0
