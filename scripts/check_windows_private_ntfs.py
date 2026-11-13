"""Exercise private staging primitives on a disposable Windows NTFS runner."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
CANARY = b"ROW public Windows NTFS qualification canary\n"


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def require_delete_sharing(native, path: Path, *, blocked: bool, directory: bool = False) -> None:
    # An explicit DELETE open isolates the sharing check from rename semantics.
    flags = 0x02000000 if directory else 0
    handle = native.kernel.CreateFileW(str(path), 0x00010000, 0x07, None, 3, flags, None)
    if handle == native.c.c_void_p(-1).value:
        require(blocked and native.c.get_last_error() == 32, "unexpected-delete-open-error")
        return
    native.close(handle)
    require(not blocked, "delete-access-granted-with-held-handle")


def open_for_access(native, path: Path, access: int, *, denied: bool) -> None:
    handle = native.kernel.CreateFileW(str(path), access, 0x07, None, 3, 0, None)
    if handle == native.c.c_void_p(-1).value:
        require(denied and native.c.get_last_error() == 5, "unexpected-other-identity-open-error")
        return
    native.close(handle)
    require(not denied, "private-file-access-granted-to-other-identity")


def token_sid(native, token) -> bytes:
    c, w = native.c, native.w
    required = w.DWORD()
    size_probe = native.advapi.GetTokenInformation(token, 1, None, 0, c.byref(required))
    require(not size_probe and c.get_last_error() == 122 and c.sizeof(c.c_void_p) <= required.value <= 4096,
            "other-identity-token-size-invalid")
    info = c.create_string_buffer(required.value)
    require(bool(native.advapi.GetTokenInformation(token, 1, info, len(info), c.byref(required))),
            "other-identity-token-read-failed")
    pointer = c.cast(info, c.POINTER(c.c_void_p))[0]
    return native._copy_sid(pointer, c.addressof(info), c.addressof(info) + len(info))


@contextmanager
def other_identity(native, account: str, password: str):
    c, w = native.c, native.w
    api = native.advapi
    native._api(api, "LogonUserW", [w.LPCWSTR, w.LPCWSTR, w.LPCWSTR, w.DWORD, w.DWORD, c.POINTER(w.HANDLE)], w.BOOL)
    native._api(api, "ImpersonateLoggedOnUser", [w.HANDLE], w.BOOL)
    native._api(api, "RevertToSelf", [], w.BOOL)
    token = w.HANDLE()
    # Interactive logon authenticates locally and gives a primary token.
    require(bool(api.LogonUserW(account, ".", password, 2, 0, c.byref(token))), "other-identity-logon-failed")
    try:
        owner = native.token_user()
        sid = token_sid(native, token)
        require(sid != owner, "other-identity-matches-owner")
        required = w.DWORD()
        elevated = w.DWORD()
        require(bool(api.GetTokenInformation(token, 20, c.byref(elevated), c.sizeof(elevated), c.byref(required)))
                and elevated.value == 0, "other-identity-elevated")
        require(bool(api.ImpersonateLoggedOnUser(token)), "other-identity-impersonation-failed")
        try:
            thread_token = w.HANDLE()
            require(bool(api.OpenThreadToken(native.kernel.GetCurrentThread(), 0x0008, True, c.byref(thread_token))),
                    "other-identity-thread-token-missing")
            try:
                require(token_sid(native, thread_token) == sid, "other-identity-thread-token-mismatch")
            finally:
                native.close(thread_token)
            yield
        finally:
            if not api.RevertToSelf():
                # A failed revert must never let the remaining probe run.
                os._exit(125)
        require(native.token_user() == owner, "other-identity-revert-failed")
    finally:
        native.close(token)


def check_other_identity(native, private: Path, control: Path, account: str, password: str) -> None:
    # These opens exercise NTFS with the real logon token. No private bytes
    # are read or written. Keep sharing unrestricted to isolate the DACL check.
    with other_identity(native, account, password):
        for access in (0x80000000, 0x40000000, 0x00010000):
            open_for_access(native, control, access, denied=False)
            open_for_access(native, private, access, denied=True)


def observe_parent_refusal(storage, native, path: Path, report: dict) -> None:
    """Summarize the first refused ancestor without exposing its path or SIDs."""
    user = native.token_user()
    trusted = (user, storage.SYSTEM_SID, storage.ADMINISTRATORS_SID)
    rights = {
        "add-file": 0x2,
        "add-subdirectory": 0x4,
        "write-extended-attributes": 0x10,
        "delete-child": 0x40,
        "write-attributes": 0x100,
        "delete": 0x10000,
        "write-dacl": 0x40000,
        "write-owner": 0x80000,
        "generic-all": 0x10000000,
        "generic-write": 0x40000000,
    }
    for index, ancestor in enumerate(storage._ancestors(path)):
        handle = native.open_directory(ancestor)
        try:
            snapshot = native.snapshot(handle)
            try:
                storage._candidate_parent(snapshot, user, volume_root=index == 0)
            except storage.PrivateStorageError as exc:
                if exc.args not in (("untrusted-parent-write-access",), ("unqualified-parent-owner",)):
                    return
                owner_classes = {
                    storage.SYSTEM_SID: "system",
                    storage.ADMINISTRATORS_SID: "administrators",
                    storage.TRUSTED_INSTALLER_SID: "trusted-installer",
                    user: "current-user",
                }
                blocking = [
                    ace for ace in snapshot.aces
                    if ace.kind == 0 and not ace.flags & 0x08 and ace.sid not in trusted
                    and ace.mask & (storage.MUTATE & ~4)
                ]
                report["parent_refusal"] = {
                    "ancestor_index": index,
                    "reason": exc.args[0],
                    "owner": owner_classes.get(snapshot.owner, "other"),
                    "blocking_grants": len(blocking),
                    "inherited_blocking_grants": sum(bool(ace.flags & 0x10) for ace in blocking),
                    "blocking_rights": [
                        name for name, mask in rights.items()
                        if mask & (storage.MUTATE & ~4) and any(ace.mask & mask for ace in blocking)
                    ],
                }
                return
        finally:
            native.close(handle)


@contextmanager
def observe_refused_fixture(storage, native, parent: Path, report: dict):
    try:
        yield
    except storage.PrivateStorageError as exc:
        if exc.args in (("untrusted-parent-write-access",), ("unqualified-parent-owner",)):
            try:
                observe_parent_refusal(storage, native, parent, report)
            except (OSError, storage.PrivateStorageError):
                report["parent_observation"] = "unavailable"
        raise


@contextmanager
def private_fixture(storage, native, parent: Path, prefix: str):
    # Windows CPython's temporary-directory ACL includes an OWNER RIGHTS ACE.
    # Create the disposable parent with the same owner-only descriptor as a
    # private stage. Existing ancestors still pass the normal product guard.
    path = parent / f"{prefix}{uuid4().hex}"
    created = False
    try:
        with storage.private_stage_guard(path, create=True, _native=native):
            created = True
            yield path
    finally:
        if created:
            shutil.rmtree(path)


def qualify(parent: Path, observed: list[str], account: str, password: str, control: Path, report: dict) -> None:
    from remote_ops_workspace import windows_private_storage as storage

    native = storage._Native()
    user = native.token_user()
    observed.append("process-token")
    with (
        observe_refused_fixture(storage, native, parent, report),
        private_fixture(storage, native, parent, "row-private-ntfs-") as scratch,
    ):
        stage = scratch / "stage"
        partial = stage / "canary.part"
        final = stage / "canary.bin"
        alias = stage / "canary.link"
        with storage.private_stage_guard(stage, create=True, _native=native) as guard:
            observed.append("exclusive-private-directory")
            require_delete_sharing(native, stage, blocked=True, directory=True)
            with os.fdopen(guard.create_private_file(partial), "wb") as writer:
                handle = storage.descriptor_handle(writer.fileno())
                with guard.private_file(handle, partial) as written:
                    writer.write(CANARY)
                    writer.flush()
                    os.fsync(writer.fileno())
                observed.append("private-writer-bound-and-flushed")

            require_delete_sharing(native, partial, blocked=False)
            with guard.named_file(partial, expected_identity=written.identity):
                require_delete_sharing(native, partial, blocked=True)
            require_delete_sharing(native, partial, blocked=False)
            observed.append("retained-handle-denies-delete-open")

            partial.rename(final)
            with guard.named_file(final, expected_identity=written.identity):
                require(final.read_bytes() == CANARY, "staged-canary-differs")
            require(guard.verify_entries(maximum=2) == 1, "unexpected-stage-entry-count")
            observed.append("published-file-identity-and-bytes")
            check_other_identity(native, final, control, account, password)
            observed.append("other-identity-read-write-delete-denied")

            os.link(final, alias)
            try:
                try:
                    with guard.named_file(final):
                        raise ValueError("linked-file-accepted")
                except storage.PrivateStorageError as exc:
                    require(exc.args == ("linked-native-object",), "unexpected-linked-file-error")
                observed.append("linked-file-refused")
            finally:
                alias.unlink()

            with guard.named_file(final, expected_identity=written.identity):
                require(final.read_bytes() == CANARY, "canary-differs-after-unlink")
            final.unlink()
            require(guard.verify_entries(maximum=1) == 0, "stage-not-empty")
        require(native.token_user() == user, "process-token-changed")
        observed.append("token-unchanged-and-stage-clean")


def signed_fixture():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from remote_ops_workspace import __version__
    from remote_ops_workspace import update_channel as channel

    signer = Ed25519PrivateKey.generate()
    manifest_url = "https://publisher.invalid/manifest.json"
    organization = "windows-ntfs-fixture"
    update_channel = "ci-canary"
    target = "windows-x64"
    assets = {"canary.bin": CANARY, "second-canary.bin": b"ROW second canary\n"}
    version = __version__.split(".")
    version[-1] = str(int(version[-1]) + 1)
    manifest = {
        "schema": channel.MOBA_PROFESSIONAL_UPDATE_MANIFEST_SCHEMA,
        "organization": organization,
        "channel": update_channel,
        "version": ".".join(version),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "update_url": manifest_url,
        "artifacts": [
            {"target": target, "name": name, "file": name, "url": f"https://publisher.invalid/{name}",
             "sha256": hashlib.sha256(body).hexdigest(), "size_bytes": len(body)}
            for name, body in assets.items()
        ],
    }
    payload = channel.canonical_update_manifest_payload(manifest)
    manifest["signature"] = {
        "algorithm": "ed25519",
        "value": base64.b64encode(signer.sign(payload)).decode("ascii"),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
    }
    policy = {
        "schema": channel.POLICY_SCHEMA,
        "enabled": True,
        "manifest_url": manifest_url,
        "organization": organization,
        "channel": update_channel,
        "selected_target": target,
        "approved_targets": [target],
        "allowed_origins": ["https://publisher.invalid"],
        "limits": {
            "manifest_bytes": 8192, "asset_bytes": 1024, "total_asset_bytes": 2048,
            "asset_count": 2, "http_timeout_seconds": 2, "operation_timeout_seconds": 30,
            "redirects": 0, "maximum_age_seconds": 3600, "future_skew_seconds": 0,
        },
    }

    def trust(key):
        public_key = base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii")
        return channel.UpdatePolicy(json.dumps({**policy, "public_key": f"ed25519:{public_key}"}).encode("utf-8"))

    return json.dumps(manifest).encode("utf-8"), assets, trust(signer), trust(Ed25519PrivateKey.generate())


def qualify_staging(parent: Path, observed: list[str]) -> None:
    from remote_ops_workspace import update_channel as channel
    from remote_ops_workspace import update_staging as staging
    from remote_ops_workspace import windows_private_storage as storage
    from remote_ops_workspace.paths import data_dir
    from remote_ops_workspace.state_lock import exclusive_file_lock

    raw, assets, policy, wrong_policy = signed_fixture()
    manifest = channel.authenticate_manifest(raw, policy)
    try:
        channel.authenticate_manifest(raw, wrong_policy)
    except channel.UpdateError as exc:
        require(exc.args == ("manifest-authentication-refused",), "wrong-fixture-key-refusal")
    else:
        raise ValueError("wrong-fixture-key-accepted")
    observed.append("real-ed25519-accepted-and-wrong-key-refused")

    class SimulatedInterruption(Exception):
        pass

    class InterruptedTransaction(staging.AssetSetTransaction):
        def _publish_phase(self, phase):
            if phase == "staged":
                raise SimulatedInterruption
            super()._publish_phase(phase)

    def transaction(transaction_type, guard):
        def lease(path):
            return exclusive_file_lock(path, timeout_seconds=5, _private_guard=guard)
        return transaction_type(Path(guard.path), manifest.binding, exclusive_lease=lease, private_guard=guard)

    with private_fixture(storage, storage._Native(), parent, "row-stage-ntfs-") as scratch:
        root = scratch / "stage"
        require(not os.environ.get("ROW_HOME"), "unexpected-row-home-override")
        home = data_dir()
        with storage.windows_update_boundary(root, home, create=True) as guard:
            observed.append("default-home-and-stage-boundary")
            operation = transaction(InterruptedTransaction, guard)
            try:
                operation.prepare(raw, {name: [body] for name, body in assets.items()})
            except SimulatedInterruption:
                observed.append("staging-interrupted-before-commit")
            else:
                raise ValueError("expected-staging-interruption-missing")

        # Reacquire every native guard and the lock as a later invocation does.
        with storage.windows_update_boundary(root, home) as guard:
            operation = transaction(staging.AssetSetTransaction, guard)
            saved = channel._read_stage_manifest(root, policy.settings["limits"]["manifest_bytes"], guard)
            require(saved == raw, "staging-recovery-manifest-changed")
            recovered_manifest = channel.authenticate_manifest(saved, policy)
            recovered = operation.recover()
            require(recovered["phase"] == "staged" and recovered["transaction_id"] == recovered_manifest.binding.transaction_id,
                    "staging-recovery-binding-mismatch")
            result = channel._verify_complete(operation, recovered_manifest, policy, time.monotonic() + 30)
            require(result["authenticity_checked"] is True and result["artifact_count"] == len(assets),
                    "staging-complete-verifier-mismatch")
            require(result["install_permitted"] is False, "staging-install-unexpectedly-permitted")
            observed.append("signed-interrupted-stage-recovered")

            asset = root / next(iter(assets))
            with asset.open("r+b") as stream:
                stream.write(b"X")
                stream.flush()
                os.fsync(stream.fileno())
            try:
                operation.recover()
            except staging.StagingError as exc:
                require(exc.args == ("staged-byte-mismatch",), "unexpected-staging-refusal")
            else:
                raise ValueError("tampered-stage-recovered")
            observed.append("tampered-stage-refused")


def qualify_staging_entrypoints(parent: Path, observed: list[str]) -> None:
    from remote_ops_workspace import update_channel as channel
    from remote_ops_workspace import windows_private_storage as storage
    from remote_ops_workspace.paths import data_dir

    raw, assets, fixture_policy, _wrong_policy = signed_fixture()
    manifest_url = fixture_policy.settings["manifest_url"]
    bodies = {manifest_url: raw, **{f"https://publisher.invalid/{name}": body for name, body in assets.items()}}
    requested: list[str] = []

    def fixture_chunks(url, _settings, _deadline, maximum, expected=None):
        body = bodies[url]
        require(len(body) <= maximum and (expected is None or len(body) == expected),
                "entrypoint-fixture-length-mismatch")
        requested.append(url)
        yield body

    native = storage._Native()
    with private_fixture(storage, native, parent, "row-entrypoint-ntfs-") as scratch:
        policy_path = scratch / "policy.json"
        with storage.private_stage_guard(scratch, _native=native) as guard:
            with os.fdopen(guard.create_private_file(policy_path), "wb") as stream:
                stream.write(fixture_policy.document)
                stream.flush()
                os.fsync(stream.fileno())
        stage = scratch / "stage"
        with (
            patch.object(channel, "_WINDOWS_PRIVATE_STAGE_QUALIFIED", True),
            patch.object(channel, "_chunks", fixture_chunks),
        ):
            policy = channel.load_update_policy(policy_path)
            require(policy.digest == fixture_policy.digest, "entrypoint-policy-digest-mismatch")
            staged = channel.stage_update(policy, stage, current_home=data_dir())
            require(requested == list(bodies), "entrypoint-fixture-request-mismatch")
            recovered = channel.recover_update(policy, stage, current_home=data_dir())
            require(requested == list(bodies), "entrypoint-recovery-requested-network")
            require(
                staged == recovered
                and staged["phase"] == "authenticated-staged"
                and staged["artifact_count"] == len(assets)
                and staged["windows_dacl_metadata_verified"] is True
                and staged["install_permitted"] is False,
                "entrypoint-stage-recovery-mismatch",
            )
            for name, body in assets.items():
                require((stage / name).read_bytes() == body, "entrypoint-staged-bytes-mismatch")
    observed.append("windows-policy-stage-and-recovery-entrypoints")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "src"))
    observed: list[str] = []
    result = {"status": "failed", "observed": observed}
    try:
        require(os.name == "nt", "windows-required")
        account = os.environ.pop("ROW_NTFS_TEST_ACCOUNT")
        password = os.environ.pop("ROW_NTFS_TEST_PASSWORD")
        control = Path(os.environ.pop("ROW_NTFS_TEST_CONTROL"))
        from remote_ops_workspace import windows_private_storage as storage

        native = storage._Native()
        # Runner temp can be on a service-owned volume or under an untrusted
        # ancestor. Use the actual token's LocalAppData for the disposable stage.
        parent = Path(native.known_folder("local"))
        qualify(parent, observed, account, password, control, result)
        qualify_staging(parent, observed)
        qualify_staging_entrypoints(parent, observed)
    except (KeyError, OSError, RuntimeError, ValueError) as exc:
        # Report fixed check names or an OS error number only. Never emit paths,
        # tokens, descriptors, environment values or runner error text.
        code = exc.args[0] if len(exc.args) == 1 else None
        if isinstance(exc, ValueError) and isinstance(code, str) and code in FAILURE_CODES:
            result["reason"] = code
        else:
            winerror = getattr(exc, "winerror", None)
            result["reason"] = f"winerror-{winerror}" if type(winerror) is int else "unexpected-error"
    else:
        result["status"] = "passed"
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")
    print(json.dumps(result))
    return int(result["status"] != "passed")


FAILURE_CODES = frozenset({
    "windows-required", "local-fixed-volume-required", "persistent-local-acl-required",
    "entrypoint-fixture-length-mismatch", "entrypoint-policy-digest-mismatch",
    "entrypoint-fixture-request-mismatch", "entrypoint-recovery-requested-network",
    "entrypoint-stage-recovery-mismatch", "entrypoint-staged-bytes-mismatch",
    "private-staging-platform-unqualified", "windows-policy-input-refused",
    "windows-private-boundary-refused", "update-stage-refused", "update-stage-io-refused",
    "unexpected-row-home-override", "expected-staging-interruption-missing", "staging-recovery-binding-mismatch",
    "staging-install-unexpectedly-permitted", "unexpected-staging-refusal",
    "wrong-fixture-key-refusal", "wrong-fixture-key-accepted", "manifest-authentication-refused",
    "staging-recovery-manifest-changed", "staging-complete-verifier-mismatch",
    "tampered-stage-recovered", "stage-io-refused", "stage-changed",
    "incomplete-stage", "unexpected-stage-entry", "interrupted-partial-stage",
    "stage-must-be-outside-home", "default-home-selection-mismatch",
    "redirected-default-home-refused", "redirected-default-local-refused",
    "unexpected-other-identity-open-error", "private-file-access-granted-to-other-identity",
    "other-identity-logon-failed", "other-identity-token-size-invalid",
    "other-identity-token-read-failed", "other-identity-matches-owner", "other-identity-elevated",
    "other-identity-impersonation-failed", "other-identity-revert-failed",
    "other-identity-thread-token-missing", "other-identity-thread-token-mismatch",
    "native-private-storage-refused", "native-security-descriptor-refused",
    "native-directory-open-refused", "native-directory-missing", "native-file-open-refused",
    "native-private-file-create-refused",
    "unqualified-parent-owner", "untrusted-parent-write-access", "native-held-edge-refused",
    "missing-or-null-dacl", "linked-native-object", "private-owner-mismatch", "private-dacl-not-exact",
    "private-inheritance-not-exact", "private-writer-handle-mismatch", "native-private-boundary-changed",
    "private-file-boundary-changed", "private-final-identity-mismatch", "native-handle-cleanup-refused",
    "unexpected-delete-open-error", "delete-access-granted-with-held-handle", "staged-canary-differs",
    "unexpected-stage-entry-count", "linked-file-accepted", "unexpected-linked-file-error",
    "canary-differs-after-unlink", "stage-not-empty", "process-token-changed",
})


if __name__ == "__main__":
    raise SystemExit(main())
