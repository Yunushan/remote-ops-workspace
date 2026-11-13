"""Exercise private staging primitives on a disposable Windows NTFS runner."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANARY = b"ROW public Windows NTFS qualification canary\n"


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def require_delete_sharing(native, path: Path, *, blocked: bool) -> None:
    # An explicit DELETE open isolates the sharing check from rename semantics.
    handle = native.kernel.CreateFileW(str(path), 0x00010000, 0x07, None, 3, 0, None)
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


def qualify(parent: Path, observed: list[str], account: str, password: str, control: Path) -> None:
    from remote_ops_workspace import windows_private_storage as storage

    native = storage._Native()
    user = native.token_user()
    observed.append("process-token")
    with tempfile.TemporaryDirectory(prefix="row-private-ntfs-", dir=parent) as scratch:
        stage = Path(scratch) / "stage"
        partial = stage / "canary.part"
        final = stage / "canary.bin"
        alias = stage / "canary.link"
        with storage.private_stage_guard(stage, create=True, _native=native) as guard:
            observed.append("exclusive-private-directory")
            with partial.open("xb") as writer:
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
        qualify(Path(os.environ["RUNNER_TEMP"]), observed, account, password, control)
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
    "unexpected-other-identity-open-error", "private-file-access-granted-to-other-identity",
    "other-identity-logon-failed", "other-identity-token-size-invalid",
    "other-identity-token-read-failed", "other-identity-matches-owner", "other-identity-elevated",
    "other-identity-impersonation-failed", "other-identity-revert-failed",
    "other-identity-thread-token-missing", "other-identity-thread-token-mismatch",
    "native-private-storage-refused", "native-security-descriptor-refused",
    "native-directory-open-refused", "native-directory-missing", "native-file-open-refused",
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
