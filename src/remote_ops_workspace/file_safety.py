from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

PRIVATE_FILE_MODE = stat.S_IRUSR | stat.S_IWUSR
PUBLIC_FILE_MODE = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH
PRIVATE_DIR_MODE = stat.S_IRWXU
SHARED_FILE_MODE = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP
SHARED_DIR_MODE = stat.S_ISGID | stat.S_IRWXU | stat.S_IRWXG


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    chmod_best_effort(path, PRIVATE_DIR_MODE)


def ensure_private_dir_required(path: Path) -> None:
    """Create a private directory and require the platform permission operation.

    POSIX mode bits provide the owner-only guarantee. Windows ``chmod`` does not
    prove the effective DACL, so Windows confidentiality additionally requires
    an operator-secured local workspace root as documented in SECURITY.md.
    """

    _require_no_linked_path_components(path)
    path.mkdir(parents=True, exist_ok=True)
    _require_no_linked_path_components(path)
    if not path.is_dir():
        raise OSError(f"private directory must be a directory: {path}")
    _chmod_required(path, PRIVATE_DIR_MODE)


def ensure_shared_dir(path: Path) -> None:
    """Require a POSIX group root or create a regular directory elsewhere.

    Without an explicitly configured GID, creating a ``0770`` directory would
    bind the store to the first writer's primary group. POSIX operators must
    therefore provision the root with group rwx and setgid inheritance.
    """

    if os.name == "posix":
        try:
            status = path.lstat()
        except FileNotFoundError as exc:
            raise OSError(
                "POSIX shared directory must be pre-provisioned with user/group "
                f"rwx and setgid permissions: {path}"
            ) from exc
    else:
        path.mkdir(parents=True, exist_ok=True)
        status = path.lstat()
    require_shared_dir_metadata(path, status)


def require_shared_dir_metadata(path: Path, status: os.stat_result) -> None:
    """Validate the stable ownership-inheritance boundary for shared files."""

    if stat.S_ISLNK(status.st_mode) or _is_reparse_point(status):
        raise OSError(f"shared directory must not be a symbolic link: {path}")
    if not stat.S_ISDIR(status.st_mode):
        raise OSError(f"shared directory must be a directory: {path}")
    if os.name == "posix":
        mode = stat.S_IMODE(status.st_mode)
        if mode & SHARED_DIR_MODE != SHARED_DIR_MODE or mode & stat.S_IRWXO:
            raise OSError(
                "POSIX shared directory must be user/group-rwx, setgid and not "
                f"world-accessible (for example 2770): {path}"
            )


def chmod_best_effort(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except OSError:
        pass


def _chmod_required(path: Path, mode: int) -> None:
    """Apply a security-sensitive POSIX mode or propagate the platform failure.

    Windows exposes only limited read-only handling through ``Path.chmod``; this
    call must not be treated as proof of an owner-only Windows DACL.
    """

    path.chmod(mode)


def write_json_atomic(
    path: Path,
    data: Any,
    *,
    private: bool = False,
    sort_keys: bool = True,
    indent: int = 2,
) -> None:
    payload = json.dumps(data, indent=indent, sort_keys=sort_keys) + "\n"
    write_text_atomic(path, payload, private=private)


def write_json_shared_atomic(
    path: Path,
    data: Any,
    *,
    sort_keys: bool = True,
    indent: int = 2,
) -> None:
    """Atomically replace a group-readable record without privatizing its root."""

    payload = (json.dumps(data, indent=indent, sort_keys=sort_keys) + "\n").encode("utf-8")
    _write_bytes_shared_atomic(path, payload)


def write_text_atomic(path: Path, text: str, *, private: bool = False) -> None:
    _write_bytes_atomic(path, text.encode("utf-8"), private=private)


def write_bytes_atomic(path: Path, payload: bytes, *, private: bool = False) -> None:
    _write_bytes_atomic(path, payload, private=private)


def append_jsonl_private(path: Path, record: Any) -> None:
    ensure_private_dir_required(path.parent)
    if _path_is_link_or_reparse(path):
        raise OSError(f"refusing to append to symlinked private artifact: {path}")
    payload = (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, PRIVATE_FILE_MODE)
    try:
        _require_open_path_identity(path, fd)
        if hasattr(os, "fchmod"):
            os.fchmod(fd, PRIVATE_FILE_MODE)
        else:
            _chmod_required(path, PRIVATE_FILE_MODE)
        written = os.write(fd, payload)
        if written != len(payload):
            raise OSError(f"short private audit append: wrote {written}/{len(payload)} bytes")
        os.fsync(fd)
    finally:
        os.close(fd)
    _chmod_required(path, PRIVATE_FILE_MODE)


def _write_bytes_atomic(path: Path, payload: bytes, *, private: bool) -> None:
    mode = PRIVATE_FILE_MODE if private else PUBLIC_FILE_MODE
    if private:
        ensure_private_dir_required(path.parent)
        # Never replace a caller-controlled link while recording private data.
        # ``os.replace`` itself replaces a link rather than following it, and
        # this explicit guard makes the rejected state observable to callers.
        if _path_is_link_or_reparse(path):
            raise OSError(f"refusing to replace symlinked private artifact: {path}")
    else:
        ensure_private_dir(path.parent)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    replaced = False
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if private:
            _chmod_required(temp_path, mode)
            _require_no_linked_path_components(path.parent)
            if _path_is_link_or_reparse(path):
                raise OSError(f"refusing to replace symlinked private artifact: {path}")
        else:
            chmod_best_effort(temp_path, mode)
        os.replace(temp_path, path)
        replaced = True
        if private:
            _chmod_required(path, mode)
        else:
            chmod_best_effort(path, mode)
    except Exception:
        if private and replaced:
            try:
                # Do not leave a potentially non-private final artifact behind
                # when the post-replace permission assertion failed.
                path.unlink()
            except OSError:
                pass
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise


def _write_bytes_shared_atomic(path: Path, payload: bytes) -> None:
    ensure_shared_dir(path.parent)
    parent_status = path.parent.stat(follow_symlinks=False)
    _require_replaceable_shared_target(path, parent_status=parent_status)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name == "posix":
            _chmod_required(temp_path, SHARED_FILE_MODE)
            require_shared_file_metadata(
                temp_path,
                temp_path.stat(follow_symlinks=False),
                parent_status,
            )
        current_parent = path.parent.stat(follow_symlinks=False)
        require_shared_dir_metadata(path.parent, current_parent)
        if (
            not stat.S_ISDIR(current_parent.st_mode)
            or _is_reparse_point(current_parent)
            or (current_parent.st_dev, current_parent.st_ino, current_parent.st_gid)
            != (parent_status.st_dev, parent_status.st_ino, parent_status.st_gid)
        ):
            raise OSError(f"shared directory changed while writing: {path.parent}")
        _require_replaceable_shared_target(path, parent_status=parent_status)
        os.replace(temp_path, path)
    except Exception:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise


def _require_replaceable_shared_target(
    path: Path,
    *,
    parent_status: os.stat_result | None = None,
) -> None:
    try:
        status = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(status.st_mode) or _is_reparse_point(status):
        raise OSError(f"refusing to replace symlinked shared artifact: {path}")
    if not stat.S_ISREG(status.st_mode):
        raise OSError(f"shared artifact must be a regular file: {path}")
    if parent_status is not None:
        require_shared_file_metadata(path, status, parent_status)


def require_shared_file_metadata(
    path: Path,
    status: os.stat_result,
    parent_status: os.stat_result,
) -> None:
    if os.name != "posix":
        return
    actual_mode = stat.S_IMODE(status.st_mode)
    if actual_mode != SHARED_FILE_MODE:
        raise OSError(
            f"shared artifact permissions must be {SHARED_FILE_MODE:04o}, "
            f"found {actual_mode:04o}: {path}"
        )
    if status.st_gid != parent_status.st_gid:
        raise OSError(
            "shared artifact group must match its setgid directory "
            f"({parent_status.st_gid}), found {status.st_gid}: {path}"
        )


def _require_no_linked_path_components(path: Path) -> None:
    """Reject symlink/reparse-point indirection in a private directory path.

    ``ROW_HOME`` is resolved by :func:`paths.data_dir` before reaching this
    boundary, so deliberate portable-home symlinks remain supported while
    caller-controlled intermediate links cannot redirect private writes.
    """

    absolute = Path(os.path.abspath(path))
    candidates = [absolute, *absolute.parents]
    for candidate in reversed(candidates):
        try:
            status = candidate.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(status.st_mode) or _is_reparse_point(status):
            raise OSError(f"refusing to use linked private directory ancestor: {candidate}")
        if candidate != absolute and not stat.S_ISDIR(status.st_mode):
            raise OSError(f"private directory ancestor must be a directory: {candidate}")


def _require_open_path_identity(path: Path, fd: int) -> None:
    """Ensure an opened private append target is still the named regular file."""

    named = path.stat(follow_symlinks=False)
    opened = os.fstat(fd)
    if stat.S_ISLNK(named.st_mode) or _is_reparse_point(named):
        raise OSError(f"refusing to append to symlinked private artifact: {path}")
    if not stat.S_ISREG(opened.st_mode):
        raise OSError(f"private append target must be a regular file: {path}")
    if (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino):
        raise OSError(f"private append target changed while opening: {path}")


def _is_reparse_point(path_status: os.stat_result) -> bool:
    attributes = getattr(path_status, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _path_is_link_or_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        status = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(status.st_mode) or _is_reparse_point(status)
