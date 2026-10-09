"""Authored, unexecuted pure/mocked contracts; no live HTTP or installer.

Synthetic zero public-key bytes and signature stubs confer no publisher authority.
Transaction fixtures use isolated temporary files, a supplied mock lease and an
explicit synthetic private boundary. Neither metadata nor a mock is native ACL
qualification; the production Windows qualification flag remains false.
"""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from remote_ops_workspace import update_channel as channel
from remote_ops_workspace import update_staging as staging
from remote_ops_workspace import windows_private_storage as storage

NOW = datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc)
ASSETS = {"linux-x64.tar.gz": b"linux test asset", "windows-x64.zip": b"windows test asset"}


@pytest.fixture(autouse=True)
def no_actual_tls_or_transport(monkeypatch):
    """Native SSL context setup and a live opener are excluded from pure tests."""
    monkeypatch.setattr(channel.ssl, "create_default_context", lambda: SimpleNamespace(
        check_hostname=True, verify_mode=channel.ssl.CERT_REQUIRED, minimum_version=None))

    class RefusedOpener:
        def open(self, *_args, **_kwargs):
            pytest.fail("pure fixture reached an unmocked HTTP opener")

    monkeypatch.setattr(channel.urllib.request, "build_opener", lambda *_args: RefusedOpener())


def policy_data():
    return {"schema": channel.POLICY_SCHEMA, "enabled": True,
            "manifest_url": "https://publisher.invalid/manifest.json",
            "public_key": "ed25519:" + base64.b64encode(bytes(32)).decode(),
            "organization": "synthetic-test", "channel": "test-only", "selected_target": "linux-x64",
            "approved_targets": ["linux-x64", "windows-x64"],
            "allowed_origins": ["https://publisher.invalid", "https://assets.invalid"],
            "limits": {"manifest_bytes": 65536, "asset_bytes": 1024, "total_asset_bytes": 2048,
                       "asset_count": 4, "http_timeout_seconds": 2, "operation_timeout_seconds": 30,
                       "redirects": 1, "maximum_age_seconds": 86400, "future_skew_seconds": 0}}


def policy(data=None):
    return channel.UpdatePolicy(json.dumps(data if data is not None else policy_data()).encode())


def manifest_data():
    rows = []
    for (name, body), target in zip(ASSETS.items(), ("linux-x64", "windows-x64"), strict=True):
        rows.append({"target": target, "name": name, "file": name,
                     "url": "https://assets.invalid/" + name,
                     "size_bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()})
    return {"schema": channel.MOBA_PROFESSIONAL_UPDATE_MANIFEST_SCHEMA,
            "organization": "synthetic-test", "channel": "test-only", "version": "1.0.28",
            "generated_at": "2026-10-06T00:00:00Z", "update_url": "https://publisher.invalid/manifest.json",
            "artifacts": rows, "signature": {"algorithm": "ed25519", "value": "AA==", "payload_sha256": ""}}


def manifest_bytes(data=None):
    data = manifest_data() if data is None else data
    data["signature"]["payload_sha256"] = hashlib.sha256(channel.canonical_update_manifest_payload(data)).hexdigest()
    return json.dumps(data, indent=1).encode()


@pytest.fixture
def accepted_signature(monkeypatch):
    calls = []

    def verify(algorithm, *, public_key, signature_value, payload, errors):
        calls.append((algorithm, public_key, signature_value, payload, errors.copy()))
        return True

    monkeypatch.setattr(channel, "_verify_update_manifest_signature", verify)
    return calls


def test_whole_original_signed_payload_and_both_targets_retained(accepted_signature):
    raw, config = manifest_bytes(), policy()
    result = channel.authenticate_manifest(raw, config, now=NOW)
    assert result.original == raw and {row.name for row in result.artifacts} == set(ASSETS)
    assert len(result.binding.artifacts) == 2
    assert accepted_signature == [("ed25519", config.settings["public_key"], "AA==",
                                   channel.canonical_update_manifest_payload(json.loads(raw)), [])]


@pytest.mark.parametrize(("field", "value"), [("organization", "other"), ("channel", "other"),
                                            ("update_url", "https://other.invalid/manifest.json")])
def test_identity_policy_refuses_manifest_override_before_signature(accepted_signature, field, value):
    data = manifest_data()
    data[field] = value
    with pytest.raises(channel.UpdateError, match="unapproved-update-identity"):
        channel.authenticate_manifest(manifest_bytes(data), policy(), now=NOW)
    assert accepted_signature == []


@pytest.mark.parametrize("version", ["1.0.27", "1.0.26", "1.0.028", "1.0.28-rc1", "1.0.28.0", 28])
def test_new_stage_requires_running_stable_newer_version(accepted_signature, version):
    data = manifest_data()
    data["version"] = version
    with pytest.raises(channel.UpdateError):
        channel.authenticate_manifest(manifest_bytes(data), policy(), now=NOW)


@pytest.mark.parametrize("stamp", ["2026-10-04T00:00:00Z", "2026-10-07T00:00:00Z",
                                 "2026-02-30T00:00:00Z", "2026-10-06T00:00:00+00:00"])
def test_time_policy_refuses_stale_future_invalid_or_non_utc_text(accepted_signature, stamp):
    data = manifest_data()
    data["generated_at"] = stamp
    with pytest.raises(channel.UpdateError):
        channel.authenticate_manifest(manifest_bytes(data), policy(), now=NOW)


@pytest.mark.parametrize(("field", "value"), [("file", "../escape"), ("size_bytes", 0), ("size_bytes", True),
                                            ("size_bytes", 1025), ("sha256", "a" * 63), ("name", "CON.zip"),
                                            ("url", "https://unapproved.invalid/file"), ("target", "unknown")])
def test_unsafe_or_unapproved_signed_artifact_refused(accepted_signature, field, value):
    data = manifest_data()
    data["artifacts"][0][field] = value
    if field == "name":
        data["artifacts"][0]["file"] = value
    with pytest.raises(channel.UpdateError):
        channel.authenticate_manifest(manifest_bytes(data), policy(), now=NOW)


@pytest.mark.parametrize("defect", ["alias", "selected-target-absent", "total", "metadata-only"])
def test_whole_set_cannot_skip_ambiguous_missing_or_overlimit_assets(accepted_signature, defect):
    data, config = manifest_data(), policy_data()
    if defect == "alias":
        data["artifacts"][1]["name"] = data["artifacts"][0]["name"].upper()
        data["artifacts"][1]["file"] = data["artifacts"][1]["name"]
    elif defect == "selected-target-absent":
        config["approved_targets"].append("macos-arm64")
        config["selected_target"] = "macos-arm64"
    elif defect == "total":
        config["limits"].update(asset_bytes=20, total_asset_bytes=20)
    else:
        del data["artifacts"][1]["file"]
    with pytest.raises(channel.UpdateError):
        channel.authenticate_manifest(manifest_bytes(data), policy(config), now=NOW)


def test_forged_signature_never_reaches_asset_origin_or_staging(monkeypatch):
    reached = []
    config = policy()
    real_approved = channel._approved_url
    monkeypatch.setattr(channel, "_verify_update_manifest_signature", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(channel, "_approved_url", lambda url, settings: reached.append(url) or real_approved(url, settings))
    with pytest.raises(channel.UpdateError, match="manifest-authentication-refused"):
        channel.authenticate_manifest(manifest_bytes(), config, now=NOW)
    assert reached == [policy_data()["manifest_url"]]


def test_payload_hash_mismatch_never_invokes_signature_backend(accepted_signature):
    data = json.loads(manifest_bytes())
    data["signature"]["payload_sha256"] = "0" * 64
    with pytest.raises(channel.UpdateError, match="manifest-authentication-refused"):
        channel.authenticate_manifest(json.dumps(data).encode(), policy(), now=NOW)
    assert accepted_signature == []


@pytest.mark.parametrize("raw", [b'{"enabled":true,"enabled":false}', b'{"value":NaN}',
                               b'{"value":Infinity}', b'{"value":' + b'9' * 5000 + b'}', b'\xff'])
def test_duplicate_nonstandard_utf8_and_integer_limits_have_fixed_refusal(raw):
    with pytest.raises(channel.UpdateError, match="ambiguous-json"):
        channel._decode(raw, 65536)


def test_disabled_template_cannot_confer_feed_or_publisher_authority():
    data = policy_data()
    data.update(enabled=False, public_key="", manifest_url="", allowed_origins=[])
    with pytest.raises(channel.UpdateError, match="update-policy-not-enabled"):
        policy(data)


@pytest.mark.parametrize("url", ["http://publisher.invalid/file", "https://u:p@publisher.invalid/file",
                               "https://publisher.invalid:0/file", "https://publisher.invalid/file#fragment",
                               "https://publisher.invalid\\private/file", "https://publisher.invalid/\nfile"])
def test_https_origin_refuses_credentials_cleartext_and_aliases(url):
    with pytest.raises(channel.UpdateError):
        channel._origin(url)


@contextmanager
def mock_lease(_path):
    yield


class SyntheticPrivateGuard:
    """Retained-object model for portable transaction fixtures, without a DLL.

    Real temporary-file identities bind the supplied descriptor to its direct
    name. This is deliberately an explicit test provider, with no SID/DACL
    conclusion and no substitution for the independently qualified provider.
    """

    def __init__(self, root):
        self.path = Path(staging.os.path.abspath(root))
        self.root_identity = self.identity(self.path.lstat())
        self.active, self.boundary_depth = True, 0
        self.named, self.writers, self.events = {}, set(), []
        self.verify()

    @staticmethod
    def identity(status):
        return status.st_dev, status.st_ino

    def verify(self):
        assert self.active, "synthetic root lease used after release"
        status = self.path.lstat()
        assert staging.stat.S_ISDIR(status.st_mode) and not staging._linked(status)
        assert self.identity(status) == self.root_identity
        self.events.append(("root-check",))

    def checked_file(self, path):
        self.verify()
        path = Path(path)
        assert path.parent == self.path, "synthetic child escapes retained root"
        status = path.lstat()
        assert staging.stat.S_ISREG(status.st_mode) and not staging._linked(status)
        assert status.st_nlink == 1
        return path, self.identity(status)

    @contextmanager
    def private_file(self, handle, path):
        path, identity = self.checked_file(path)
        assert type(handle) is int and handle >= 0
        assert self.identity(staging.os.fstat(handle)) == identity
        assert handle not in self.writers
        self.writers.add(handle)
        self.events.append(("descriptor-enter", path.name))
        try:
            yield SimpleNamespace(identity=identity)
        finally:
            # The R3 raw owner must outlive stream close and this post-check.
            assert self.identity(staging.os.fstat(handle)) == identity
            assert self.checked_file(path)[1] == identity
            self.writers.remove(handle)
            self.events.append(("descriptor-exit", path.name))

    @contextmanager
    def named_file(self, path, *, expected_identity=None):
        path, identity = self.checked_file(path)
        assert expected_identity is None or expected_identity == identity
        self.named[path.name] = self.named.get(path.name, 0) + 1
        self.events.append(("named-enter", path.name))
        try:
            yield SimpleNamespace(identity=identity)
        finally:
            assert self.checked_file(path)[1] == identity
            self.named[path.name] -= 1
            if not self.named[path.name]:
                del self.named[path.name]
            self.events.append(("named-exit", path.name))


@pytest.fixture
def private_boundary(monkeypatch):
    """Supply explicit boundaries only to the 13 changed compatibility tests."""
    guards = []

    def denied(*_args, **_kwargs):
        pytest.fail("compatibility fixture reached an unmocked native provider")

    def descriptor_handle(descriptor):
        assert type(descriptor) is int and descriptor >= 0
        return descriptor  # Synthetic identity only; never msvcrt.get_osfhandle.

    monkeypatch.setattr(storage, "_Native", denied)
    monkeypatch.setattr(storage, "descriptor_handle", descriptor_handle)

    def guard(root):
        value = SyntheticPrivateGuard(root)
        guards.append(value)
        return value

    def stage(root):
        value = guard(root)

        @contextmanager
        def boundary(selected, _home, *, recover=False):
            assert Path(staging.os.path.abspath(selected)) == value.path
            assert type(recover) is bool
            value.verify()
            value.boundary_depth += 1
            value.events.append(("boundary-enter", recover))
            try:
                yield value.path, value
            finally:
                value.verify()
                assert not value.named and not value.writers
                value.boundary_depth -= 1
                value.events.append(("boundary-exit", recover))
                value.active = False

        monkeypatch.setattr(channel, "_stage_boundary", boundary)
        return value

    yield SimpleNamespace(guard=guard, stage=stage)
    for value in guards:
        assert value.boundary_depth == 0 and not value.named and not value.writers
        value.active = False


def transaction(tmp_path, private_boundary):
    root, raw = tmp_path / "stage", b"opaque synthetic manifest"
    root.mkdir(mode=0o700)
    digest = hashlib.sha256(raw).hexdigest()
    binding = staging.AssetSetBinding(digest, tuple(staging.StageBinding(digest, name, hashlib.sha256(body).hexdigest(), len(body))
                                                    for name, body in ASSETS.items()))
    return staging.AssetSetTransaction(root, binding, exclusive_lease=mock_lease,
                                       private_guard=private_boundary.guard(root)), raw


def test_actual_set_transaction_stages_every_file_and_recovers_without_authority(tmp_path, private_boundary):
    operation, raw = transaction(tmp_path, private_boundary)
    result = operation.prepare(raw, {name: [body] for name, body in ASSETS.items()})
    assert result["artifact_count"] == 2 and not result["authenticity_checked"] and not result["install_permitted"]
    assert all((operation.root / name).read_bytes() == body for name, body in ASSETS.items())
    operation._publish_phase("receiving")
    assert operation.recover() == result
    assert json.loads((operation.root / staging.JOURNAL).read_bytes())["phase"] == "staged"


@pytest.mark.parametrize("mutation", ["tamper", "missing", "partial", "extra", "journal", "manifest"])
def test_recovery_refuses_any_asset_or_journal_change_and_retains_evidence(tmp_path, mutation, private_boundary):
    operation, raw = transaction(tmp_path, private_boundary)
    operation.prepare(raw, {name: [body] for name, body in ASSETS.items()})
    other = operation.root / "windows-x64.zip"
    if mutation == "tamper":
        other.write_bytes(b"X" * len(ASSETS[other.name]))
    elif mutation == "missing":
        other.unlink()
    elif mutation == "partial":
        (operation.root / ".windows-x64.zip.partial").write_bytes(b"partial")
    elif mutation == "extra":
        (operation.root / "unknown.bin").write_bytes(b"unknown")
    elif mutation == "journal":
        (operation.root / staging.JOURNAL).write_bytes(b'{"phase":"staged","phase":"receiving"}')
    else:
        (operation.root / staging.MANIFEST).write_bytes(b"changed")
    before = {p.name: p.read_bytes() for p in operation.root.iterdir()}
    with pytest.raises(staging.StagingError):
        operation.recover()
    assert {p.name: p.read_bytes() for p in operation.root.iterdir()} == before


def test_short_asset_retains_partial_and_receiving_journal(tmp_path, private_boundary):
    operation, raw = transaction(tmp_path, private_boundary)
    with pytest.raises(staging.StagingError, match="staged-byte-mismatch"):
        operation.prepare(raw, {name: [body[:-1]] for name, body in ASSETS.items()})
    assert json.loads((operation.root / staging.JOURNAL).read_bytes())["phase"] == "receiving"
    assert (operation.root / ".linux-x64.tar.gz.partial").exists()


def test_deadline_callback_applies_to_real_set_atomic_write_and_scan(tmp_path, private_boundary):
    operation, raw = transaction(tmp_path, private_boundary)
    ticks = []
    operation.checkpoint = lambda: ticks.append(True)
    operation.prepare(raw, {name: [body] for name, body in ASSETS.items()})
    assert len(ticks) >= 20

    def refused():
        raise channel.UpdateError("update-operation-deadline")

    operation.checkpoint = refused
    with pytest.raises(channel.UpdateError, match="update-operation-deadline"):
        operation.recover()


class Response:
    status = 200

    def __init__(self, chunks, headers=None):
        self.chunks, self.headers, self.closed = iter(chunks), headers or {}, False

    def read(self, _maximum):
        return next(self.chunks, b"")

    def close(self):
        self.closed = True


@pytest.mark.parametrize(("body", "headers"), [([b"long"], {}), ([b"x"], {}),
                                              ([b"abc"], {"Content-Length": "4"}),
                                              ([b"abc"], {"Content-Length": "bad"})])
def test_response_lengths_refuse_and_close(monkeypatch, body, headers):
    response = Response(body, headers)
    monkeypatch.setattr(channel, "_open_response", lambda *_args: response)
    with pytest.raises(channel.UpdateError, match="https-byte-bound"):
        list(channel._chunks("https://assets.invalid/test", policy_data(), float("inf"), 3, 3))
    assert response.closed


def test_abandoned_download_stream_closes_before_eof(monkeypatch):
    response = Response([b"a", b"b", b"c"])
    monkeypatch.setattr(channel, "_open_response", lambda *_args: response)
    stream = channel._chunks("https://assets.invalid/test", policy_data(), float("inf"), 3, 3)
    assert next(stream) == b"a"
    stream.close()
    assert response.closed


def test_unapproved_redirect_and_request_credentials_are_refused(monkeypatch):
    requests = []
    error = channel.urllib.error.HTTPError("https://publisher.invalid/manifest.json", 302, "private error",
                                           {"Location": "https://not-approved.invalid/private"}, None)

    class Opener:
        def open(self, request, *, timeout):
            requests.append((request, timeout))
            raise error

    monkeypatch.setattr(channel.urllib.request, "build_opener", lambda *_handlers: Opener())
    with pytest.raises(channel.UpdateError, match="unapproved-https-origin"):
        channel._open_response(policy_data()["manifest_url"], policy_data(), float("inf"))
    assert len(requests) == 1
    request, timeout = requests[0]
    assert timeout == 2 and request.data is None
    assert set(key.lower() for key in request.headers) == {"user-agent", "accept", "accept-encoding"}


def test_expired_deadline_never_invokes_opener_open(monkeypatch):
    class Opener:
        def open(self, *_args, **_kwargs):
            pytest.fail("expired deadline reached transport")

    monkeypatch.setattr(channel.urllib.request, "build_opener", lambda *_args: Opener())
    monkeypatch.setattr(channel.time, "monotonic", lambda: 10)
    with pytest.raises(channel.UpdateError, match="update-operation-deadline"):
        list(channel._chunks(policy_data()["manifest_url"], policy_data(), 9, 100))


def test_real_cross_process_lease_adapter_receives_exact_checked_budget(monkeypatch, accepted_signature, tmp_path):
    calls = []
    monkeypatch.setattr(channel, "exclusive_file_lock", lambda path, **kwargs: calls.append((path, kwargs)) or mock_lease(path))
    monkeypatch.setattr(channel.time, "monotonic", lambda: 5)
    manifest = channel.authenticate_manifest(manifest_bytes(), policy(), now=NOW)
    operation = channel._transaction(tmp_path, manifest, 20)
    with operation.exclusive_lease(tmp_path / staging.JOURNAL):
        pass
    assert calls == [(tmp_path / staging.JOURNAL, {"timeout_seconds": 15})]
    assert len(operation.binding.artifacts) == 2


def test_windows_stage_refused_before_network_or_mutation(monkeypatch, tmp_path):
    reached = []
    monkeypatch.setattr(channel, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(channel, "_chunks", lambda *_args: reached.append(True))
    with pytest.raises(channel.UpdateError, match="private-staging-platform-unqualified"):
        channel.stage_update(policy(), tmp_path, current_home=tmp_path / "home")
    assert reached == []


def test_full_validator_observes_original_manifest_and_all_assets(tmp_path, monkeypatch, accepted_signature, private_boundary):
    raw = manifest_bytes()
    manifest = channel.authenticate_manifest(raw, policy(), now=NOW)
    root = tmp_path / "stage"
    root.mkdir(mode=0o700)
    guard = private_boundary.guard(root)
    operation = staging.AssetSetTransaction(root, manifest.binding, exclusive_lease=mock_lease, private_guard=guard)
    operation.prepare(raw, {name: [body] for name, body in ASSETS.items()})
    observed = []

    def validate(path, **kwargs):
        assert set(guard.named) == {staging.JOURNAL, staging.MANIFEST, *ASSETS}
        observed.append((path.read_bytes(), {name: (kwargs["assets_dir"] / name).read_bytes() for name in ASSETS}, kwargs))
        return SimpleNamespace(passed=True)

    monkeypatch.setattr(channel, "validate_professional_update_manifest", validate)
    real_authenticate = channel.authenticate_manifest
    monkeypatch.setattr(channel, "authenticate_manifest", lambda body, config: real_authenticate(body, config, now=NOW))
    result = channel._verify_complete(operation, manifest, policy(), float("inf"))
    assert observed[0][:2] == (raw, ASSETS)
    assert observed[0][2]["public_key"] == policy_data()["public_key"]
    assert result["whole_declared_asset_set_verified"] and result["artifact_count"] == 2
    assert result["selected_files"] == ["linux-x64.tar.gz"] and not result["install_permitted"]
    assert result["authenticity_checked"] and not result["windows_acl_verified"] and result["readiness_credit"] == 0


def test_recovery_reauthenticates_current_policy_before_journal_trust(monkeypatch, tmp_path, private_boundary):
    reached = []
    guard = private_boundary.stage(tmp_path)

    def lease(path, *, timeout_seconds, _private_guard):
        assert _private_guard is guard and guard.boundary_depth == 1
        assert 0 < timeout_seconds <= 30
        return mock_lease(path)

    def read_manifest(_root, _maximum, selected):
        assert selected is guard and guard.boundary_depth == 1
        return manifest_bytes()

    monkeypatch.setattr(channel, "exclusive_file_lock", lease)
    monkeypatch.setattr(channel, "_read_stage_manifest", read_manifest)
    monkeypatch.setattr(channel, "_verify_update_manifest_signature", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(channel, "_transaction", lambda *_args: reached.append(True))
    with pytest.raises(channel.UpdateError, match="manifest-authentication-refused"):
        channel.recover_update(policy(), tmp_path, current_home=tmp_path / "home")
    assert reached == []


def test_stage_closes_all_owned_generators_after_atomic_refusal(monkeypatch, tmp_path, accepted_signature, private_boundary):
    closed, raw = [], manifest_bytes()
    real_authenticate = channel.authenticate_manifest
    monkeypatch.setattr(channel, "authenticate_manifest", lambda body, config: real_authenticate(body, config, now=NOW))
    guard = private_boundary.stage(tmp_path)

    def lease(path, *, timeout_seconds, _private_guard):
        assert _private_guard is guard and guard.boundary_depth == 1
        assert 0 < timeout_seconds <= 30
        return mock_lease(path)

    monkeypatch.setattr(channel, "exclusive_file_lock", lease)

    def chunks(url, *_args):
        try:
            yield raw if url.endswith("manifest.json") else ASSETS[url.rsplit("/", 1)[1]]
        finally:
            closed.append(url)

    class RefusingTransaction:
        def prepare(self, _original, streams):
            for stream in streams.values():
                next(stream)
            raise staging.StagingError("stage-byte-bound")

    monkeypatch.setattr(channel, "_chunks", chunks)
    def refusing_transaction(*_args, private_guard):
        assert private_guard is guard and guard.boundary_depth == 1
        return RefusingTransaction()

    monkeypatch.setattr(channel, "_transaction", refusing_transaction)
    with pytest.raises(channel.UpdateError, match="update-stage-refused"):
        channel.stage_update(policy(), tmp_path, current_home=tmp_path / "home")
    assert len(closed) == 3


def cli_functions():
    """Execute only actual parser/three new CLI functions under explicit mocks."""
    source = (Path(channel.__file__).parent / "cli.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    wanted = {"build_parser", "_customizer_authenticated_stage", "cmd_customizer_update_stage",
              "cmd_customizer_update_stage_recover"}
    definitions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    assert {node.name for node in definitions} == wanted
    names = {node.id for item in definitions for node in ast.walk(item)
             if isinstance(node, ast.Name) and node.id.startswith("cmd_")}
    namespace = {name: lambda _args: 0 for name in names}
    namespace.update(__package__="remote_ops_workspace", argparse=argparse, json=json,
                     Path=Path, __version__=channel.__version__,
                     DEFAULT_PLUGIN_CHECK_HOST="unrelated-parser-mock.invalid",
                     DEFAULT_PLUGIN_CHECK_USERNAME="unrelated-parser-mock",
                     REQUIRED_POLICY_SURFACES=("unrelated-parser-mock",),
                     SERVER_DEFAULT_PORTS={"unrelated-parser-mock": 1},
                     SUPPORTED_IMPORT_FORMATS=("unrelated-parser-mock",),
                     data_dir=lambda: Path("synthetic-row-home"))
    import sys

    namespace["sys"] = sys
    exec(compile(ast.Module(body=definitions, type_ignores=[]), "bound-cli-functions", "exec"), namespace)
    return namespace


@pytest.mark.parametrize("recover", [False, True])
def test_actual_new_cli_parser_and_handler_route_explicit_policy_without_install(monkeypatch, capsys, recover):
    namespace, calls = cli_functions(), []
    marker = object()
    monkeypatch.setattr(channel, "load_update_policy", lambda path: calls.append(("policy", path)) or marker)

    def operation(config, root, *, current_home):
        calls.append(("operation", config, root, current_home))
        return {"phase": "authenticated-staged", "version": "1.0.28", "artifact_count": 2, "install_permitted": False}

    monkeypatch.setattr(channel, "recover_update" if recover else "stage_update", operation)
    parser = namespace["build_parser"]()
    command = "update-stage-recover" if recover else "update-stage"
    args = parser.parse_args(["customizer", command, "--policy", "explicit-policy.json", "--stage", "private-stage", "--json"])
    assert args.func(args) == 0
    assert calls == [("policy", Path("explicit-policy.json")),
                     ("operation", marker, Path("private-stage"), Path("synthetic-row-home"))]
    assert json.loads(capsys.readouterr().out)["install_permitted"] is False


def test_actual_cli_input_error_does_not_print_secret_received_text(monkeypatch, capsys):
    namespace = cli_functions()

    def refuse(_path):
        raise ValueError("SECRET URL AND KEY CONTENT")

    monkeypatch.setattr(channel, "load_update_policy", refuse)
    args = SimpleNamespace(policy=Path("policy.json"), stage=Path("stage"), json=True)
    assert namespace["cmd_customizer_update_stage"](args) == 1
    output = capsys.readouterr()
    assert "SECRET" not in output.out + output.err
    assert json.loads(output.out) == {"phase": "refused", "refusal": "update-stage-input-refused", "install_permitted": False}


@pytest.mark.parametrize(("field", "value"), [("asset_count", True), ("asset_bytes", 1.0),
                                            ("redirects", 4), ("operation_timeout_seconds", 0)])
def test_policy_numeric_fields_require_plain_bounded_integers(field, value):
    data = policy_data()
    data["limits"][field] = value
    with pytest.raises(channel.UpdateError, match="invalid-trust-policy"):
        policy(data)


def test_backend_error_list_refuses_even_with_a_true_adapter_result(monkeypatch):
    def verify(*_args, errors, **_kwargs):
        errors.append("synthetic missing backend message")
        return True

    monkeypatch.setattr(channel, "_verify_update_manifest_signature", verify)
    with pytest.raises(channel.UpdateError, match="manifest-authentication-refused"):
        channel.authenticate_manifest(manifest_bytes(), policy(), now=NOW)


def test_real_stage_flow_keeps_both_targets_and_full_verification_inside_owned_lease(monkeypatch, tmp_path, accepted_signature, private_boundary):
    events, raw = [], manifest_bytes()
    held = [0]
    root = tmp_path / "stage"
    root.mkdir(mode=0o700)
    guard = private_boundary.stage(root)

    @contextmanager
    def lease(_path, *, timeout_seconds, _private_guard):
        assert _private_guard is guard and guard.boundary_depth == 1
        assert 0 < timeout_seconds <= 30
        events.append("lock-enter")
        held[0] += 1
        try:
            yield
        finally:
            held[0] -= 1
            events.append("lock-exit")

    def chunks(url, *_args):
        events.append("manifest" if url.endswith("manifest.json") else "asset")
        yield raw if url.endswith("manifest.json") else ASSETS[url.rsplit("/", 1)[1]]

    def validate(path, **_kwargs):
        assert path.read_bytes() == raw
        assert all((root / name).read_bytes() == body for name, body in ASSETS.items())
        assert held[0] == 1
        assert set(guard.named) == {staging.JOURNAL, staging.MANIFEST, *ASSETS}
        events.append("full-validator")
        return SimpleNamespace(passed=True)

    real_authenticate = channel.authenticate_manifest
    monkeypatch.setattr(channel, "authenticate_manifest", lambda body, config: real_authenticate(body, config, now=NOW))
    monkeypatch.setattr(channel, "exclusive_file_lock", lease)
    monkeypatch.setattr(channel, "_chunks", chunks)
    monkeypatch.setattr(channel, "validate_professional_update_manifest", validate)
    result = channel.stage_update(policy(), root, current_home=tmp_path / "home")
    assert result["artifact_count"] == 2 and result["whole_declared_asset_set_verified"]
    assert events[0] == "lock-enter" and events[-1] == "lock-exit"
    assert events.count("asset") == 2 and events.count("full-validator") == 1
    assert not result["install_permitted"]


def test_bad_complete_validator_result_never_permits_install(tmp_path, monkeypatch, accepted_signature, private_boundary):
    raw = manifest_bytes()
    manifest = channel.authenticate_manifest(raw, policy(), now=NOW)
    root = tmp_path / "stage"
    root.mkdir(mode=0o700)
    operation = staging.AssetSetTransaction(root, manifest.binding, exclusive_lease=mock_lease,
                                           private_guard=private_boundary.guard(root))
    operation.prepare(raw, {name: [body] for name, body in ASSETS.items()})
    monkeypatch.setattr(channel, "validate_professional_update_manifest", lambda *_args, **_kwargs: SimpleNamespace(passed=False))
    with pytest.raises(channel.UpdateError, match="staged-manifest-verification-refused"):
        channel._verify_complete(operation, manifest, policy(), float("inf"))


@pytest.mark.parametrize("encoding", ["gzip", "br"])
def test_encoded_response_refuses_and_closes_before_body(monkeypatch, encoding):
    response = Response([b"private"], {"Content-Encoding": encoding})
    monkeypatch.setattr(channel.urllib.request, "build_opener", lambda *_args: SimpleNamespace(open=lambda *_a, **_k: response))
    with pytest.raises(channel.UpdateError, match="https-response-refused"):
        list(channel._chunks(policy_data()["manifest_url"], policy_data(), float("inf"), 100))
    assert response.closed


def test_non_success_response_is_closed_without_reading_body(monkeypatch):
    response = Response([b"unpublished private message"])
    response.status = 403
    monkeypatch.setattr(channel.urllib.request, "build_opener", lambda *_args: SimpleNamespace(open=lambda *_a, **_k: response))
    with pytest.raises(channel.UpdateError, match="https-response-refused"):
        channel._open_response(policy_data()["manifest_url"], policy_data(), float("inf"))
    assert response.closed and next(response.chunks) == b"unpublished private message"


def test_approved_redirect_keeps_requests_credential_free_and_closes_old_response(monkeypatch):
    requests, handlers, closed = [], [], []
    response = Response([b"ok"])
    error = channel.urllib.error.HTTPError(policy_data()["manifest_url"], 302, "not public",
                                           {"Location": "https://assets.invalid/manifest.json"}, None)
    error.close = lambda: closed.append(True)

    class Opener:
        def open(self, request, **kwargs):
            requests.append((request, kwargs))
            if len(requests) == 1:
                raise error
            return response

    def build(*given):
        handlers.extend(given)
        return Opener()

    monkeypatch.setattr(channel.urllib.request, "build_opener", build)
    assert channel._open_response(policy_data()["manifest_url"], policy_data(), float("inf")) is response
    assert [request.full_url for request, _kwargs in requests] == [policy_data()["manifest_url"], "https://assets.invalid/manifest.json"]
    assert closed == [True]
    assert handlers[0].proxies == {} and handlers[1].redirect_request(None) is None
    assert all(set(key.lower() for key in request.headers) == {"user-agent", "accept", "accept-encoding"}
               and request.data is None for request, _kwargs in requests)


def test_redirect_limit_refuses_loop_and_closes_every_http_error(monkeypatch):
    calls, closed = [], []

    class Opener:
        def open(self, request, **_kwargs):
            calls.append(request.full_url)
            error = channel.urllib.error.HTTPError(request.full_url, 302, "not public", {"Location": request.full_url}, None)
            error.close = lambda: closed.append(True)
            raise error

    monkeypatch.setattr(channel.urllib.request, "build_opener", lambda *_args: Opener())
    with pytest.raises(channel.UpdateError, match="https-response-refused"):
        channel._open_response(policy_data()["manifest_url"], policy_data(), float("inf"))
    assert len(calls) == 2 and closed == [True, True]


@pytest.mark.parametrize(("hostname_check", "verify_mode"), [(False, channel.ssl.CERT_REQUIRED), (True, channel.ssl.CERT_NONE)])
def test_missing_certificate_or_hostname_verification_refuses_before_opener(monkeypatch, hostname_check, verify_mode):
    constructed = []
    monkeypatch.setattr(channel.ssl, "create_default_context", lambda: SimpleNamespace(
        check_hostname=hostname_check, verify_mode=verify_mode, minimum_version=None))
    monkeypatch.setattr(channel.urllib.request, "build_opener", lambda *_args: constructed.append(True))
    with pytest.raises(channel.UpdateError, match="tls-verification-required"):
        channel._open_response(policy_data()["manifest_url"], policy_data(), float("inf"))
    assert constructed == []


def test_transport_error_maps_fixed_code_without_received_url_or_message(monkeypatch):
    class Opener:
        def open(self, *_args, **_kwargs):
            raise channel.urllib.error.URLError("SECRET received URL and message")

    monkeypatch.setattr(channel.urllib.request, "build_opener", lambda *_args: Opener())
    with pytest.raises(channel.UpdateError) as found:
        channel._open_response(policy_data()["manifest_url"], policy_data(), float("inf"))
    assert str(found.value) == "https-transport-refused"


@pytest.mark.parametrize("body", [b"ab", b"abcd"])
def test_manifest_stream_must_match_declared_length_even_without_asset_size(monkeypatch, body):
    response = Response([body], {"Content-Length": "3"})
    monkeypatch.setattr(channel, "_open_response", lambda *_args: response)
    with pytest.raises(channel.UpdateError, match="https-byte-bound"):
        list(channel._chunks(policy_data()["manifest_url"], policy_data(), float("inf"), 100))
    assert response.closed


def test_read_error_closes_owned_response_and_maps_private_message(monkeypatch):
    class BrokenResponse(Response):
        def read(self, _maximum):
            raise OSError("SECRET transport detail")

    response = BrokenResponse([])
    monkeypatch.setattr(channel, "_open_response", lambda *_args: response)
    with pytest.raises(channel.UpdateError) as found:
        list(channel._chunks(policy_data()["manifest_url"], policy_data(), float("inf"), 100))
    assert str(found.value) == "https-transport-refused" and response.closed


def test_policy_regular_reader_rejects_hard_link_metadata_before_open(monkeypatch, tmp_path, private_boundary):
    path = tmp_path / "policy.json"
    path.write_bytes(json.dumps(policy_data()).encode())
    original = Path.lstat

    def lstat(selected):
        status = original(selected)
        if selected == path:
            return SimpleNamespace(st_mode=status.st_mode, st_file_attributes=0, st_nlink=2, st_size=status.st_size)
        return status

    monkeypatch.setattr(Path, "lstat", lstat)
    guard = private_boundary.guard(tmp_path)
    with pytest.raises(channel.UpdateError, match="unsafe-input-file"):
        channel._read_regular(path, channel.POLICY_BYTES, private_guard=guard)
    assert guard.events == [("root-check",)]  # No descriptor/name opened on unsafe metadata.


def test_wrong_asset_digest_keeps_partial_instead_of_publishing_success(tmp_path, private_boundary):
    operation, raw = transaction(tmp_path, private_boundary)
    bad = {name: [b"X" * len(body)] for name, body in ASSETS.items()}
    with pytest.raises(staging.StagingError, match="staged-byte-mismatch"):
        operation.prepare(raw, bad)
    assert (operation.root / ".linux-x64.tar.gz.partial").read_bytes() == bad["linux-x64.tar.gz"][0]
    assert json.loads((operation.root / staging.JOURNAL).read_bytes())["phase"] == "receiving"


def test_stage_io_failure_is_fixed_refusal_and_retains_all_existing_evidence(tmp_path, monkeypatch, private_boundary):
    operation, raw = transaction(tmp_path, private_boundary)

    def fail(*_args, **_kwargs):
        raise OSError("SECRET filesystem detail")

    monkeypatch.setattr(operation, "_atomic", fail)
    with pytest.raises(staging.StagingError) as found:
        operation.prepare(raw, {name: [body] for name, body in ASSETS.items()})
    assert str(found.value) == "stage-io-refused"
    assert list(operation.root.iterdir()) == []


def test_recovery_never_follows_asset_urls_and_keeps_outer_lease(tmp_path, monkeypatch, accepted_signature, private_boundary):
    raw, held = manifest_bytes(), [0]
    manifest = channel.authenticate_manifest(raw, policy(), now=NOW)
    root = tmp_path / "stage"
    root.mkdir(mode=0o700)
    staging.AssetSetTransaction(root, manifest.binding, exclusive_lease=mock_lease,
                               private_guard=private_boundary.guard(root)).prepare(raw, {name: [body] for name, body in ASSETS.items()})
    guard = private_boundary.stage(root)

    @contextmanager
    def lease(_path, *, timeout_seconds, _private_guard):
        assert _private_guard is guard and guard.boundary_depth == 1
        assert 0 < timeout_seconds <= 30
        held[0] += 1
        try:
            yield
        finally:
            held[0] -= 1

    def no_download(*_args, **_kwargs):
        pytest.fail("offline recovery reached network")

    def validate(*_args, **_kwargs):
        assert held[0] == 1
        assert set(guard.named) == {staging.JOURNAL, staging.MANIFEST, *ASSETS}
        return SimpleNamespace(passed=True)

    real_authenticate = channel.authenticate_manifest
    monkeypatch.setattr(channel, "authenticate_manifest", lambda body, config: real_authenticate(body, config, now=NOW))
    monkeypatch.setattr(channel, "exclusive_file_lock", lease)
    monkeypatch.setattr(channel, "_chunks", no_download)
    monkeypatch.setattr(channel, "validate_professional_update_manifest", validate)
    result = channel.recover_update(policy(), root, current_home=tmp_path / "home")
    assert result["artifact_count"] == 2 and not result["install_permitted"] and held == [0]
