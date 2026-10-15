"""Operator-configured authenticated staging. Never installs or changes ROW_HOME.

The complete original signed asset set is retained and checked. TLS deadlines
are checked around synchronous socket calls, not a preemptive DNS/process timer.
Private Windows staging remains refused pending genuine native qualification.
The guarded source path never infers qualification from mocks or operator input.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import ssl
import stat
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .moba_customizer import (
    MOBA_PROFESSIONAL_UPDATE_MANIFEST_SCHEMA,
    _validate_update_public_key,
    _verify_update_manifest_signature,
    canonical_update_manifest_payload,
    validate_professional_update_manifest,
)
from .state_lock import exclusive_file_lock
from .update_staging import (
    JOURNAL,
    MANIFEST,
    MAX_ARTIFACT_BYTES,
    MAX_ASSET_SET_BYTES,
    MAX_ASSETS,
    MAX_MANIFEST_BYTES,
    AssetSetBinding,
    AssetSetTransaction,
    StageBinding,
    StagingError,
)

POLICY_SCHEMA = "row.update-trust-policy.v1"
POLICY_BYTES = 16384
CHUNK_BYTES = 65536
VERSION = re.compile(r"(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})")
TARGET = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")

# Not configurable by policy/environment/CLI. Genuine disposable-host ABI,
# default-parent/writer/lock/recovery and independent identity denial are absent.
_WINDOWS_PRIVATE_STAGE_QUALIFIED = False


class UpdateError(ValueError):
    """Only a fixed public refusal code, never received text or URL."""


def _need(condition, code):
    if not condition:
        raise UpdateError(code)


def _exact(value, keys, code):
    _need(type(value) is dict and set(value) == set(keys), code)


def _integer(value, low, high, code):
    _need(type(value) is int and low <= value <= high, code)


def _text(value, maximum, code):
    _need(type(value) is str and 0 < len(value) <= maximum
          and not any(ord(char) < 32 or ord(char) == 127 for char in value), code)
    return value


def _pairs(items):
    value = {}
    for key, item in items:
        _need(key not in value, "ambiguous-json")
        value[key] = item
    return value


def _constant(_value):
    raise UpdateError("ambiguous-json")


def _decode(raw, maximum):
    _need(type(raw) is bytes and 0 < len(raw) <= maximum, "json-byte-bound")
    try:
        return json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=_pairs,
                          parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise UpdateError("ambiguous-json") from exc


def _origin(url):
    _text(url, 4096, "unsafe-https-url")
    _need(url.isascii() and not any(char.isspace() for char in url) and "\\" not in url, "unsafe-https-url")
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise UpdateError("unsafe-https-url") from exc
    _need(parsed.scheme == "https" and parsed.hostname and parsed.username is None
          and parsed.password is None and not parsed.fragment and (port is None or 1 <= port <= 65535), "unsafe-https-url")
    host = parsed.hostname.lower()
    _need(re.fullmatch(r"[a-z0-9.-]+", host) is not None and not host.startswith(".")
          and not host.endswith(".") and ".." not in host, "unsafe-https-url")
    return "https://" + host + (":" + str(port) if port not in (None, 443) else "")


def _approved_url(url, settings):
    _need(_origin(url) in settings["allowed_origins"], "unapproved-https-origin")
    return url


def _policy_data(raw):
    data = _decode(raw, POLICY_BYTES)
    _exact(data, {"schema", "enabled", "manifest_url", "public_key", "organization", "channel",
                  "selected_target", "approved_targets", "allowed_origins", "limits"}, "invalid-trust-policy")
    _need(data["schema"] == POLICY_SCHEMA and data["enabled"] is True, "update-policy-not-enabled")
    for key in ("organization", "channel"):
        _text(data[key], 128, "invalid-trust-policy")
    try:
        _validate_update_public_key(_text(data["public_key"], 128, "invalid-trust-key"))
    except ValueError as exc:
        raise UpdateError("invalid-trust-key") from exc
    targets = data["approved_targets"]
    _need(type(targets) is list and 1 <= len(targets) <= MAX_ASSETS
          and all(type(row) is str and TARGET.fullmatch(row) is not None for row in targets)
          and len(set(targets)) == len(targets), "invalid-trust-policy")
    _need(type(data["selected_target"]) is str and data["selected_target"] in targets, "invalid-trust-policy")
    origins = data["allowed_origins"]
    _need(type(origins) is list and 1 <= len(origins) <= 16, "invalid-trust-policy")
    for origin in origins:
        _need(type(origin) is str and origin == _origin(origin), "invalid-trust-policy")
        parsed = urllib.parse.urlsplit(origin)
        _need(not parsed.path and not parsed.query, "invalid-trust-policy")
    _need(len(set(origins)) == len(origins), "invalid-trust-policy")
    _approved_url(data["manifest_url"], data)
    limits = data["limits"]
    fields = {"manifest_bytes", "asset_bytes", "total_asset_bytes", "asset_count", "http_timeout_seconds",
              "operation_timeout_seconds", "redirects", "maximum_age_seconds", "future_skew_seconds"}
    _exact(limits, fields, "invalid-trust-policy")
    bounds = {"manifest_bytes": (1, MAX_MANIFEST_BYTES), "asset_bytes": (1, MAX_ARTIFACT_BYTES),
              "total_asset_bytes": (1, MAX_ASSET_SET_BYTES), "asset_count": (1, MAX_ASSETS),
              "http_timeout_seconds": (1, 30), "operation_timeout_seconds": (1, 900), "redirects": (0, 3),
              "maximum_age_seconds": (1, 31 * 86400), "future_skew_seconds": (0, 3600)}
    for key, (low, high) in bounds.items():
        _integer(limits[key], low, high, "invalid-trust-policy")
    _need(limits["asset_bytes"] <= limits["total_asset_bytes"]
          and limits["http_timeout_seconds"] <= limits["operation_timeout_seconds"], "invalid-trust-policy")
    return data


@dataclass(frozen=True)
class UpdatePolicy:
    """Trust is explicitly supplied by the operator, never by a manifest."""
    document: bytes

    def __post_init__(self):
        _policy_data(self.document)

    @property
    def settings(self):
        return _policy_data(self.document)

    @property
    def digest(self):
        return hashlib.sha256(self.document).hexdigest()


def _no_links(path):
    for component in (*reversed(path.parents), path):
        info = component.lstat()
        _need(not stat.S_ISLNK(info.st_mode)
              and not bool(getattr(info, "st_file_attributes", 0) & 0x400), "linked-input-path")


def _read_regular(path, maximum, private_guard=None):
    path = Path(os.path.abspath(path))
    _no_links(path)
    before = path.lstat()
    _need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 < before.st_size <= maximum, "unsafe-input-file")
    if os.name == "posix":
        _need(before.st_uid in (0, os.getuid()) and not (stat.S_IMODE(before.st_mode) & 0o022), "unsafe-input-file")
    with path.open("rb") as stream:
        from contextlib import nullcontext

        if private_guard is None:
            boundary = nullcontext()
        else:
            from .windows_private_storage import descriptor_handle

            boundary = private_guard.private_file(descriptor_handle(stream.fileno()), path)
        with boundary:
            opened = os.fstat(stream.fileno())
            def shared(row):
                return (row.st_dev, row.st_ino, row.st_size, row.st_mtime_ns)

            def identity(row):
                return (row.st_dev, row.st_ino, row.st_mode, row.st_size, row.st_nlink, row.st_mtime_ns, row.st_ctime_ns)
            _need(shared(opened) == shared(before), "input-file-changed")
            raw = stream.read(maximum + 1)
            after = os.fstat(stream.fileno())
    after_path = path.lstat()
    _need(len(raw) == before.st_size and identity(opened) == identity(after)
          and identity(before) == identity(after_path), "input-file-changed")
    return raw


def load_update_policy(path):
    # Until qualification exists, refuse before interpreting even the Windows
    # operator policy. No signer/feed/key authority is inferred from local paths.
    _need(os.name != "nt" or _WINDOWS_PRIVATE_STAGE_QUALIFIED is True,
          "private-staging-platform-unqualified")
    if os.name != "nt":
        return UpdatePolicy(_read_regular(path, POLICY_BYTES))
    from .windows_private_storage import PrivateStorageError, private_stage_guard

    selected = Path(os.path.abspath(path))
    try:
        # Require the exact private file policy too; a public key does not make
        # an attacker-writable trust-policy input safe. Never rewrite its ACL.
        with private_stage_guard(selected.parent) as guard:
            return UpdatePolicy(_read_regular(selected, POLICY_BYTES, private_guard=guard))
    except PrivateStorageError as exc:
        raise UpdateError("windows-policy-input-refused") from exc


def _private_stage(root, current_home):
    # Never infer a protected Windows DACL from chmod or operator assertions.
    _need(os.name == "posix", "private-staging-platform-unqualified")
    root = Path(os.path.abspath(root))
    home = Path(os.path.abspath(current_home))
    _need(root != home and not root.is_relative_to(home), "stage-must-be-outside-home")
    _no_links(root)
    # A first-use ROW_HOME can be absent. Its existing ancestors must be plain.
    for ancestor in reversed((home, *home.parents)):
        if ancestor.exists() or ancestor.is_symlink():
            _no_links(ancestor)
    info = root.lstat()
    _need(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
          and not stat.S_IMODE(info.st_mode) & 0o077, "private-stage-required")
    return root


def _release_version(value):
    _need(type(value) is str and VERSION.fullmatch(value) is not None, "invalid-release-version")
    return tuple(int(piece) for piece in value.split("."))


@dataclass(frozen=True)
class ManifestArtifact:
    target: str
    name: str
    url: str
    sha256: str
    size: int


@dataclass(frozen=True)
class AuthenticatedManifest:
    original: bytes
    version: str
    artifacts: tuple[ManifestArtifact, ...]

    @property
    def binding(self):
        digest = hashlib.sha256(self.original).hexdigest()
        return AssetSetBinding(digest, tuple(StageBinding(digest, row.name, row.sha256, row.size) for row in self.artifacts))


def authenticate_manifest(raw, policy, *, now=None):
    _need(type(policy) is UpdatePolicy, "invalid-trust-policy")
    settings = policy.settings
    data = _decode(raw, settings["limits"]["manifest_bytes"])
    _exact(data, {"schema", "channel", "organization", "version", "generated_at", "update_url", "artifacts", "signature"}, "invalid-stage-manifest")
    _need(data["schema"] == MOBA_PROFESSIONAL_UPDATE_MANIFEST_SCHEMA, "invalid-stage-manifest")
    _need(type(data["channel"]) is str and data["channel"] == settings["channel"]
          and type(data["organization"]) is str and data["organization"] == settings["organization"], "unapproved-update-identity")
    _need(data["update_url"] == settings["manifest_url"], "unapproved-update-identity")
    signature = data["signature"]
    _need(type(signature) is dict and {"algorithm", "value", "payload_sha256"}.issubset(signature)
          and set(signature).issubset({"algorithm", "value", "payload_sha256", "key_id"}), "invalid-stage-manifest")
    _need(signature["algorithm"] == "ed25519" and type(signature["value"]) is str
          and 0 < len(signature["value"]) <= 128 and type(signature["payload_sha256"]) is str
          and re.fullmatch(r"[0-9a-f]{64}", signature["payload_sha256"]) is not None, "invalid-stage-manifest")
    if "key_id" in signature:
        _text(signature["key_id"], 128, "invalid-stage-manifest")
    try:
        payload = canonical_update_manifest_payload(data)
    except (ValueError, RecursionError) as exc:
        raise UpdateError("invalid-stage-manifest") from exc
    _need(hashlib.sha256(payload).hexdigest() == signature["payload_sha256"], "manifest-authentication-refused")
    errors = []
    _need(_verify_update_manifest_signature("ed25519", public_key=settings["public_key"],
                                          signature_value=signature["value"], payload=payload, errors=errors)
          and not errors, "manifest-authentication-refused")
    _need(_release_version(data["version"]) > _release_version(__version__), "update-version-not-newer")
    stamp = data["generated_at"]
    _need(type(stamp) is str and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", stamp) is not None, "invalid-release-time")
    try:
        generated = datetime.fromisoformat(stamp[:-1] + "+00:00")
    except ValueError as exc:
        raise UpdateError("invalid-release-time") from exc
    now = now if now is not None else datetime.now(timezone.utc)
    _need(type(now) is datetime and now.tzinfo is not None, "invalid-release-time")
    age = (now - generated).total_seconds()
    _need(-settings["limits"]["future_skew_seconds"] <= age <= settings["limits"]["maximum_age_seconds"], "release-time-policy-refused")
    rows = data["artifacts"]
    _need(type(rows) is list and 1 <= len(rows) <= settings["limits"]["asset_count"], "invalid-stage-manifest")
    artifacts = []
    names, pairs = set(), set()
    total = 0
    for row in rows:
        _exact(row, {"target", "name", "url", "sha256", "size_bytes", "file"}, "invalid-stage-artifact")
        _need(type(row["target"]) is str and row["target"] in settings["approved_targets"], "unapproved-update-target")
        _need(type(row["file"]) is str and row["file"] == row["name"], "invalid-stage-artifact")
        _integer(row["size_bytes"], 1, settings["limits"]["asset_bytes"], "invalid-stage-artifact")
        try:
            bound = StageBinding(hashlib.sha256(raw).hexdigest(), row["name"], row["sha256"], row["size_bytes"])
        except StagingError as exc:
            raise UpdateError("invalid-stage-artifact") from exc
        _approved_url(row["url"], settings)
        folded = bound.artifact_name.casefold()
        pair = (row["target"], row["name"])
        _need(folded not in names and pair not in pairs, "ambiguous-stage-artifact")
        names.add(folded)
        pairs.add(pair)
        total += row["size_bytes"]
        _need(total <= settings["limits"]["total_asset_bytes"], "asset-set-byte-bound")
        artifacts.append(ManifestArtifact(row["target"], row["name"], row["url"], row["sha256"], row["size_bytes"]))
    _need(any(row.target == settings["selected_target"] for row in artifacts), "selected-target-absent")
    return AuthenticatedManifest(raw, data["version"], tuple(artifacts))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    _need(remaining > 0, "update-operation-deadline")
    return remaining


def _deadline(deadline):
    _remaining(deadline)


def _open_response(url, settings, deadline):
    _approved_url(url, settings)
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    _need(context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED, "tls-verification-required")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect(),
                                         urllib.request.HTTPSHandler(context=context))
    for redirects in range(settings["limits"]["redirects"] + 1):
        timeout = min(settings["limits"]["http_timeout_seconds"], _remaining(deadline))
        request = urllib.request.Request(url, headers={"User-Agent": "ROW-authenticated-staging",
                                                       "Accept": "application/octet-stream", "Accept-Encoding": "identity"})
        try:
            response = opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            status, location = exc.code, exc.headers.get("Location")
            exc.close()
            _need(status in (301, 302, 303, 307, 308) and redirects < settings["limits"]["redirects"]
                  and type(location) is str and 0 < len(location) <= 4096, "https-response-refused")
            url = _approved_url(urllib.parse.urljoin(url, location), settings)
            continue
        except (OSError, ValueError, urllib.error.URLError) as exc:
            raise UpdateError("https-transport-refused") from exc
        if response.status != 200 or response.headers.get("Content-Encoding", "identity") != "identity":
            response.close()
            raise UpdateError("https-response-refused")
        return response
    raise UpdateError("https-response-refused")


def _chunks(url, settings, deadline, maximum, expected=None):
    response = _open_response(url, settings, deadline)
    total = 0
    try:
        length = response.headers.get("Content-Length")
        declared = None
        if length is not None:
            _need(type(length) is str and re.fullmatch(r"0|[1-9][0-9]{0,9}", length) is not None, "https-byte-bound")
            _need(int(length) <= maximum and (expected is None or int(length) == expected), "https-byte-bound")
            declared = int(length)
        while True:
            _deadline(deadline)
            chunk = response.read(CHUNK_BYTES)
            _deadline(deadline)
            _need(type(chunk) is bytes, "https-byte-bound")
            if not chunk:
                break
            total += len(chunk)
            _need(len(chunk) <= CHUNK_BYTES and total <= maximum, "https-byte-bound")
            yield chunk
        _need(total > 0 and (expected is None or total == expected)
              and (declared is None or total == declared), "https-byte-bound")
    except (OSError, ValueError, urllib.error.URLError) as exc:
        if isinstance(exc, UpdateError):
            raise
        raise UpdateError("https-transport-refused") from exc
    finally:
        response.close()


@contextmanager
def _stage_boundary(root, current_home, *, recover=False):
    if os.name != "nt":
        yield _private_stage(root, current_home), None
        return
    _need(_WINDOWS_PRIVATE_STAGE_QUALIFIED is True, "private-staging-platform-unqualified")
    from .windows_private_storage import PrivateStorageError, windows_update_boundary

    try:
        with windows_update_boundary(root, current_home, create=not recover) as guard:
            yield Path(guard.path), guard
    except PrivateStorageError as exc:
        raise UpdateError("windows-private-boundary-refused") from exc


def _stage_lease(path, timeout, guard):
    if guard is None:
        return exclusive_file_lock(path, timeout_seconds=timeout)
    return exclusive_file_lock(path, timeout_seconds=timeout, _private_guard=guard)


def _read_stage_manifest(root, maximum, guard):
    if guard is None:
        return _read_regular(root / MANIFEST, maximum)
    # Read only after binding the actual descriptor to a retained private name.
    from .windows_private_storage import descriptor_handle

    path = root / MANIFEST
    before = path.lstat()
    _need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 < before.st_size <= maximum, "unsafe-input-file")
    with path.open("rb") as stream:
        with guard.private_file(descriptor_handle(stream.fileno()), path):
            opened = os.fstat(stream.fileno())
            def identity(row):
                return (row.st_dev, row.st_ino, row.st_size, row.st_mtime_ns)
            _need(identity(opened) == identity(before), "input-file-changed")
            raw = stream.read(maximum + 1)
            after = os.fstat(stream.fileno())
            _need(identity(after) == identity(opened), "input-file-changed")
    _need(len(raw) == before.st_size and identity(path.lstat()) == identity(before), "input-file-changed")
    return raw


def _transaction(root, manifest, deadline, private_guard=None):
    def lease(path):
        return _stage_lease(path, min(30, _remaining(deadline)), private_guard)
    return AssetSetTransaction(root, manifest.binding, exclusive_lease=lease,
                               checkpoint=lambda: _deadline(deadline), private_guard=private_guard)


def _verify_complete(transaction, manifest, policy, deadline):
    with transaction._verified_files():
        return _verify_complete_held(transaction, manifest, policy, deadline)


def _verify_complete_held(transaction, manifest, policy, deadline):
    _deadline(deadline)
    transaction._root()
    transaction._inventory()
    transaction._check_inputs()
    settings = policy.settings
    result = validate_professional_update_manifest(transaction.root / MANIFEST,
                                                  public_key=settings["public_key"], expected_channel=settings["channel"],
                                                  expected_organization=settings["organization"], assets_dir=transaction.root)
    _need(result.passed is True, "staged-manifest-verification-refused")
    observed = transaction._read(MANIFEST, settings["limits"]["manifest_bytes"])
    _need(observed == manifest.original, "staged-manifest-changed")
    authenticate_manifest(observed, policy)
    transaction._check_inputs()
    _deadline(deadline)
    return {"phase": "authenticated-staged", "manifest_sha256": manifest.binding.manifest_sha256,
            "trust_policy_sha256": policy.digest, "transaction_id": manifest.binding.transaction_id,
            "version": manifest.version, "selected_target": settings["selected_target"],
            "selected_files": [row.name for row in manifest.artifacts if row.target == settings["selected_target"]],
            "whole_declared_asset_set_verified": True, "artifact_count": len(manifest.artifacts),
            "artifact_total_bytes": sum(row.size for row in manifest.artifacts),
            "authenticity_checked": True, "install_permitted": False,
            "private_staging_metadata_verified": True, "windows_acl_verified": False,
            "windows_dacl_metadata_verified": transaction.private_guard is not None,
            "windows_other_identity_denial_qualified": False,
            "power_loss_or_hostile_host_safe": False, "readiness_credit": 0}


def stage_update(policy, stage_root, *, current_home):
    _need(type(policy) is UpdatePolicy, "invalid-trust-policy")
    settings = policy.settings
    deadline = time.monotonic() + settings["limits"]["operation_timeout_seconds"]
    try:
        with _stage_boundary(stage_root, current_home, recover=False) as (root, guard):
            with _stage_lease(root / JOURNAL, min(30, settings["limits"]["operation_timeout_seconds"]), guard):
                raw = b"".join(_chunks(settings["manifest_url"], settings, deadline, settings["limits"]["manifest_bytes"]))
                manifest = authenticate_manifest(raw, policy)
                transaction = (_transaction(root, manifest, deadline) if guard is None
                                   else _transaction(root, manifest, deadline, private_guard=guard))
                streams = {row.name: _chunks(row.url, settings, deadline, row.size, row.size) for row in manifest.artifacts}
                try:
                    transaction.prepare(manifest.original, streams)
                    return _verify_complete(transaction, manifest, policy, deadline)
                finally:
                    # A failed atomic write can stop iteration before HTTP EOF.
                    # Close every owned generator; partial files remain evidence.
                    for stream in streams.values():
                        stream.close()
    except StagingError as exc:
        raise UpdateError("update-stage-refused") from exc
    except OSError as exc:
        raise UpdateError("update-stage-io-refused") from exc


def recover_update(policy, stage_root, *, current_home):
    _need(type(policy) is UpdatePolicy, "invalid-trust-policy")
    settings = policy.settings
    deadline = time.monotonic() + settings["limits"]["operation_timeout_seconds"]
    try:
        with _stage_boundary(stage_root, current_home, recover=True) as (root, guard):
            with _stage_lease(root / JOURNAL, min(30, settings["limits"]["operation_timeout_seconds"]), guard):
                # Journal authenticity fields never authorize recovery. Reapply the
                # current operator policy and exact original signature from scratch.
                raw = _read_stage_manifest(root, settings["limits"]["manifest_bytes"], guard)
                manifest = authenticate_manifest(raw, policy)
                transaction = (_transaction(root, manifest, deadline) if guard is None
                                   else _transaction(root, manifest, deadline, private_guard=guard))
                transaction.recover()
                return _verify_complete(transaction, manifest, policy, deadline)
    except StagingError as exc:
        raise UpdateError("update-stage-refused") from exc
    except OSError as exc:
        raise UpdateError("update-stage-io-refused") from exc
