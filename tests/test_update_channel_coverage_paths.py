"""New validation and custody regressions; synthetic providers grant no native trust."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from io import BytesIO
from pathlib import PurePosixPath
from types import SimpleNamespace

import pytest

from remote_ops_workspace import update_channel as channel
from remote_ops_workspace import windows_private_storage as storage


def _policy_document():
    return {
        "schema": channel.POLICY_SCHEMA,
        "enabled": True,
        "manifest_url": "https://publisher.invalid/manifest.json",
        "public_key": "ed25519:" + base64.b64encode(bytes(32)).decode(),
        "organization": "coverage-fixture",
        "channel": "synthetic",
        "selected_target": "linux-x64",
        "approved_targets": ["linux-x64"],
        "allowed_origins": ["https://publisher.invalid"],
        "limits": {
            "manifest_bytes": 65536,
            "asset_bytes": 1024,
            "total_asset_bytes": 2048,
            "asset_count": 2,
            "http_timeout_seconds": 2,
            "operation_timeout_seconds": 30,
            "redirects": 1,
            "maximum_age_seconds": 86400,
            "future_skew_seconds": 0,
        },
    }


def _policy_bytes():
    return json.dumps(_policy_document()).encode()


@pytest.mark.parametrize("url", ["https://publisher.invalid:invalid/feed", "https://[broken/feed"])
def test_origin_parser_failures_expose_only_fixed_refusal(url):
    with pytest.raises(channel.UpdateError, match="^unsafe-https-url$"):
        channel._origin(url)


def test_invalid_operator_key_is_mapped_to_fixed_trust_key_refusal():
    document = _policy_document()
    document["public_key"] = "ed25519:not-valid-base64"
    with pytest.raises(channel.UpdateError, match="^invalid-trust-key$"):
        channel.UpdatePolicy(json.dumps(document).encode())


def _manifest_document():
    body = b"synthetic asset"
    return {
        "schema": channel.MOBA_PROFESSIONAL_UPDATE_MANIFEST_SCHEMA,
        "channel": "synthetic",
        "organization": "coverage-fixture",
        "version": "1.0.28",
        "generated_at": "2026-10-08T00:00:00Z",
        "update_url": "https://publisher.invalid/manifest.json",
        "artifacts": [{"target": "linux-x64", "name": "linux.tar.gz", "file": "linux.tar.gz",
                       "url": "https://publisher.invalid/linux.tar.gz", "size_bytes": len(body),
                       "sha256": hashlib.sha256(body).hexdigest()}],
        "signature": {"algorithm": "ed25519", "value": "AA==", "payload_sha256": "0" * 64},
    }


def test_optional_signature_key_id_is_validated_and_original_document_retained(monkeypatch):
    document = _manifest_document()
    document["signature"]["key_id"] = "synthetic-rotation-key"
    payload = channel.canonical_update_manifest_payload(document)
    document["signature"]["payload_sha256"] = hashlib.sha256(payload).hexdigest()
    raw = json.dumps(document).encode()
    observed = []

    def verify(algorithm, **kwargs):
        observed.append((algorithm, kwargs["payload"], kwargs["signature_value"]))
        return True

    monkeypatch.setattr(channel, "_verify_update_manifest_signature", verify)
    result = channel.authenticate_manifest(raw, channel.UpdatePolicy(_policy_bytes()),
                                           now=datetime(2026, 10, 8, tzinfo=timezone.utc))
    assert result.original == raw
    assert observed == [("ed25519", payload, "AA==")]
    assert result.artifacts[0].name == "linux.tar.gz"


@pytest.mark.parametrize("error_type", [ValueError, RecursionError])
def test_canonical_payload_failure_refuses_before_signature_backend(monkeypatch, error_type):
    calls = []

    def canonical(_document):
        raise error_type("private malformed-payload detail")

    monkeypatch.setattr(channel, "canonical_update_manifest_payload", canonical)
    monkeypatch.setattr(channel, "_verify_update_manifest_signature", lambda *_args, **_kwargs: calls.append(True))
    with pytest.raises(channel.UpdateError, match="^invalid-stage-manifest$"):
        channel.authenticate_manifest(json.dumps(_manifest_document()).encode(), channel.UpdatePolicy(_policy_bytes()))
    assert calls == []


def _status(**changes):
    values = {"st_dev": 1, "st_ino": 2, "st_mode": stat.S_IFREG | 0o600, "st_nlink": 1,
              "st_size": 6, "st_uid": 7, "st_mtime_ns": 10, "st_ctime_ns": 11}
    values.update(changes)
    return SimpleNamespace(**values)


def _reader(monkeypatch, *, defect=None):
    """A retained descriptor facade: no host paths, descriptors or native APIs."""
    events = []
    before, opened, after_fd, after_path = (_status() for _ in range(4))
    body = b"policy"
    if defect == "opened-inode":
        opened.st_ino += 1
    elif defect == "descriptor-mode":
        after_fd.st_mode = stat.S_IFREG | 0o400
    elif defect == "path-time":
        after_path.st_ctime_ns += 1
    elif defect == "short-read":
        body = b"pol"
    elif defect == "owner":
        before.st_uid = 8
    elif defect == "writable":
        before.st_mode = stat.S_IFREG | 0o622
    path_status, descriptor_status = iter((before, after_path)), iter((opened, after_fd))

    class Stream(BytesIO):
        def fileno(self):
            return 73

        def read(self, maximum=-1):
            events.append(("read", maximum))
            return super().read(maximum)

    stream = Stream(body)

    class File:
        def lstat(self):
            events.append(("lstat",))
            return next(path_status)

        def open(self, mode):
            assert mode == "rb"
            events.append(("open",))
            return stream

    selected = File()

    def fstat(descriptor):
        assert descriptor == 73
        events.append(("fstat", descriptor))
        return next(descriptor_status)

    monkeypatch.setattr(channel, "Path", lambda _path: selected)
    monkeypatch.setattr(channel, "_no_links", lambda path: events.append(("links", path)))
    monkeypatch.setattr(channel, "os", SimpleNamespace(name="posix", getuid=lambda: 7, fstat=fstat,
                                                      path=SimpleNamespace(abspath=lambda _path: "/safe/policy.json")))
    return selected, stream, events


@pytest.mark.parametrize("private", [False, True])
def test_regular_reader_binds_retained_descriptor_and_closes_before_return(monkeypatch, private):
    selected, stream, events = _reader(monkeypatch)

    class Guard:
        @contextmanager
        def private_file(self, handle, path):
            assert handle == "synthetic-handle" and path is selected
            events.append(("private-enter",))
            try:
                yield
            finally:
                events.append(("private-exit",))

    monkeypatch.setattr(storage, "descriptor_handle", lambda descriptor: "synthetic-handle" if descriptor == 73 else None)
    assert channel._read_regular("ignored-synthetic-input", 32, Guard() if private else None) == b"policy"
    assert stream.closed and events[0] == ("links", selected)
    assert ("read", 33) in events and events.count(("fstat", 73)) == 2
    assert (("private-enter",) in events) is private
    if private:
        assert events.index(("private-enter",)) < events.index(("fstat", 73)) < events.index(("private-exit",))


@pytest.mark.parametrize("defect", ["opened-inode", "descriptor-mode", "path-time", "short-read"])
def test_regular_reader_refuses_identity_or_length_change_and_closes(monkeypatch, defect):
    _selected, stream, _events = _reader(monkeypatch, defect=defect)
    with pytest.raises(channel.UpdateError, match="^input-file-changed$"):
        channel._read_regular("ignored-synthetic-input", 32)
    assert stream.closed


@pytest.mark.parametrize("defect", ["owner", "writable"])
def test_posix_policy_permissions_refuse_before_descriptor_open(monkeypatch, defect):
    _selected, stream, events = _reader(monkeypatch, defect=defect)
    with pytest.raises(channel.UpdateError, match="^unsafe-input-file$"):
        channel._read_regular("ignored-synthetic-input", 32)
    assert ("open",) not in events and not any(event[0] == "fstat" for event in events)
    stream.close()


def test_posix_policy_loader_validates_the_exact_reader_bytes(monkeypatch):
    raw, calls = _policy_bytes(), []
    monkeypatch.setattr(channel, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(channel, "_read_regular", lambda path, maximum: calls.append((path, maximum)) or raw)
    result = channel.load_update_policy("synthetic-policy")
    assert result.document == raw and calls == [("synthetic-policy", channel.POLICY_BYTES)]


def test_qualified_windows_policy_boundary_failure_has_fixed_code(monkeypatch, tmp_path):
    calls = []

    def refuse(parent):
        calls.append(parent)
        raise storage.PrivateStorageError("private native detail")

    monkeypatch.setattr(channel, "os", SimpleNamespace(name="nt", path=os.path))
    monkeypatch.setattr(channel, "_WINDOWS_PRIVATE_STAGE_QUALIFIED", True)
    monkeypatch.setattr(storage, "private_stage_guard", refuse)
    monkeypatch.setattr(channel, "_read_regular", lambda *_args, **_kwargs: pytest.fail("refused boundary read policy bytes"))
    with pytest.raises(channel.UpdateError, match="^windows-policy-input-refused$"):
        channel.load_update_policy(tmp_path / "policy.json")
    assert calls == [tmp_path]


@pytest.fixture
def private_tree(monkeypatch):
    state = {"mode": 0o700, "uid": 7, "present": {"/", "/private-stage"}, "stats": []}

    class SyntheticPath(PurePosixPath):
        def exists(self):
            return str(self) in state["present"]

        def is_symlink(self):
            return False

        def lstat(self):
            state["stats"].append(str(self))
            is_stage = str(self) == "/private-stage"
            return SimpleNamespace(st_mode=stat.S_IFDIR | (state["mode"] if is_stage else 0o755),
                                   st_uid=state["uid"] if is_stage else 0, st_file_attributes=0)

    monkeypatch.setattr(channel, "Path", SyntheticPath)
    monkeypatch.setattr(channel, "os", SimpleNamespace(name="posix", getuid=lambda: 7,
                                                      path=SimpleNamespace(abspath=lambda value: str(SyntheticPath(value)))))
    return state


@pytest.mark.parametrize("home_exists", [False, True])
def test_private_posix_stage_checks_existing_home_ancestors_without_creating_home(private_tree, home_exists):
    if home_exists:
        private_tree["present"].add("/home")
    assert str(channel._private_stage("/private-stage", "/home")) == "/private-stage"
    assert ("/home" in private_tree["stats"]) is home_exists
    assert private_tree["present"] == ({"/", "/private-stage", "/home"} if home_exists else {"/", "/private-stage"})


@pytest.mark.parametrize("field,value", [("mode", 0o750), ("uid", 8)])
def test_private_posix_stage_refuses_public_permissions_or_other_owner(private_tree, field, value):
    private_tree[field] = value
    with pytest.raises(channel.UpdateError, match="^private-stage-required$"):
        channel._private_stage("/private-stage", "/home")


@pytest.mark.parametrize("root", ["/home", "/home/inside"])
def test_private_stage_never_uses_current_home_or_its_descendants(private_tree, root):
    with pytest.raises(channel.UpdateError, match="^stage-must-be-outside-home$"):
        channel._private_stage(root, "/home")
    assert private_tree["stats"] == []


def test_nonwindows_boundary_yields_private_root_and_no_windows_guard(monkeypatch):
    marker, calls = object(), []
    monkeypatch.setattr(channel, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(channel, "_private_stage", lambda root, home: calls.append((root, home)) or marker)
    with channel._stage_boundary("stage", "home", recover=True) as result:
        assert result == (marker, None)
    assert calls == [("stage", "home")]


@pytest.mark.parametrize("recover", [False, True])
def test_qualified_windows_boundary_routes_creation_and_closes_guard(monkeypatch, tmp_path, recover):
    guard, calls = SimpleNamespace(path=str(tmp_path / "stage")), []

    @contextmanager
    def boundary(root, home, *, create):
        calls.append(("enter", root, home, create))
        try:
            yield guard
        finally:
            calls.append(("exit",))

    monkeypatch.setattr(channel, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(channel, "_WINDOWS_PRIVATE_STAGE_QUALIFIED", True)
    monkeypatch.setattr(storage, "windows_update_boundary", boundary)
    with channel._stage_boundary("selected-stage", "selected-home", recover=recover) as (root, observed):
        assert str(root) == guard.path and observed is guard
    assert calls == [("enter", "selected-stage", "selected-home", not recover), ("exit",)]


@pytest.mark.parametrize("fail_in_body", [False, True])
def test_qualified_windows_boundary_maps_enter_or_held_guard_refusal(monkeypatch, fail_in_body):
    closed = []

    @contextmanager
    def boundary(*_args, **_kwargs):
        if not fail_in_body:
            raise storage.PrivateStorageError("private enter detail")
        try:
            yield SimpleNamespace(path="synthetic-stage")
        finally:
            closed.append(True)

    monkeypatch.setattr(channel, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(channel, "_WINDOWS_PRIVATE_STAGE_QUALIFIED", True)
    monkeypatch.setattr(storage, "windows_update_boundary", boundary)
    with pytest.raises(channel.UpdateError, match="^windows-private-boundary-refused$"):
        with channel._stage_boundary("stage", "home"):
            raise storage.PrivateStorageError("private held guard detail")
    assert closed == ([True] if fail_in_body else [])


def test_unguarded_stage_manifest_read_retains_regular_reader_contract(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(channel, "_read_regular", lambda path, maximum: calls.append((path, maximum)) or b"original")
    assert channel._read_stage_manifest(tmp_path, 99, None) == b"original"
    assert calls == [(tmp_path / channel.MANIFEST, 99)]


def test_empty_redirect_budget_refuses_without_opening_network(monkeypatch):
    settings = _policy_document()
    settings["limits"]["redirects"] = -1
    calls = []
    monkeypatch.setattr(channel.ssl, "create_default_context", lambda: SimpleNamespace(
        check_hostname=True, verify_mode=channel.ssl.CERT_REQUIRED, minimum_version=None))
    monkeypatch.setattr(channel.urllib.request, "build_opener", lambda *_args: SimpleNamespace(
        open=lambda *_args, **_kwargs: calls.append(True)))
    with pytest.raises(channel.UpdateError, match="^https-response-refused$"):
        channel._open_response(settings["manifest_url"], settings, float("inf"))
    assert calls == []


@pytest.mark.parametrize("operation", ["stage_update", "recover_update"])
def test_stage_filesystem_failure_maps_fixed_code_before_transport(monkeypatch, operation):
    calls = []

    def boundary(root, home, *, recover):
        calls.append((root, home, recover))
        raise OSError("private filesystem detail")

    monkeypatch.setattr(channel, "_stage_boundary", boundary)
    monkeypatch.setattr(channel, "_chunks", lambda *_args: pytest.fail("filesystem refusal reached transport"))
    with pytest.raises(channel.UpdateError, match="^update-stage-io-refused$"):
        getattr(channel, operation)(channel.UpdatePolicy(_policy_bytes()), "stage", current_home="home")
    assert calls == [("stage", "home", operation == "recover_update")]


def test_recovery_transaction_refusal_maps_code_without_final_success(monkeypatch, tmp_path):
    events = []

    def recover():
        events.append("recover")
        raise channel.StagingError("private journal detail")

    monkeypatch.setattr(channel, "_stage_boundary", lambda *_args, **_kwargs: nullcontext((tmp_path, None)))
    monkeypatch.setattr(channel, "_stage_lease", lambda *_args: nullcontext())
    monkeypatch.setattr(channel, "_read_stage_manifest", lambda *_args: b"original signed bytes")
    monkeypatch.setattr(channel, "authenticate_manifest", lambda raw, _policy: SimpleNamespace(original=raw))
    monkeypatch.setattr(channel, "_transaction", lambda *_args: SimpleNamespace(recover=recover))
    monkeypatch.setattr(channel, "_verify_complete", lambda *_args: pytest.fail("refused journal published success"))
    with pytest.raises(channel.UpdateError, match="^update-stage-refused$"):
        channel.recover_update(channel.UpdatePolicy(_policy_bytes()), tmp_path, current_home="home")
    assert events == ["recover"]
