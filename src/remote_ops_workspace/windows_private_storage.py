"""Source proposal: retained Windows directory handles and exact owner DACLs.

No ctypes/DLL/security API is imported or called until the real native provider
is constructed. The updater integration is guarded by a false qualification gate.
Genuine Windows ABI, default-parent and other-identity denial remain unqualified.
"""
from __future__ import annotations

import hashlib
import ntpath
import os
import struct
from contextlib import contextmanager
from dataclasses import dataclass

FILE_ALL_ACCESS = 0x001F01FF
DACL_PRESENT = 0x0004
DACL_PROTECTED = 0x1000
DIRECTORY = 0x10
REPARSE = 0x400
MAX_ACES = 64
MAX_DESCRIPTOR = 65536
SYSTEM_SID = bytes.fromhex("010100000000000512000000")
ADMINISTRATORS_SID = bytes.fromhex("01020000000000052000000020020000")
MUTATE = 0x000D0156 | 0x50000000
KNOWN_MASK = FILE_ALL_ACCESS | 0xF0000000


class PrivateStorageError(ValueError):
    """Fixed refusal codes only; no SID, path, SDDL or received diagnostics."""


class PrivatePathMissing(PrivateStorageError):
    """An actual native open returned FILE/PATH_NOT_FOUND, not any other error."""


def _require(condition, code):
    if not condition:
        raise PrivateStorageError(code)


def _sid(value):
    _require(type(value) is bytes and 8 <= len(value) <= 68 and value[0] == 1
             and value[1] <= 15 and len(value) == 8 + value[1] * 4, "invalid-sid-shape")
    return value


@dataclass(frozen=True)
class Ace:
    kind: int
    flags: int
    mask: int
    sid: bytes


@dataclass(frozen=True)
class Snapshot:
    identity: tuple[int, int, int]
    attributes: int
    links: int
    owner: bytes
    control: int
    aces: tuple[Ace, ...]
    descriptor_sha256: str


def _validate(snapshot):
    _require(type(snapshot) is Snapshot and type(snapshot.identity) is tuple and len(snapshot.identity) == 3
             and all(type(value) is int and 0 <= value <= 0xFFFFFFFF for value in snapshot.identity), "invalid-object-identity")
    _require(type(snapshot.attributes) is int and 0 <= snapshot.attributes <= 0xFFFFFFFF and not snapshot.attributes & REPARSE
             and type(snapshot.links) is int and snapshot.links == 1, "linked-native-object")
    _sid(snapshot.owner)
    _require(type(snapshot.control) is int and 0 <= snapshot.control <= 65535
             and snapshot.control & DACL_PRESENT, "missing-or-null-dacl")
    _require(type(snapshot.aces) is tuple and 1 <= len(snapshot.aces) <= MAX_ACES, "missing-or-unbounded-dacl")
    _require(type(snapshot.descriptor_sha256) is str and len(snapshot.descriptor_sha256) == 64
             and all(char in "0123456789abcdef" for char in snapshot.descriptor_sha256), "invalid-descriptor-digest")
    for ace in snapshot.aces:
        _require(type(ace) is Ace and type(ace.kind) is int and ace.kind in (0, 1)
                 and type(ace.flags) is int and 0 <= ace.flags <= 0x1F
                 and type(ace.mask) is int and 0 <= ace.mask <= 0xFFFFFFFF
                 and not ace.mask & ~KNOWN_MASK, "unsupported-ace")
        _sid(ace.sid)


def require_parent(snapshot, user):
    """Conservative raw allow-mask refusal, not group/effective-access simulation."""
    _validate(snapshot)
    _sid(user)
    privileged = (user, SYSTEM_SID, ADMINISTRATORS_SID)
    _require(snapshot.attributes & DIRECTORY and snapshot.owner in privileged, "unqualified-parent-owner")
    for ace in snapshot.aces:
        # Inherit-only rights do not apply to this parent object. A deny never
        # makes an otherwise unsafe allow acceptable to this conservative gate.
        if ace.kind == 0 and not ace.flags & 0x08 and ace.sid not in privileged:
            _require(not ace.mask & MUTATE, "untrusted-parent-write-access")


def require_private(snapshot, user, *, directory):
    _validate(snapshot)
    _sid(user)
    _require(snapshot.owner == user, "private-owner-mismatch")
    _require(bool(snapshot.attributes & DIRECTORY) is directory, "private-kind-mismatch")
    _require(len(snapshot.aces) == 1, "private-dacl-not-exact")
    ace = snapshot.aces[0]
    _require(ace.kind == 0 and ace.sid == user and ace.mask == FILE_ALL_ACCESS, "private-dacl-not-exact")
    if directory:
        _require(snapshot.control & DACL_PROTECTED and ace.flags == 0x03, "private-inheritance-not-exact")
    else:
        # Empty newly opened files can inherit the sole owner grant. The parent
        # guard must remain held through verification and the plaintext write.
        _require(ace.flags in (0, 0x10), "private-inheritance-not-exact")


def _ancestors(path):
    raw = os.fspath(path)
    _require(type(raw) is str and 3 <= len(raw) <= 4096 and "\x00" not in raw, "unsafe-native-path")
    raw = raw.replace("/", "\\")
    drive, tail = ntpath.splitdrive(raw)
    _require(len(drive) == 2 and drive[0].isascii() and drive[0].isalpha() and drive[1] == ":"
             and tail.startswith("\\") and not raw.startswith("\\"), "local-absolute-path-required")
    parts = [part for part in tail.split("\\") if part]
    reserved = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
    _require(1 <= len(parts) <= 63 and all(part not in (".", "..") and not part.endswith((".", " "))
             and ":" not in part and not any(ord(char) < 32 for char in part)
             and part.split(".")[0].casefold() not in reserved for part in parts), "unsafe-native-path")
    paths = [drive.upper() + "\\"]
    for part in parts:
        paths.append(ntpath.join(paths[-1], part))
    return tuple(paths)


class _Native:
    """Actual Win32 API provider, source only until explicit genuine-host use."""

    def __init__(self):
        _require(os.name == "nt", "windows-required")
        import ctypes
        from ctypes import wintypes

        self.c, self.w = ctypes, wintypes
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        self.shell = ctypes.WinDLL("shell32", use_last_error=True)
        self.com = ctypes.WinDLL("ole32", use_last_error=True)
        p, d, b, h = ctypes.c_void_p, wintypes.DWORD, wintypes.BOOL, wintypes.HANDLE
        self._api(self.kernel, "GetCurrentProcess", [], h)
        self._api(self.kernel, "GetCurrentThread", [], h)
        self._api(self.kernel, "CloseHandle", [h], b)
        self._api(self.kernel, "LocalFree", [p], p)
        self._api(self.kernel, "GetDriveTypeW", [wintypes.LPCWSTR], wintypes.UINT)
        self._api(self.kernel, "CreateFileW", [wintypes.LPCWSTR, d, d, p, d, d, h], h)
        self._api(self.kernel, "CreateDirectoryW", [wintypes.LPCWSTR, p], b)
        self._api(self.kernel, "GetFileInformationByHandle", [h, p], b)
        self._api(self.kernel, "GetVolumeInformationByHandleW", [h, wintypes.LPWSTR, d, p, p, p, wintypes.LPWSTR, d], b)
        self._api(self.advapi, "OpenThreadToken", [h, d, b, ctypes.POINTER(h)], b)
        self._api(self.advapi, "OpenProcessToken", [h, d, ctypes.POINTER(h)], b)
        self._api(self.advapi, "GetTokenInformation", [h, ctypes.c_int, p, d, ctypes.POINTER(d)], b)
        self._api(self.advapi, "GetSecurityInfo", [h, ctypes.c_int, d, p, p, p, p, ctypes.POINTER(p)], d)
        self._api(self.advapi, "GetSecurityDescriptorLength", [p], d)
        self._api(self.advapi, "IsValidSecurityDescriptor", [p], b)
        self._api(self.advapi, "GetSecurityDescriptorControl", [p, p, p], b)
        self._api(self.advapi, "GetSecurityDescriptorOwner", [p, p, p], b)
        self._api(self.advapi, "GetSecurityDescriptorDacl", [p, p, p, p], b)
        self._api(self.advapi, "GetAclInformation", [p, p, d, ctypes.c_int], b)
        self._api(self.advapi, "GetAce", [p, d, p], b)
        self._api(self.advapi, "IsValidSid", [p], b)
        self._api(self.advapi, "GetLengthSid", [p], d)
        self._api(self.advapi, "InitializeAcl", [p, d, d], b)
        self._api(self.advapi, "AddAccessAllowedAceEx", [p, d, d, d, p], b)
        self._api(self.advapi, "InitializeSecurityDescriptor", [p, d], b)
        self._api(self.advapi, "SetSecurityDescriptorOwner", [p, p, b], b)
        self._api(self.advapi, "SetSecurityDescriptorDacl", [p, b, p, b], b)
        self._api(self.advapi, "SetSecurityDescriptorControl", [p, wintypes.WORD, wintypes.WORD], b)
        self._api(self.shell, "SHGetKnownFolderPath", [p, d, h, ctypes.POINTER(p)], wintypes.LONG)
        self._api(self.com, "CoTaskMemFree", [p], None)

    def _api(self, dll, name, arguments, result):
        function = getattr(dll, name)
        function.argtypes, function.restype = arguments, result

    def _ok(self, result):
        _require(bool(result), "native-private-storage-refused")

    def _copy_sid(self, pointer, low, high):
        address = self.c.cast(pointer, self.c.c_void_p).value
        _require(type(address) is int and low <= address and address + 8 <= high, "native-sid-out-of-bound")
        prefix = self.c.string_at(address, 8)
        size = 8 + prefix[1] * 4
        _require(prefix[0] == 1 and prefix[1] <= 15 and address + size <= high, "native-sid-out-of-bound")
        self._ok(self.advapi.IsValidSid(pointer))
        _require(self.advapi.GetLengthSid(pointer) == size, "native-sid-out-of-bound")
        return _sid(self.c.string_at(address, size))

    def token_user(self):
        c, w = self.c, self.w
        token = w.HANDLE()
        if self.advapi.OpenThreadToken(self.kernel.GetCurrentThread(), 0x0008, True, c.byref(token)):
            self.close(token)
            raise PrivateStorageError("impersonated-thread-refused")
        _require(c.get_last_error() == 1008, "native-token-scope-refused")
        self._ok(self.advapi.OpenProcessToken(self.kernel.GetCurrentProcess(), 0x0008, c.byref(token)))
        try:
            size = w.DWORD()
            result = self.advapi.GetTokenInformation(token, 1, None, 0, c.byref(size))
            _require(not result and c.get_last_error() == 122 and c.sizeof(c.c_void_p) + 4 <= size.value <= MAX_DESCRIPTOR,
                     "native-token-bound-refused")
            buffer = c.create_string_buffer(size.value)
            self._ok(self.advapi.GetTokenInformation(token, 1, buffer, size.value, c.byref(size)))
            pointer = c.cast(buffer, c.POINTER(c.c_void_p))[0]
            return self._copy_sid(pointer, c.addressof(buffer), c.addressof(buffer) + len(buffer))
        finally:
            self.close(token)

    def known_folder(self, role, *, default=False):
        """Observe current-token known folders without CREATE/INIT or env lookup.

        Bounded terminator walking relies on the native API's allocated,
        NUL-terminated PWSTR contract; no broader allocator-size proof is made.
        The allocation is freed even when HRESULT/path validation refuses.
        """
        _require(role in ("roaming", "local") and type(default) is bool, "unknown-native-folder-role")
        fields = ((0x3EB685DB, 0x65F9, 0x4CF6, 0xA0, 0x3A, 0xE3, 0xEF, 0x65, 0x72, 0x9F, 0x3D)
                  if role == "roaming" else
                  (0xF1B32785, 0x6FBA, 0x4FCF, 0x9D, 0x55, 0x7B, 0x8E, 0x7F, 0x15, 0x70, 0x91))
        c = self.c
        guid = c.create_string_buffer(struct.pack("<IHH8B", *fields), 16)
        pointer = c.c_void_p()
        user = self.token_user()
        try:
            # KF_FLAG_DONT_VERIFY; default adds KF_FLAG_DEFAULT_PATH. Neither
            # call creates a folder or applies shell initialization/settings.
            result = self.shell.SHGetKnownFolderPath(guid, 0x4000 | (0x0400 if default else 0),
                                                     None, c.byref(pointer))
            _require(result == 0 and pointer.value is not None, "native-known-folder-refused")
            chars = c.cast(pointer, c.POINTER(c.c_wchar))
            parts = []
            for index in range(4096):
                value = chars[index]
                if value == "\x00":
                    break
                parts.append(value)
            else:
                # Exact-bound strings still need the API-owned terminator.
                # This normal-exhaustion path is reachable; no tracing exclusion
                # or changed range provider is needed to exercise the boundary.
                _require(chars[4096] == "\x00", "native-known-folder-bound")
            path = "".join(parts)
            canonical = _ancestors(path)[-1]
            _require(path.replace("/", "\\") == canonical, "native-known-folder-alias-refused")
            _require(self.token_user() == user, "native-token-changed")
            return canonical
        finally:
            if pointer.value is not None:
                self.com.CoTaskMemFree(pointer)

    @contextmanager
    def directory_entries(self, path):
        """Enumerate direct names only, under the retained native root lease."""
        with os.scandir(path) as entries:
            yield (entry.path for entry in entries)

    def open_directory(self, path):
        _require(self.kernel.GetDriveTypeW(ntpath.splitdrive(path)[0] + "\\") == 3, "local-fixed-volume-required")
        handle = self.kernel.CreateFileW(path, 0x00020080, 0x03, None, 3, 0x02200000, None)
        if handle in (None, self.c.c_void_p(-1).value):
            if self.c.get_last_error() in (2, 3):
                raise PrivatePathMissing("native-directory-missing")
            raise PrivateStorageError("native-directory-open-refused")
        return handle

    def open_file(self, path):
        handle = self.kernel.CreateFileW(path, 0x00020080, 0x03, None, 3, 0x00200000, None)
        _require(handle not in (None, self.c.c_void_p(-1).value), "native-file-open-refused")
        return handle

    def close(self, handle):
        self._ok(self.kernel.CloseHandle(handle))

    def create_private_directory(self, path, user):
        c, w = self.c, self.w

        class Descriptor(c.Structure):
            _fields_ = [("revision", w.BYTE), ("reserved", w.BYTE), ("control", w.WORD),
                        ("owner", c.c_void_p), ("group", c.c_void_p), ("sacl", c.c_void_p), ("dacl", c.c_void_p)]

        class Attributes(c.Structure):
            _fields_ = [("length", w.DWORD), ("descriptor", c.c_void_p), ("inherit_handle", w.BOOL)]

        sid = c.create_string_buffer(_sid(user))
        acl = c.create_string_buffer(8 + 8 + len(user))
        self._ok(self.advapi.InitializeAcl(acl, len(acl), 2))
        self._ok(self.advapi.AddAccessAllowedAceEx(acl, 2, 0x03, FILE_ALL_ACCESS, sid))
        descriptor = Descriptor()
        self._ok(self.advapi.InitializeSecurityDescriptor(c.byref(descriptor), 1))
        self._ok(self.advapi.SetSecurityDescriptorOwner(c.byref(descriptor), sid, False))
        self._ok(self.advapi.SetSecurityDescriptorDacl(c.byref(descriptor), True, acl, False))
        self._ok(self.advapi.SetSecurityDescriptorControl(c.byref(descriptor), DACL_PROTECTED, DACL_PROTECTED))
        attributes = Attributes(c.sizeof(Attributes), c.addressof(descriptor), False)
        # Exclusive CreateDirectory failure (including already exists) refuses;
        # no existing root/parent owner or DACL is rewritten.
        self._ok(self.kernel.CreateDirectoryW(path, c.byref(attributes)))

    def _information(self, handle):
        c, w = self.c, self.w

        class FileInfo(c.Structure):
            _fields_ = [("attributes", w.DWORD), ("creation", w.FILETIME), ("access", w.FILETIME),
                        ("write", w.FILETIME), ("volume", w.DWORD), ("size_high", w.DWORD), ("size_low", w.DWORD),
                        ("links", w.DWORD), ("index_high", w.DWORD), ("index_low", w.DWORD)]

        info = FileInfo()
        self._ok(self.kernel.GetFileInformationByHandle(handle, c.byref(info)))
        return info

    def identity(self, handle):
        info = self._information(handle)
        return ((info.volume, info.index_high, info.index_low), info.attributes, info.links)

    def snapshot(self, handle):
        c, w = self.c, self.w
        info = self._information(handle)
        name, flags, serial, maximum = c.create_unicode_buffer(32), w.DWORD(), w.DWORD(), w.DWORD()
        self._ok(self.kernel.GetVolumeInformationByHandleW(handle, None, 0, c.byref(serial), c.byref(maximum),
                                                          c.byref(flags), name, len(name)))
        # ReFS requires independently reviewed 128-bit FileIdInfo binding.
        _require(flags.value & 0x08 and name.value == "NTFS" and serial.value == info.volume, "persistent-local-acl-required")
        descriptor = c.c_void_p()
        result = self.advapi.GetSecurityInfo(handle, 1, 0x05, None, None, None, None, c.byref(descriptor))
        _require(result == 0 and descriptor.value is not None, "native-security-descriptor-refused")
        try:
            self._ok(self.advapi.IsValidSecurityDescriptor(descriptor))
            size = self.advapi.GetSecurityDescriptorLength(descriptor)
            _require(20 <= size <= MAX_DESCRIPTOR, "native-security-descriptor-bound")
            start, end = descriptor.value, descriptor.value + size
            control, revision = w.WORD(), w.DWORD()
            self._ok(self.advapi.GetSecurityDescriptorControl(descriptor, c.byref(control), c.byref(revision)))
            owner, defaulted = c.c_void_p(), w.BOOL()
            self._ok(self.advapi.GetSecurityDescriptorOwner(descriptor, c.byref(owner), c.byref(defaulted)))
            _require(not defaulted.value, "native-defaulted-owner-refused")
            owner_bytes = self._copy_sid(owner, start, end)
            present, acl, defaulted = w.BOOL(), c.c_void_p(), w.BOOL()
            self._ok(self.advapi.GetSecurityDescriptorDacl(descriptor, c.byref(present), c.byref(acl), c.byref(defaulted)))
            _require(present.value and acl.value is not None and not defaulted.value
                     and start <= acl.value and acl.value + 8 <= end, "missing-or-null-dacl")
            header = c.string_at(acl.value, 8)
            acl_size, ace_count = struct.unpack_from("<HH", header, 2)
            _require(header[0] in (2, 4) and 8 <= acl_size and acl.value + acl_size <= end
                     and 1 <= ace_count <= MAX_ACES, "native-acl-bound")
            usage = (w.DWORD * 3)()
            self._ok(self.advapi.GetAclInformation(acl, usage, c.sizeof(usage), 2))
            _require(usage[0] == ace_count and 8 <= usage[1] <= acl_size and usage[1] + usage[2] == acl_size, "native-acl-bound")
            aces, expected = [], acl.value + 8
            for index in range(ace_count):
                pointer = c.c_void_p()
                self._ok(self.advapi.GetAce(acl, index, c.byref(pointer)))
                _require(pointer.value == expected and expected + 8 <= acl.value + usage[1], "native-ace-bound")
                kind, ace_flags, ace_size, mask = struct.unpack("<BBHI", c.string_at(expected, 8))
                _require(kind in (0, 1) and 16 <= ace_size and expected + ace_size <= acl.value + usage[1], "unsupported-ace")
                sid = self._copy_sid(c.c_void_p(expected + 8), expected + 8, expected + ace_size)
                _require(ace_size == 8 + len(sid), "native-ace-bound")
                aces.append(Ace(kind, ace_flags, mask, sid))
                expected += ace_size
            _require(expected == acl.value + usage[1], "native-acl-bound")
            return Snapshot((info.volume, info.index_high, info.index_low), info.attributes, info.links,
                            owner_bytes, control.value, tuple(aces), hashlib.sha256(c.string_at(start, size)).hexdigest())
        finally:
            _require(self.kernel.LocalFree(descriptor) is None, "native-descriptor-release-refused")


class PrivateDirectoryGuard:
    def __init__(self, native, user, opened, *, missing_path=None):
        self.native, self.user, self.opened = native, user, opened
        self.missing_path = missing_path

    @property
    def path(self):
        return self.opened[-1][0]

    def verify(self):
        _require(self.native.token_user() == self.user, "native-token-changed")
        for _path, handle, original, private in self.opened:
            observed = self.native.snapshot(handle)
            (require_private(observed, self.user, directory=True) if private else require_parent(observed, self.user))
            _require(observed == original, "native-private-boundary-changed")
        if self.missing_path is not None:
            try:
                handle = self.native.open_directory(self.missing_path)
            except PrivatePathMissing:
                return
            try:
                raise PrivateStorageError("native-missing-boundary-changed")
            finally:
                self.native.close(handle)

    def verify_entries(self, *, maximum):
        """Qualify every existing direct child before a new lock/payload byte.

        Enumeration is bounded and consumes no file payload. Retained ancestor
        handles and the exact private root prevent untrusted name replacement;
        all yielded named handles close even when a descriptor/limit refuses.
        """
        _require(type(maximum) is int and 1 <= maximum <= 134, "private-entry-bound")
        self.verify()
        count = 0
        with self.native.directory_entries(self.path) as entries:
            for path in entries:
                count += 1
                _require(count <= maximum, "private-entry-bound")
                with self.named_file(path):
                    pass
        self.verify()
        return count

    @contextmanager
    def private_file(self, native_handle, expected_path):
        """Bind the actual writer handle to a retained named private child.

        Enter before plaintext/copy/append; leave after flush/verification and
        before atomic rename. The named handle has READ_CONTROL independently
        of an os.open writer handle's access rights, and excludes delete sharing.
        """
        self.verify()
        paths = _ancestors(expected_path)
        _require(len(paths) == len(self.opened) + 1
                 and paths[-2] == self.opened[-1][0], "private-child-containment-refused")
        named = self.native.open_file(paths[-1])
        try:
            snapshot = self.native.snapshot(named)
            require_private(snapshot, self.user, directory=False)
            identity = (snapshot.identity, snapshot.attributes, snapshot.links)
            _require(self.native.identity(native_handle) == identity, "private-writer-handle-mismatch")
            _require(snapshot.identity[0] == self.opened[-1][2].identity[0], "private-volume-mismatch")
            yield snapshot
            self.verify()
            observed = self.native.snapshot(named)
            require_private(observed, self.user, directory=False)
            _require(observed == snapshot and self.native.identity(native_handle) == identity, "private-file-boundary-changed")
        finally:
            self.native.close(named)

    @contextmanager
    def named_file(self, expected_path, *, expected_identity=None):
        """Retain a final/read-only direct child's exact private native object.

        The caller must leave this context before replacing that named target.
        It does not read payload or change its owner/DACL.
        """
        self.verify()
        paths = _ancestors(expected_path)
        _require(len(paths) == len(self.opened) + 1 and paths[-2] == self.path,
                 "private-child-containment-refused")
        named = self.native.open_file(paths[-1])
        try:
            snapshot = self.native.snapshot(named)
            require_private(snapshot, self.user, directory=False)
            _require(snapshot.identity[0] == self.opened[-1][2].identity[0], "private-volume-mismatch")
            _require(expected_identity is None or snapshot.identity == expected_identity,
                     "private-final-identity-mismatch")
            yield snapshot
            self.verify()
            observed = self.native.snapshot(named)
            require_private(observed, self.user, directory=False)
            _require(observed == snapshot, "private-file-boundary-changed")
        finally:
            self.native.close(named)


def descriptor_handle(descriptor):
    """Obtain the actual CRT descriptor's native handle only on the real path."""
    _require(os.name == "nt" and type(descriptor) is int and descriptor >= 0,
             "native-descriptor-required")
    import msvcrt

    handle = msvcrt.get_osfhandle(descriptor)
    _require(type(handle) is int and handle not in (-1, -2), "native-descriptor-refused")
    return handle


@contextmanager
def private_stage_guard(path, *, create=False, create_if_missing=False, _native=None):
    """Hold non-delete-shared ancestor handles through all writes/verification.

Default native provider is Windows-only. `_native` is an explicit pure mock seam;
product callers must never accept a supplied provider from configuration/input.
"""
    _require(type(create) is bool and type(create_if_missing) is bool
             and not (create and create_if_missing), "invalid-private-stage-request")
    native = _Native() if _native is None else _native
    paths, opened = _ancestors(path), []
    user = _sid(native.token_user())
    try:
        for ancestor in paths[:-1]:
            handle = native.open_directory(ancestor)
            opened.append((ancestor, handle, None, False))
            snapshot = native.snapshot(handle)
            require_parent(snapshot, user)
            opened[-1] = (ancestor, handle, snapshot, False)
            if len(opened) > 1:
                _require(snapshot.identity[0] == opened[0][2].identity[0], "private-volume-mismatch")
        if create:
            native.create_private_directory(paths[-1], user)
        try:
            handle = native.open_directory(paths[-1])
        except PrivatePathMissing:
            _require(create_if_missing and not create, "private-stage-missing")
            # Every existing parent is still retained and already validated.
            # A racing creator makes exclusive creation refuse; never adopt it.
            native.create_private_directory(paths[-1], user)
            handle = native.open_directory(paths[-1])
        opened.append((paths[-1], handle, None, True))
        snapshot = native.snapshot(handle)
        require_private(snapshot, user, directory=True)
        _require(snapshot.identity[0] == opened[0][2].identity[0], "private-volume-mismatch")
        opened[-1] = (paths[-1], handle, snapshot, True)
        guard = PrivateDirectoryGuard(native, user, opened)
        guard.verify()
        yield guard
        guard.verify()
    finally:
        failed = False
        for _path, handle, _snapshot, _private in reversed(opened):
            try:
                native.close(handle)
            except (OSError, PrivateStorageError):
                failed = True
        _require(not failed, "native-handle-cleanup-refused")


@contextmanager
def private_home_guard(path, *, _native=None):
    """Observe ROW_HOME/default current state without creating or rewriting it.

    An existing last component must be an exact private directory. For a first
    use home, hold all existing conservative parents and recheck the first
    missing component; no subsequent component is created by the updater.
    """
    native = _Native() if _native is None else _native
    paths, opened, missing = _ancestors(path), [], None
    user = _sid(native.token_user())
    try:
        for index, ancestor in enumerate(paths):
            try:
                handle = native.open_directory(ancestor)
            except PrivatePathMissing:
                _require(index > 0 and bool(opened), "native-home-volume-missing")
                missing = ancestor
                break
            opened.append((ancestor, handle, None, index == len(paths) - 1))
            observed = native.snapshot(handle)
            private = index == len(paths) - 1
            (require_private(observed, user, directory=True) if private else require_parent(observed, user))
            _require(index == 0 or observed.identity[0] == opened[0][2].identity[0], "private-volume-mismatch")
            opened[-1] = (ancestor, handle, observed, private)
        guard = PrivateDirectoryGuard(native, user, opened, missing_path=missing)
        guard.verify()
        yield guard
        guard.verify()
    finally:
        failed = False
        for _path, handle, _snapshot, _private in reversed(opened):
            try:
                native.close(handle)
            except (OSError, PrivateStorageError):
                failed = True
        _require(not failed, "native-handle-cleanup-refused")


def _selected_home(native, current_home, environment):
    """Bind actual repository data_dir behavior, not an invented stage default."""
    selected = _ancestors(current_home)[-1]
    override = environment.get("ROW_HOME")
    if override:
        # data_dir resolves ROW_HOME before reaching the command. Require the
        # original selection to be an exact local path too; refuse expansion,
        # aliases, symlink resolution and lossy Unicode/case equivalence.
        original = _ancestors(override)[-1]
        _require(override.replace("/", "\\") == original and selected == original,
                 "row-home-selection-mismatch")
        return selected
    roaming = native.known_folder("roaming")
    _require(roaming == native.known_folder("roaming", default=True), "redirected-default-home-refused")
    local = native.known_folder("local")
    _require(local == native.known_folder("local", default=True), "redirected-default-local-refused")
    _ancestors(local)
    appdata = environment.get("APPDATA")
    _require(not appdata or _ancestors(appdata)[-1] == roaming,
             "appdata-selection-mismatch")
    _require(selected == ntpath.join(roaming, "RemoteOpsWorkspace"), "default-home-selection-mismatch")
    return selected


@contextmanager
def windows_update_boundary(stage_root, current_home, *, create=False, _native=None, _environment=None):
    """Bind current-home selection and hold all native stage ancestors/roots.

    An explicit --stage remains required. This never creates/chmods/rewrites
    ROW_HOME, default app roots or any pre-existing owner/DACL. Only an absent
    selected stage leaf can be created exclusively with its private descriptor.
    Product callers never accept a provider/environment from configuration.
    """
    _require(type(create) is bool, "invalid-private-stage-request")
    native = _Native() if _native is None else _native
    environment = os.environ if _environment is None else _environment
    root_paths = _ancestors(stage_root)
    root = root_paths[-1]
    selected = _selected_home(native, current_home, environment)
    home_paths = _ancestors(selected)
    # Conservative lexical alias collision refusal is supplemental only. Real
    # existing home containment below is bound by volume/file indices.
    folded_root = tuple(piece.casefold() for piece in root_paths)
    folded_home = tuple(piece.casefold() for piece in home_paths)
    _require(folded_root[:len(folded_home)] != folded_home, "stage-must-be-outside-home")
    with private_home_guard(selected, _native=native) as home:
        with private_stage_guard(root, create_if_missing=create, _native=native) as stage:
            if home.missing_path is None:
                home_id = home.opened[-1][2].identity
                _require(all(row[2].identity != home_id for row in stage.opened), "stage-must-be-outside-home")
            home.verify()
            stage.verify()
            # Maximum 64 assets, their partials, journal/manifest/lock and
            # their partials. Unknown entries still undergo metadata checks;
            # the authenticated transaction separately rejects unknown names.
            stage.verify_entries(maximum=134)
            yield stage
            home.verify()
            stage.verify()
