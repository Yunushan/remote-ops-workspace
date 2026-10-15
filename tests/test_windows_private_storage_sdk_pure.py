"""Finite SDK contract mocks; no ctypes, DLL, CRT or product import.

These cases compile selected actual source nodes only inside the fixture. Their
filename is the candidate's real source filename, so ordinary branch tracing
can see the exercised product lines. Memory addresses, layouts and API outcomes
are bounded synthetic values. They do not qualify Windows ABI, default ancestry,
other-user denial or any production privacy/installation gate.

Fixed declaration facts below were read independently from Microsoft Windows
SDK 10.0.26100.0: fileapi.h, handleapi.h, winbase.h, processthreadsapi.h,
securitybaseapi.h, aclapi.h, winnt.h, minwinbase.h, KnownFolders.h,
shlobj_core.h and combaseapi.h. CI needs neither an installed SDK nor .tmp data.
No expected prototype, GUID, mask or structure is extracted from product AST.
"""
from __future__ import annotations
import __future__

import ast
import builtins
import hashlib
import ntpath
import re
import struct
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

USER = bytes.fromhex("0101000000000005e9030000")
OTHER = bytes.fromhex("0101000000000005ea030000")
INVALID_HANDLE = 0xFFFFFFFFFFFFFFFF
FILE_PATH = r"C:\Stage\journal.json"
DIRECTORY_PATH = r"C:\Stage"
ROAMING_GUID = bytes.fromhex("db85b63ef965f64ca03ae3ef65729f3d")
LOCAL_GUID = bytes.fromhex("8527b3f1ba6fcf4f9d557b8e7f157091")
MAX_FOLDER_PATH = "C:\\" + "\\".join(["x" * 64] * 62 + ["y" * 63])

# p: LPVOID, d: DWORD, b: BOOL, h: HANDLE. Pointer categories are explicit.
SDK_PROTOTYPES = {
    "GetCurrentProcess": ("kernel32", (), "h"),
    "GetCurrentThread": ("kernel32", (), "h"),
    "CloseHandle": ("kernel32", ("h",), "b"),
    "LocalFree": ("kernel32", ("p",), "p"),
    "GetDriveTypeW": ("kernel32", ("LPCWSTR",), "UINT"),
    "CreateFileW": ("kernel32", ("LPCWSTR", "d", "d", "p", "d", "d", "h"), "h"),
    "CreateDirectoryW": ("kernel32", ("LPCWSTR", "p"), "b"),
    "GetFileInformationByHandle": ("kernel32", ("h", "p"), "b"),
    "GetVolumeInformationByHandleW": ("kernel32", ("h", "LPWSTR", "d", "p", "p", "p", "LPWSTR", "d"), "b"),
    "OpenThreadToken": ("advapi32", ("h", "d", "b", "*h"), "b"),
    "OpenProcessToken": ("advapi32", ("h", "d", "*h"), "b"),
    "GetTokenInformation": ("advapi32", ("h", "int", "p", "d", "*d"), "b"),
    "GetSecurityInfo": ("advapi32", ("h", "int", "d", "p", "p", "p", "p", "*p"), "d"),
    "GetSecurityDescriptorLength": ("advapi32", ("p",), "d"),
    "IsValidSecurityDescriptor": ("advapi32", ("p",), "b"),
    "GetSecurityDescriptorControl": ("advapi32", ("p", "p", "p"), "b"),
    "GetSecurityDescriptorOwner": ("advapi32", ("p", "p", "p"), "b"),
    "GetSecurityDescriptorDacl": ("advapi32", ("p", "p", "p", "p"), "b"),
    "GetAclInformation": ("advapi32", ("p", "p", "d", "int"), "b"),
    "GetAce": ("advapi32", ("p", "d", "p"), "b"),
    "IsValidSid": ("advapi32", ("p",), "b"),
    "GetLengthSid": ("advapi32", ("p",), "d"),
    "InitializeAcl": ("advapi32", ("p", "d", "d"), "b"),
    "AddAccessAllowedAceEx": ("advapi32", ("p", "d", "d", "d", "p"), "b"),
    "InitializeSecurityDescriptor": ("advapi32", ("p", "d"), "b"),
    "SetSecurityDescriptorOwner": ("advapi32", ("p", "p", "b"), "b"),
    "SetSecurityDescriptorDacl": ("advapi32", ("p", "b", "p", "b"), "b"),
    "SetSecurityDescriptorControl": ("advapi32", ("p", "WORD", "WORD"), "b"),
    "SHGetKnownFolderPath": ("shell32", ("p", "d", "h", "*p"), "LONG"),
    "CoTaskMemFree": ("ole32", ("p",), None),
}
SDK_DESCRIPTOR_FIELDS = (("revision", "BYTE"), ("reserved", "BYTE"), ("control", "WORD"),
                         ("owner", "p"), ("group", "p"), ("sacl", "p"), ("dacl", "p"))
SDK_ATTRIBUTES_FIELDS = (("length", "d"), ("descriptor", "p"), ("inherit_handle", "b"))
SDK_INFORMATION_FIELDS = (("attributes", "d"), ("creation", "FILETIME"), ("access", "FILETIME"),
                          ("write", "FILETIME"), ("volume", "d"), ("size_high", "d"),
                          ("size_low", "d"), ("links", "d"), ("index_high", "d"), ("index_low", "d"))


class Cell:
    def __init__(self, kind, value):
        self.kind, self.value = kind, value


class Scalar:
    def __init__(self, tag, width, alignment=None, *, pointer=False):
        self.tag, self.width = tag, width
        self.alignment = width if alignment is None else alignment
        self.pointer = pointer

    def __call__(self, value=None):
        if value is None and not self.pointer:
            value = 0
        if self.pointer and value == -1:
            value = INVALID_HANDLE
        return Cell(self, value)

    def __mul__(self, count):
        assert type(count) is int and 1 <= count <= 64
        return ArrayType(self, count)


class ArrayType:
    def __init__(self, kind, count):
        self.kind, self.count = kind, count

    def __call__(self):
        return Array(self.kind, self.count)


class Array:
    def __init__(self, kind, count):
        self.kind, self.values = kind, [0] * count

    def __getitem__(self, index):
        return self.values[index]

    def __setitem__(self, index, value):
        assert type(index) is int and 0 <= index < len(self.values)
        assert type(value) is int and 0 <= value <= 0xFFFFFFFF
        self.values[index] = value


class Region:
    def __init__(self, address, value, *, wide=False):
        self.address, self.wide, self.freed = address, wide, False
        self.value = list(value) if wide else bytearray(value)

    def __len__(self):
        return len(self.value)


class Arena:
    """Only these finite Python byte/character arrays can ever be dereferenced."""

    def __init__(self):
        self.regions, self.objects, self.reads = [], {}, []
        self.next_address = 0x10000

    def allocate(self, value, *, wide=False):
        assert 1 <= len(value) <= 65536
        assert len(self.regions) < 128
        region = Region(self.next_address, value, wide=wide)
        self.next_address += ((len(value) * (2 if wide else 1) + 15) // 16) * 16 + 16
        self.regions.append(region)
        return region

    def region(self, address, size, *, wide=False):
        assert type(address) is int and type(size) is int and 0 <= size <= 65536
        for region in self.regions:
            width = 2 if region.wide else 1
            if region.wide == wide and region.address <= address and address + size * width <= region.address + len(region) * width:
                assert not region.freed, "virtual read after allocator release"
                return region, (address - region.address) // width
        raise AssertionError("virtual memory access outside an explicit bounded allocation")

    def bytes(self, address, size):
        region, offset = self.region(address, size)
        self.reads.append(("bytes", address, size))
        return bytes(region.value[offset:offset + size])

    def character(self, address, index):
        assert type(index) is int and 0 <= index <= 4096
        region, offset = self.region(address + index * 2, 1, wide=True)
        self.reads.append(("wide", address, index))
        return region.value[offset]

    def write(self, address, value):
        region, offset = self.region(address, len(value))
        region.value[offset:offset + len(value)] = value

    def release(self, address):
        matches = [region for region in self.regions if region.address == address]
        assert len(matches) == 1 and not matches[0].freed, "duplicate or foreign virtual free"
        matches[0].freed = True

    def object_address(self, value):
        if not hasattr(value, "_virtual_address"):
            value._virtual_address = self.allocate(bytes(64)).address
            self.objects[value._virtual_address] = value
        return value._virtual_address


class Buffer:
    def __init__(self, region):
        self.region = region

    def __len__(self):
        return len(self.region)

    @property
    def value(self):
        if self.region.wide:
            return "".join(self.region.value).split("\x00", 1)[0]
        return bytes(self.region.value).split(b"\x00", 1)[0]

    @value.setter
    def value(self, value):
        assert self.region.wide and type(value) is str and len(value) < len(self)
        self.region.value[:] = list(value) + ["\x00"] * (len(self) - len(value))


class PointerType:
    def __init__(self, target):
        self.target, self.tag = target, "*" + target.tag


class PointerView:
    def __init__(self, c, address, target):
        self.c, self.address, self.target = c, address, target

    def __getitem__(self, index):
        if self.target is self.c.c_wchar:
            return self.c.arena.character(self.address, index)
        assert self.target is self.c.c_void_p and index == 0
        return struct.unpack("<Q", self.c.arena.bytes(self.address, 8))[0]


class Ref:
    def __init__(self, value):
        self.value = value


def scalar_value(value):
    return value.value if isinstance(value, Cell) else value


def fields_of(value):
    return tuple((name, kind.tag) for name, kind in value._fields_)


class FakeC:
    def __init__(self, harness):
        self.harness, self.arena, self.last_error = harness, harness.arena, 0
        self.c_void_p, self.c_int, self.c_wchar = Scalar("p", 8, pointer=True), Scalar("int", 4), Scalar("wchar", 2)
        self.wintypes = SimpleNamespace(DWORD=Scalar("d", 4), BOOL=Scalar("b", 4), HANDLE=Scalar("h", 8, pointer=True),
                                       WORD=Scalar("WORD", 2), BYTE=Scalar("BYTE", 1), UINT=Scalar("UINT", 4),
                                       LONG=Scalar("LONG", 4), LPCWSTR=Scalar("LPCWSTR", 8, pointer=True),
                                       LPWSTR=Scalar("LPWSTR", 8, pointer=True), FILETIME=Scalar("FILETIME", 8, 4))
        self.pointers = {}

        class Structure:
            def __init__(self, *values):
                assert len(values) <= len(self._fields_)
                for index, (name, _kind) in enumerate(self._fields_):
                    setattr(self, name, values[index] if index < len(values) else 0)

        self.Structure = Structure

    def __getattr__(self, name):
        raise AssertionError("unapproved ctypes capability: " + name)

    def WinDLL(self, name, *, use_last_error):
        assert name in ("kernel32", "advapi32", "shell32", "ole32") and use_last_error is True
        self.harness.dll_loads.append((name, use_last_error))
        return self.harness.dlls[name]

    def POINTER(self, target):
        if target not in self.pointers:
            self.pointers[target] = PointerType(target)
        return self.pointers[target]

    def cast(self, value, target):
        address = self.addressof(value) if isinstance(value, Buffer) else scalar_value(value)
        if target is self.c_void_p:
            return self.c_void_p(address)
        assert isinstance(target, PointerType)
        return PointerView(self, address, target.target)

    def byref(self, value):
        return Ref(value)

    def addressof(self, value):
        return value.region.address if isinstance(value, Buffer) else self.arena.object_address(value)

    def string_at(self, address, size):
        return self.arena.bytes(self.addressof(address) if isinstance(address, Buffer) else scalar_value(address), size)

    def create_string_buffer(self, value, size=None):
        if type(value) is int:
            assert size is None
            return Buffer(self.arena.allocate(bytes(value)))
        assert type(value) is bytes
        length = len(value) + 1 if size is None else size
        assert len(value) <= length
        return Buffer(self.arena.allocate(value + bytes(length - len(value))))

    def create_unicode_buffer(self, size):
        assert type(size) is int and 1 <= size <= 4098
        return Buffer(self.arena.allocate("\x00" * size, wide=True))

    def sizeof(self, value):
        if isinstance(value, Scalar):
            return value.width
        if isinstance(value, Array):
            return value.kind.width * len(value.values)
        cls = value if isinstance(value, type) else type(value)
        assert issubclass(cls, self.Structure)
        offset, alignment = 0, 1
        for _name, kind in cls._fields_:
            alignment = max(alignment, kind.alignment)
            offset = (offset + kind.alignment - 1) // kind.alignment * kind.alignment + kind.width
        return (offset + alignment - 1) // alignment * alignment

    def get_last_error(self):
        return self.last_error


class Function:
    def __init__(self, harness, name):
        self.harness, self.name, self.argtypes, self.restype = harness, name, None, None

    def __call__(self, *arguments):
        self.harness.calls.append((self.name, arguments))
        assert self.name in self.harness.handlers, "unapproved SDK function call: " + self.name
        return self.harness.handlers[self.name](*arguments)


class DLL:
    def __init__(self, harness, library):
        self.functions = {name: Function(harness, name) for name, (dll, _args, _result) in SDK_PROTOTYPES.items() if dll == library}

    def __getattr__(self, name):
        assert name in self.functions, "unapproved DLL export: " + name
        return self.functions[name]


class FakeOS:
    name = "nt"

    def __init__(self):
        self.enumerator = None

    def __getattr__(self, name):
        raise AssertionError("unapproved OS capability: " + name)

    def fspath(self, value):
        assert type(value) is str
        return value

    def scandir(self, path):
        assert self.enumerator is not None, "unapproved filesystem enumeration"
        return self.enumerator(path)


class Harness:
    def __init__(self):
        self.arena, self.os = Arena(), FakeOS()
        self.calls, self.dll_loads, self.handlers = [], [], {}
        self.closed, self.freed_com, self.freed_local, self.token_opened = [], [], [], []
        self.dlls = {library: DLL(self, library) for library in ("kernel32", "advapi32", "shell32", "ole32")}
        self.c = FakeC(self)
        self.crt_calls, self.crt_result = [], None
        self.crt = SimpleNamespace(get_osfhandle=self.crt_handle)

    @property
    def names(self):
        return [name for name, _arguments in self.calls]

    def allow(self, name, callback):
        assert name in SDK_PROTOTYPES and callable(callback)
        self.handlers[name] = callback

    def crt_handle(self, descriptor):
        self.crt_calls.append(descriptor)
        assert self.crt_result is not None, "unapproved CRT handle query"
        if isinstance(self.crt_result, BaseException):
            raise self.crt_result
        return self.crt_result

    def import_fake(self, name, _globals=None, _locals=None, fromlist=(), level=0):
        assert level == 0
        if name == "ctypes":
            assert fromlist in (None, (), ("wintypes",))
            return self.c
        if name == "msvcrt":
            assert not fromlist
            return self.crt
        raise AssertionError("unapproved projected-source import: " + name)

    def sid_apis(self, length, *, valid=True):
        self.allow("IsValidSid", lambda _pointer: int(valid))
        self.allow("GetLengthSid", lambda _pointer: length)

    def close_api(self, *, success=True):
        def close(handle):
            value = scalar_value(handle)
            assert value not in self.closed, "duplicate virtual handle close"
            if success:
                self.closed.append(value)
            return int(success)
        self.allow("CloseHandle", close)

    def token(self, fault="success", *, users=(USER,), capacity=32):
        """Explicit TOKEN_QUERY/TOKEN_USER mock; no implicit success exports."""
        self.allow("GetCurrentThread", lambda: -2)
        self.allow("GetCurrentProcess", lambda: -1)
        self.close_api()
        self.sid_apis(12, valid=fault != "sid-invalid")
        if fault == "sid-length":
            self.sid_apis(16)
        assert capacity in (28, 32, 65536)
        current, filled, thread_calls = [0], [0], [0]

        def thread(handle, access, open_as_self, result):
            assert (handle, access, open_as_self) == (-2, 8, True)
            thread_calls[0] += 1
            if fault == "impersonated":
                result.value.value = 100
                self.token_opened.append(100)
                return 1
            self.c.last_error = 5 if fault == "thread-error" or (fault == "second-thread-error" and thread_calls[0] == 2) else 1008
            return 0

        def process(handle, access, result):
            assert (handle, access) == (-1, 8)
            if fault == "process-failure":
                return 0
            current[0] += 1
            result.value.value = 100 + current[0]
            self.token_opened.append(result.value.value)
            return 1

        def information(handle, info_class, buffer, buffer_capacity, result):
            assert scalar_value(handle) == 100 + current[0] and info_class == 1
            if buffer is None:
                assert buffer_capacity == 0
                result.value.value = 11 if fault == "query-small" else 65537 if fault == "query-large" else capacity
                self.c.last_error = 5 if fault == "query-error" else 122
                return int(fault == "query-success")
            assert buffer_capacity == capacity and len(buffer) == capacity
            if fault == "fill-failure":
                return 0
            if fault == "fill-exception":
                raise RuntimeError("controlled-token-provider-fault")
            if fault == "fill-interrupt":
                raise KeyboardInterrupt("controlled-token-provider-fault")
            user = users[min(filled[0], len(users) - 1)]
            filled[0] += 1
            address = self.c.addressof(buffer)
            self.arena.write(address, struct.pack("<Q", address + 16))
            self.arena.write(address + 16, user)
            return 1

        self.allow("OpenThreadToken", thread)
        self.allow("OpenProcessToken", process)
        self.allow("GetTokenInformation", information)

    def folder(self, path, *, result=0, allocate=True):
        self.folder_addresses = []

        def query(guid, flags, token, output):
            assert len(guid) == 16 and token is None
            assert flags in (0x4000, 0x4400)
            if allocate:
                region = self.arena.allocate(path + "\x00", wide=True)
                output.value.value = region.address
                self.folder_addresses.append(region.address)
            return result

        def free(pointer):
            address = scalar_value(pointer)
            self.arena.release(address)
            self.freed_com.append(address)

        self.allow("SHGetKnownFolderPath", query)
        self.allow("CoTaskMemFree", free)

    def information(self, *, success=True):
        def query(handle, output):
            assert handle == 77 and fields_of(output.value) == SDK_INFORMATION_FIELDS
            if not success:
                return 0
            for name, value in (("attributes", 0x10), ("volume", 7), ("links", 1), ("index_high", 23), ("index_low", 29)):
                setattr(output.value, name, value)
            return 1
        self.allow("GetFileInformationByHandle", query)

    def snapshot(self, fault="success", *, acl_revision=2, kinds=(0,), descriptor_size=128):
        """Fixed relative-SD/ACL/ACE bytes from declared field contracts."""
        self.information(success=fault != "information-api")
        self.sid_apis(16 if fault == "sid-length" else 12, valid=fault != "sid-api")
        ace_size = 24 if fault == "ace-padding" else 20
        ace_records = [struct.pack("<BBHI", kind, 3, ace_size, 0x001F01FF) + USER + bytes(ace_size - 20) for kind in kinds]
        if fault == "ace-kind":
            ace_records[0] = struct.pack("<BBHI", 2, 3, 20, 0x001F01FF) + USER
        elif fault == "ace-short":
            ace_records[0] = struct.pack("<BBHI", 0, 3, 15, 0x001F01FF) + USER
        elif fault == "ace-outside":
            ace_records[0] = struct.pack("<BBHI", 0, 3, 64, 0x001F01FF) + USER
        elif fault == "sid-revision":
            ace_records[0] = ace_records[0][:8] + bytes([2]) + USER[1:]
        elif fault == "sid-count":
            ace_records[0] = ace_records[0][:9] + bytes([16]) + USER[2:]
        used = 8 + sum(map(len, ace_records))
        acl_size = used + (4 if fault == "acl-unconsumed" else 0)
        count = 0 if fault == "acl-empty" else 65 if fault == "acl-many" else len(kinds)
        declared_size = 7 if fault == "acl-short" else 200 if fault == "acl-outside" else acl_size
        header = struct.pack("<BBHHH", 1 if fault == "acl-revision" else acl_revision, 0, declared_size, count, 0)
        assert descriptor_size in (128, 65536)
        data = bytearray(descriptor_size)
        data[:20] = struct.pack("<BBHIIII", 1, 0, 0x1004, 24, 0, 0, 48)
        data[24:36] = USER
        data[48:48 + 8] = header
        cursor = 56
        for record in ace_records:
            data[cursor:cursor + len(record)] = record
            cursor += len(record)
        region = self.arena.allocate(bytes(data))
        start, owner, acl = region.address, region.address + 24, region.address + 48
        self.descriptor_address, self.descriptor_bytes = start, bytes(data)
        self.security_allocations = []

        def volume(handle, label, label_capacity, serial, maximum, flags, name, name_capacity):
            assert (handle, label, label_capacity, name_capacity) == (77, None, 0, 32)
            if fault == "volume-api":
                return 0
            serial.value.value, maximum.value.value = (8 if fault == "volume-serial" else 7), 255
            flags.value.value = 0 if fault == "volume-flags" else 8
            name.value = "ReFS" if fault == "volume-name" else "NTFS"
            return 1

        def security(handle, object_type, mask, owner_out, group_out, dacl_out, sacl_out, output):
            assert (handle, object_type, mask, owner_out, group_out, dacl_out, sacl_out) == (77, 1, 5, None, None, None, None)
            if fault == "security-api":
                return 5
            if fault != "security-null":
                output.value.value = start
                self.security_allocations.append(start)
            return 0

        def control(descriptor, output, revision):
            assert scalar_value(descriptor) == start
            output.value.value, revision.value.value = 0x1004, 1
            return int(fault != "control-api")

        def owner_query(descriptor, output, defaulted):
            assert scalar_value(descriptor) == start
            output.value.value = start - 1 if fault == "owner-low" else start + 121 if fault == "owner-high" else owner
            defaulted.value.value = int(fault == "owner-defaulted")
            return int(fault != "owner-api")

        def dacl(descriptor, present, output, defaulted):
            assert scalar_value(descriptor) == start
            present.value.value, defaulted.value.value = int(fault != "dacl-absent"), int(fault == "dacl-defaulted")
            output.value.value = None if fault == "dacl-null" else start - 1 if fault == "dacl-low" else start + 121 if fault == "dacl-high" else acl
            return int(fault != "dacl-api")

        def usage(pointer, output, capacity, info_class):
            assert (scalar_value(pointer), capacity, info_class) == (acl, 12, 2)
            output[0] = len(kinds) + int(fault == "usage-count")
            output[1] = 7 if fault == "usage-small" else acl_size + 1 if fault == "usage-large" else 8 if fault == "ace-header-outside" else acl_size
            output[2] = 1 if fault == "usage-free" else acl_size - 8 if fault == "ace-header-outside" else 0
            return int(fault != "usage-api")

        def ace(pointer, index, output):
            assert scalar_value(pointer) == acl and 0 <= index < len(kinds)
            output.value.value = acl + 8 + sum(len(record) for record in ace_records[:index]) + int(fault == "ace-pointer")
            return int(fault != "ace-api")

        def free(pointer):
            assert scalar_value(pointer) == start and self.security_allocations == [start]
            if fault == "release-api":
                return start
            self.arena.release(start)
            self.freed_local.append(start)
            return None

        self.allow("GetVolumeInformationByHandleW", volume)
        self.allow("GetSecurityInfo", security)
        self.allow("IsValidSecurityDescriptor", lambda _pointer: int(fault != "descriptor-invalid"))
        self.allow("GetSecurityDescriptorLength", lambda _pointer: 19 if fault == "descriptor-small" else 65537 if fault == "descriptor-large" else descriptor_size)
        self.allow("GetSecurityDescriptorControl", control)
        self.allow("GetSecurityDescriptorOwner", owner_query)
        self.allow("GetSecurityDescriptorDacl", dacl)
        self.allow("GetAclInformation", usage)
        self.allow("GetAce", ace)
        self.allow("LocalFree", free)

    def creation(self, fault=None):
        self.created = []

        def initialize_acl(acl, capacity, revision):
            assert (capacity, revision) == (28, 2) and len(acl) == 28
            self.arena.write(self.c.addressof(acl), struct.pack("<BBHHH", 2, 0, 28, 0, 0))
            return int(fault != "InitializeAcl")

        def add_ace(acl, revision, flags, mask, sid):
            assert (revision, flags, mask) == (2, 3, 0x001F01FF)
            assert self.c.string_at(sid, 12) == USER and len(sid) == 13
            address = self.c.addressof(acl)
            self.arena.write(address, struct.pack("<BBHHH", 2, 0, 28, 1, 0))
            self.arena.write(address + 8, struct.pack("<BBHI", 0, 3, 20, 0x001F01FF) + USER)
            return int(fault != "AddAccessAllowedAceEx")

        def initialize_descriptor(output, revision):
            assert revision == 1 and fields_of(output.value) == SDK_DESCRIPTOR_FIELDS
            output.value.revision = 1
            return int(fault != "InitializeSecurityDescriptor")

        def owner(output, sid, defaulted):
            assert defaulted is False and self.c.string_at(sid, 12) == USER
            output.value.owner = self.c.addressof(sid)
            return int(fault != "SetSecurityDescriptorOwner")

        def dacl(output, present, acl, defaulted):
            assert present is True and defaulted is False
            output.value.dacl = self.c.addressof(acl)
            output.value.control |= 4
            return int(fault != "SetSecurityDescriptorDacl")

        def control(output, mask, value):
            assert (mask, value) == (0x1000, 0x1000)
            output.value.control |= value
            return int(fault != "SetSecurityDescriptorControl")

        def create(path, attributes):
            assert path == DIRECTORY_PATH and fields_of(attributes.value) == SDK_ATTRIBUTES_FIELDS
            assert attributes.value.length == self.c.sizeof(type(attributes.value)) == 24
            assert attributes.value.inherit_handle is False
            descriptor = self.arena.objects[attributes.value.descriptor]
            assert descriptor.revision == 1 and descriptor.control == 0x1004
            assert (descriptor.group, descriptor.sacl) == (0, 0)
            assert self.arena.bytes(descriptor.owner, 12) == USER
            acl_bytes = self.arena.bytes(descriptor.dacl, 28)
            assert acl_bytes == struct.pack("<BBHHHBBHI", 2, 0, 28, 1, 0, 0, 3, 20, 0x001F01FF) + USER
            if fault == "CreateDirectoryW":
                self.c.last_error = 183  # ERROR_ALREADY_EXISTS still refuses.
                return 0
            self.created.append(path)
            return 1

        for name, callback in (("InitializeAcl", initialize_acl), ("AddAccessAllowedAceEx", add_ace),
                               ("InitializeSecurityDescriptor", initialize_descriptor), ("SetSecurityDescriptorOwner", owner),
                               ("SetSecurityDescriptorDacl", dacl), ("SetSecurityDescriptorControl", control),
                               ("CreateDirectoryW", create)):
            self.allow(name, callback)


def project_actual_source(harness, monkeypatch):
    """The only compile/exec site; no module imports or OS providers forwarded."""
    filename = Path(__file__).resolve().parents[1] / "src" / "remote_ops_workspace" / "windows_private_storage.py"
    tree = ast.parse(filename.read_text(encoding="utf-8"), filename=str(filename))
    selected_names = {"PrivateStorageError", "PrivatePathMissing", "_require", "_sid", "Ace", "Snapshot", "_ancestors", "_Native", "descriptor_handle"}
    constants = {"FILE_ALL_ACCESS", "DACL_PROTECTED", "MAX_DESCRIPTOR", "MAX_ACES"}
    nodes = []
    observed = set()
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in selected_names:
            nodes.append(node)
            observed.add(node.name)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in constants:
            nodes.append(node)
            observed.add(node.targets[0].id)
    assert observed == selected_names | constants
    module = ModuleType("row_sdk_pure_actual_source")
    monkeypatch.setitem(sys.modules, module.__name__, module)
    allowed_builtins = {name: getattr(builtins, name) for name in ("__build_class__", "object", "ValueError", "type", "len", "bool", "int", "str", "bytes", "tuple", "list", "range", "all", "any", "ord", "getattr")}
    allowed_builtins["__import__"] = harness.import_fake
    module.__dict__.update(__builtins__=allowed_builtins, os=harness.os, dataclass=dataclass, contextmanager=contextmanager,
                           ntpath=SimpleNamespace(splitdrive=ntpath.splitdrive, join=ntpath.join),
                           struct=SimpleNamespace(pack=struct.pack, unpack=struct.unpack, unpack_from=struct.unpack_from),
                           hashlib=SimpleNamespace(sha256=hashlib.sha256))
    fragment = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    exec(compile(fragment, str(filename), "exec", flags=__future__.annotations.compiler_flag, dont_inherit=True), module.__dict__)
    return module


@pytest.fixture
def sdk(monkeypatch):
    harness = Harness()
    harness.module = project_actual_source(harness, monkeypatch)
    harness.native = harness.module._Native()
    return harness


def refused(sdk, code):
    return pytest.raises(sdk.module.PrivateStorageError, match="^" + re.escape(code) + "$")


def test_sdk_constructor_binds_all_thirty_primary_prototypes_and_denies_other_effects(sdk):
    assert sdk.dll_loads == [(name, True) for name in ("kernel32", "advapi32", "shell32", "ole32")]
    assert len(SDK_PROTOTYPES) == 30 and sdk.calls == []
    for name, (dll, arguments, result) in SDK_PROTOTYPES.items():
        function = getattr(sdk.dlls[dll], name)
        assert tuple(kind.tag for kind in function.argtypes) == arguments
        assert (None if function.restype is None else function.restype.tag) == result
    for call in (lambda: sdk.c.WinDLL("unapproved", use_last_error=True), lambda: sdk.native.kernel.ReadFile,
                 lambda: sdk.c.CDLL, lambda: sdk.os.environ, lambda: sdk.import_fake("socket")):
        with pytest.raises(AssertionError):
            call()
    sdk.os.name = "posix"
    with refused(sdk, "windows-required"):
        sdk.module._Native()
    assert len(sdk.dll_loads) == 4 and sdk.calls == []


@pytest.mark.parametrize("sid", [USER, b"\x01\x0f" + bytes(6) + bytes(60)], ids=["one-subauthority", "maximum-fifteen"])
def test_sdk_copy_sid_obeys_declared_shape_and_allocation_bounds(sdk, sid):
    buffer = sdk.c.create_string_buffer(sid, len(sid))
    address = sdk.c.addressof(buffer)
    sdk.sid_apis(len(sid))
    assert sdk.native._copy_sid(sdk.c.c_void_p(address), address, address + len(sid)) == sid
    assert sdk.names == ["IsValidSid", "GetLengthSid"]
    assert sdk.arena.reads == [("bytes", address, 8), ("bytes", address, len(sid))]


@pytest.mark.parametrize("fault,code,expected_calls", [
    ("null", "native-sid-out-of-bound", []), ("before", "native-sid-out-of-bound", []),
    ("header-outside", "native-sid-out-of-bound", []), ("revision", "native-sid-out-of-bound", []),
    ("count", "native-sid-out-of-bound", []), ("tail-outside", "native-sid-out-of-bound", []),
    ("validity", "native-private-storage-refused", ["IsValidSid"]),
    ("length", "native-sid-out-of-bound", ["IsValidSid", "GetLengthSid"]),
])
def test_sdk_copy_sid_refuses_before_unbounded_read_or_later_api(sdk, fault, code, expected_calls):
    data = bytes([2]) + USER[1:] if fault == "revision" else USER[:1] + bytes([16]) + USER[2:] if fault == "count" else USER
    buffer = sdk.c.create_string_buffer(data, len(data))
    address = sdk.c.addressof(buffer)
    pointer = None if fault == "null" else address - 1 if fault == "before" else address
    high = address + 7 if fault == "header-outside" else address + 8 if fault == "tail-outside" else address + len(data)
    sdk.sid_apis(16 if fault == "length" else 12, valid=fault != "validity")
    with refused(sdk, code):
        sdk.native._copy_sid(sdk.c.c_void_p(pointer), address, high)
    assert sdk.names == expected_calls
    assert len(sdk.arena.reads) == (0 if fault in ("null", "before", "header-outside") else 1)


@pytest.mark.parametrize("capacity", [28, 32, 65536], ids=["exact-sid-end", "ordinary", "maximum-buffer"])
def test_sdk_token_user_uses_process_query_and_closes_its_owned_token(sdk, capacity):
    sdk.token(capacity=capacity)
    assert sdk.native.token_user() == USER
    assert sdk.token_opened == sdk.closed == [101]
    assert sdk.names == ["GetCurrentThread", "OpenThreadToken", "GetCurrentProcess", "OpenProcessToken", "GetTokenInformation", "GetTokenInformation", "IsValidSid", "GetLengthSid", "CloseHandle"]
    assert all(kind != "wide" for kind, _address, _length in sdk.arena.reads)


@pytest.mark.parametrize("fault,code,closed,last_before_close", [
    ("impersonated", "impersonated-thread-refused", [100], "OpenThreadToken"),
    ("thread-error", "native-token-scope-refused", [], "OpenThreadToken"),
    ("process-failure", "native-private-storage-refused", [], "OpenProcessToken"),
    ("query-success", "native-token-bound-refused", [101], "GetTokenInformation"),
    ("query-error", "native-token-bound-refused", [101], "GetTokenInformation"),
    ("query-small", "native-token-bound-refused", [101], "GetTokenInformation"),
    ("query-large", "native-token-bound-refused", [101], "GetTokenInformation"),
    ("fill-failure", "native-private-storage-refused", [101], "GetTokenInformation"),
    ("sid-invalid", "native-private-storage-refused", [101], "IsValidSid"),
    ("sid-length", "native-sid-out-of-bound", [101], "GetLengthSid"),
])
def test_sdk_token_refusal_preserves_scope_and_owned_cleanup(sdk, fault, code, closed, last_before_close):
    sdk.token(fault)
    with refused(sdk, code):
        sdk.native.token_user()
    assert sdk.closed == closed and sdk.token_opened == closed
    if closed:
        assert sdk.names[-2:] == [last_before_close, "CloseHandle"]
    else:
        assert sdk.names[-1:] == [last_before_close]
    if fault in ("impersonated", "thread-error", "process-failure", "query-success", "query-error", "query-small", "query-large"):
        assert sdk.arena.reads == []


@pytest.mark.parametrize("fault,error", [("fill-exception", RuntimeError), ("fill-interrupt", KeyboardInterrupt)])
def test_sdk_token_provider_exception_still_closes_owned_token(sdk, fault, error):
    sdk.token(fault)
    with pytest.raises(error, match="^controlled-token-provider-fault$"):
        sdk.native.token_user()
    assert sdk.token_opened == sdk.closed == [101] and sdk.names[-1] == "CloseHandle"


@pytest.mark.parametrize("role,default,guid,flags", [
    ("roaming", False, ROAMING_GUID, 0x4000), ("roaming", True, ROAMING_GUID, 0x4400),
    ("local", False, LOCAL_GUID, 0x4000), ("local", True, LOCAL_GUID, 0x4400),
])
def test_sdk_known_folders_bind_primary_guids_flags_current_token_and_com_free(sdk, role, default, guid, flags):
    path = "C:\\Users\\Operator\\AppData\\" + ("Roaming" if role == "roaming" else "Local")
    sdk.token()
    sdk.folder(path)
    assert sdk.native.known_folder(role, default=default) == path
    query = next(arguments for name, arguments in sdk.calls if name == "SHGetKnownFolderPath")
    assert sdk.c.string_at(query[0], 16) == guid and query[1:3] == (flags, None)
    assert sdk.freed_com == sdk.folder_addresses and len(sdk.freed_com) == 1
    assert sdk.token_opened == sdk.closed == [101, 102]
    assert sdk.names[-1] == "CoTaskMemFree" and sdk.freed_local == []


@pytest.mark.parametrize("role,default", [("other", False), ("roaming", 1), ("local", "false")])
def test_sdk_unknown_folder_request_has_no_token_or_shell_effect(sdk, role, default):
    with refused(sdk, "unknown-native-folder-role"):
        sdk.native.known_folder(role, default=default)
    assert sdk.calls == [] and sdk.arena.regions == []


def test_sdk_known_folder_accepts_exact_4096_characters_and_terminator(sdk):
    assert len(MAX_FOLDER_PATH) == 4096 and len(MAX_FOLDER_PATH.split("\\")[1:]) == 63
    sdk.token()
    sdk.folder(MAX_FOLDER_PATH)
    assert sdk.native.known_folder("local") == MAX_FOLDER_PATH
    wide = [index for kind, _address, index in sdk.arena.reads if kind == "wide"]
    assert wide == list(range(4097)) and sdk.freed_com == sdk.folder_addresses
    assert sdk.closed == [101, 102]


@pytest.mark.parametrize("fault,code", [
    ("hresult", "native-known-folder-refused"), ("null", "native-known-folder-refused"),
    ("first-nul", "unsafe-native-path"), ("non-nul-4096", "native-known-folder-bound"),
    ("alias", "native-known-folder-alias-refused"), ("token-change", "native-token-changed"),
])
def test_sdk_known_folder_refusals_free_any_returned_com_allocation(sdk, fault, code):
    path = "" if fault == "first-nul" else MAX_FOLDER_PATH + "b" if fault == "non-nul-4096" else r"c:\Data" if fault == "alias" else r"C:\Data"
    sdk.token(users=(USER, OTHER) if fault == "token-change" else (USER,))
    sdk.folder(path, result=0x80004005 if fault == "hresult" else 0, allocate=fault != "null")
    with refused(sdk, code):
        sdk.native.known_folder("roaming")
    assert sdk.freed_com == sdk.folder_addresses
    wide = [index for kind, _address, index in sdk.arena.reads if kind == "wide"]
    if fault in ("hresult", "null"):
        assert wide == []
    elif fault == "first-nul":
        assert wide == [0]
    elif fault == "non-nul-4096":
        assert wide == list(range(4097))
    assert sdk.closed == ([101, 102] if fault == "token-change" else [101])
    assert sdk.names[-1] == ("SHGetKnownFolderPath" if fault == "null" else "CoTaskMemFree")


def test_sdk_known_folder_initial_token_failure_never_calls_shell(sdk):
    sdk.token("thread-error")
    with refused(sdk, "native-token-scope-refused"):
        sdk.native.known_folder("local")
    assert "SHGetKnownFolderPath" not in sdk.names and sdk.freed_com == []


def test_sdk_known_folder_recheck_token_failure_frees_returned_allocation(sdk):
    sdk.token("second-thread-error")
    sdk.folder(r"C:\Data")
    with refused(sdk, "native-token-scope-refused"):
        sdk.native.known_folder("local")
    assert sdk.names[-2:] == ["OpenThreadToken", "CoTaskMemFree"]
    assert sdk.freed_com == sdk.folder_addresses and sdk.closed == [101]


@pytest.mark.parametrize("failure", ["none", "body", "iteration"])
def test_sdk_directory_entry_enumerator_closes_without_reading_file_payload(sdk, failure):
    events = []

    class Enumeration:
        def __enter__(self):
            events.append("enter")
            return self

        def __iter__(self):
            yield SimpleNamespace(path=FILE_PATH)
            if failure == "iteration":
                raise RuntimeError("controlled-enumeration-fault")

        def __exit__(self, _kind, _error, _traceback):
            events.append("exit")

    def scandir(path):
        assert path == DIRECTORY_PATH
        events.append("scandir")
        return Enumeration()

    sdk.os.enumerator = scandir
    if failure == "none":
        with sdk.native.directory_entries(DIRECTORY_PATH) as paths:
            assert list(paths) == [FILE_PATH]
    else:
        with pytest.raises(RuntimeError, match="^controlled-enumeration-fault$"):
            with sdk.native.directory_entries(DIRECTORY_PATH) as paths:
                if failure == "body":
                    raise RuntimeError("controlled-enumeration-fault")
                list(paths)
    assert events == ["scandir", "enter", "exit"] and sdk.calls == []


@pytest.mark.parametrize("directory,flags", [(True, 0x02200000), (False, 0x00200000)])
def test_sdk_opens_read_control_attributes_without_delete_sharing(sdk, directory, flags):
    sdk.allow("GetDriveTypeW", lambda root: 3 if root == "C:\\" else pytest.fail("wrong drive root"))

    def open_file(*arguments):
        assert arguments == (DIRECTORY_PATH if directory else FILE_PATH, 0x20080, 3, None, 3, flags, None)
        assert not arguments[2] & 4 and not arguments[1] & 0x40000000
        return 77

    sdk.allow("CreateFileW", open_file)
    sdk.close_api()
    assert (sdk.native.open_directory(DIRECTORY_PATH) if directory else sdk.native.open_file(FILE_PATH)) == 77
    assert sdk.closed == []
    sdk.native.close(77)
    assert sdk.closed == [77] and sdk.names[-1] == "CloseHandle"


@pytest.mark.parametrize("drive_type", [0, 2, 4, 5, 6])
def test_sdk_directory_refuses_nonfixed_volume_before_open(sdk, drive_type):
    sdk.allow("GetDriveTypeW", lambda _root: drive_type)
    with refused(sdk, "local-fixed-volume-required"):
        sdk.native.open_directory(DIRECTORY_PATH)
    assert sdk.names == ["GetDriveTypeW"]


@pytest.mark.parametrize("handle,error,missing", [(None, 2, True), (INVALID_HANDLE, 3, True), (None, 5, False), (INVALID_HANDLE, 32, False)])
def test_sdk_directory_missing_is_distinct_from_access_or_sharing_refusal(sdk, handle, error, missing):
    sdk.allow("GetDriveTypeW", lambda _root: 3)
    sdk.allow("CreateFileW", lambda *_arguments: handle)
    sdk.c.last_error = error
    code = "native-directory-missing" if missing else "native-directory-open-refused"
    with refused(sdk, code) as raised:
        sdk.native.open_directory(DIRECTORY_PATH)
    assert isinstance(raised.value, sdk.module.PrivatePathMissing) is missing
    assert sdk.names == ["GetDriveTypeW", "CreateFileW"] and sdk.closed == []


@pytest.mark.parametrize("handle", [None, INVALID_HANDLE])
def test_sdk_file_invalid_handle_has_no_owned_handle_to_close(sdk, handle):
    sdk.allow("CreateFileW", lambda *_arguments: handle)
    with refused(sdk, "native-file-open-refused"):
        sdk.native.open_file(FILE_PATH)
    assert sdk.names == ["CreateFileW"] and sdk.closed == []


def test_sdk_close_failure_is_a_fixed_native_refusal(sdk):
    sdk.close_api(success=False)
    with refused(sdk, "native-private-storage-refused"):
        sdk.native.close(77)
    assert sdk.names == ["CloseHandle"] and sdk.closed == []


def test_sdk_creation_builds_exact_owner_only_protected_noninheritable_attributes(sdk):
    sdk.creation()
    sdk.native.create_private_directory(DIRECTORY_PATH, USER)
    assert sdk.created == [DIRECTORY_PATH]
    assert sdk.names == ["InitializeAcl", "AddAccessAllowedAceEx", "InitializeSecurityDescriptor", "SetSecurityDescriptorOwner", "SetSecurityDescriptorDacl", "SetSecurityDescriptorControl", "CreateDirectoryW"]
    assert sdk.closed == sdk.freed_com == sdk.freed_local == []


@pytest.mark.parametrize("api", ["InitializeAcl", "AddAccessAllowedAceEx", "InitializeSecurityDescriptor", "SetSecurityDescriptorOwner", "SetSecurityDescriptorDacl", "SetSecurityDescriptorControl", "CreateDirectoryW"])
def test_sdk_creation_api_refusal_never_advances_or_rewrites_existing_acl(sdk, api):
    sdk.creation(api)
    with refused(sdk, "native-private-storage-refused"):
        sdk.native.create_private_directory(DIRECTORY_PATH, USER)
    order = ["InitializeAcl", "AddAccessAllowedAceEx", "InitializeSecurityDescriptor", "SetSecurityDescriptorOwner", "SetSecurityDescriptorDacl", "SetSecurityDescriptorControl", "CreateDirectoryW"]
    assert sdk.names == order[:order.index(api) + 1] and sdk.created == []
    assert sdk.closed == sdk.freed_com == sdk.freed_local == []


@pytest.mark.parametrize("user", [None, "sid", b"", bytes([2]) + USER[1:]])
def test_sdk_creation_invalid_sid_refuses_before_any_security_or_directory_api(sdk, user):
    with refused(sdk, "invalid-sid-shape"):
        sdk.native.create_private_directory(DIRECTORY_PATH, user)
    assert sdk.calls == [] and sdk.arena.regions == []


def test_sdk_information_identity_retains_volume_index_attributes_and_link_count(sdk):
    sdk.information()
    assert sdk.native.identity(77) == ((7, 23, 29), 0x10, 1)
    assert sdk.names == ["GetFileInformationByHandle"] and sdk.closed == []


def test_sdk_information_failure_refuses_without_closing_borrowed_handle(sdk):
    sdk.information(success=False)
    with refused(sdk, "native-private-storage-refused"):
        sdk.native.identity(77)
    assert sdk.names == ["GetFileInformationByHandle"] and sdk.closed == []


@pytest.mark.parametrize("revision,kinds,size", [(2, (0,), 128), (4, (0, 1), 128), (2, (0,), 65536)], ids=["acl-revision2-one-allow", "acl-revision4-allow-deny", "maximum-descriptor"])
def test_sdk_snapshot_parses_bounded_owner_and_aces_and_frees_local_descriptor(sdk, revision, kinds, size):
    sdk.snapshot(acl_revision=revision, kinds=kinds, descriptor_size=size)
    observed = sdk.native.snapshot(77)
    assert (observed.identity, observed.attributes, observed.links, observed.owner, observed.control) == ((7, 23, 29), 0x10, 1, USER, 0x1004)
    assert tuple((ace.kind, ace.flags, ace.mask, ace.sid) for ace in observed.aces) == tuple((kind, 3, 0x001F01FF, USER) for kind in kinds)
    assert observed.descriptor_sha256 == hashlib.sha256(sdk.descriptor_bytes).hexdigest()
    assert sdk.security_allocations == sdk.freed_local == [sdk.descriptor_address]
    assert [args[1] for name, args in sdk.calls if name == "GetAce"] == list(range(len(kinds)))
    assert sdk.names[-1] == "LocalFree" and sdk.closed == sdk.freed_com == []


SNAPSHOT_REFUSALS = [
    ("information-api", "native-private-storage-refused", "GetFileInformationByHandle", False),
    ("volume-api", "native-private-storage-refused", "GetVolumeInformationByHandleW", False),
    ("volume-flags", "persistent-local-acl-required", "GetVolumeInformationByHandleW", False),
    ("volume-name", "persistent-local-acl-required", "GetVolumeInformationByHandleW", False),
    ("volume-serial", "persistent-local-acl-required", "GetVolumeInformationByHandleW", False),
    ("security-api", "native-security-descriptor-refused", "GetSecurityInfo", False),
    ("security-null", "native-security-descriptor-refused", "GetSecurityInfo", False),
    ("descriptor-invalid", "native-private-storage-refused", "IsValidSecurityDescriptor", True),
    ("descriptor-small", "native-security-descriptor-bound", "GetSecurityDescriptorLength", True),
    ("descriptor-large", "native-security-descriptor-bound", "GetSecurityDescriptorLength", True),
    ("control-api", "native-private-storage-refused", "GetSecurityDescriptorControl", True),
    ("owner-api", "native-private-storage-refused", "GetSecurityDescriptorOwner", True),
    ("owner-defaulted", "native-defaulted-owner-refused", "GetSecurityDescriptorOwner", True),
    ("owner-low", "native-sid-out-of-bound", "GetSecurityDescriptorOwner", True),
    ("owner-high", "native-sid-out-of-bound", "GetSecurityDescriptorOwner", True),
    ("dacl-api", "native-private-storage-refused", "GetSecurityDescriptorDacl", True),
    ("dacl-absent", "missing-or-null-dacl", "GetSecurityDescriptorDacl", True),
    ("dacl-null", "missing-or-null-dacl", "GetSecurityDescriptorDacl", True),
    ("dacl-defaulted", "missing-or-null-dacl", "GetSecurityDescriptorDacl", True),
    ("dacl-low", "missing-or-null-dacl", "GetSecurityDescriptorDacl", True),
    ("dacl-high", "missing-or-null-dacl", "GetSecurityDescriptorDacl", True),
    ("acl-revision", "native-acl-bound", "GetSecurityDescriptorDacl", True),
    ("acl-short", "native-acl-bound", "GetSecurityDescriptorDacl", True),
    ("acl-outside", "native-acl-bound", "GetSecurityDescriptorDacl", True),
    ("acl-empty", "native-acl-bound", "GetSecurityDescriptorDacl", True),
    ("acl-many", "native-acl-bound", "GetSecurityDescriptorDacl", True),
    ("usage-api", "native-private-storage-refused", "GetAclInformation", True),
    ("usage-count", "native-acl-bound", "GetAclInformation", True),
    ("usage-small", "native-acl-bound", "GetAclInformation", True),
    ("usage-large", "native-acl-bound", "GetAclInformation", True),
    ("usage-free", "native-acl-bound", "GetAclInformation", True),
    ("ace-api", "native-private-storage-refused", "GetAce", True),
    ("ace-pointer", "native-ace-bound", "GetAce", True),
    ("ace-header-outside", "native-ace-bound", "GetAce", True),
    ("ace-kind", "unsupported-ace", "GetAce", True),
    ("ace-short", "unsupported-ace", "GetAce", True),
    ("ace-outside", "unsupported-ace", "GetAce", True),
    ("sid-revision", "native-sid-out-of-bound", "GetAce", True),
    ("sid-count", "native-sid-out-of-bound", "GetAce", True),
    ("sid-api", "native-private-storage-refused", "IsValidSid", True),
    ("sid-length", "native-sid-out-of-bound", "GetLengthSid", True),
    ("ace-padding", "native-ace-bound", "GetLengthSid", True),
    ("acl-unconsumed", "native-acl-bound", "GetLengthSid", True),
]


@pytest.mark.parametrize("fault,code,last_api,allocated", SNAPSHOT_REFUSALS, ids=[row[0] for row in SNAPSHOT_REFUSALS])
def test_sdk_snapshot_refusals_stop_before_later_metadata_and_free_owned_allocation(sdk, fault, code, last_api, allocated):
    sdk.snapshot(fault)
    with refused(sdk, code):
        sdk.native.snapshot(77)
    if allocated:
        assert sdk.names[-2:] == [last_api, "LocalFree"]
    else:
        assert sdk.names[-1:] == [last_api]
    assert sdk.freed_local == ([sdk.descriptor_address] if allocated else [])
    assert sdk.security_allocations == sdk.freed_local
    assert sdk.closed == sdk.freed_com == []


def test_sdk_snapshot_local_free_failure_is_a_fixed_refusal_without_duplicate_release(sdk):
    sdk.snapshot("release-api")
    with refused(sdk, "native-descriptor-release-refused"):
        sdk.native.snapshot(77)
    assert sdk.names.count("LocalFree") == 1 and sdk.names[-1] == "LocalFree"
    assert sdk.security_allocations == [sdk.descriptor_address] and sdk.freed_local == []


@pytest.mark.parametrize("error", [RuntimeError, KeyboardInterrupt])
def test_sdk_snapshot_provider_exception_frees_owned_descriptor(sdk, error):
    sdk.snapshot()

    def fail_ace(_acl, _index, _output):
        raise error("controlled-snapshot-provider-fault")

    sdk.allow("GetAce", fail_ace)
    with pytest.raises(error, match="^controlled-snapshot-provider-fault$"):
        sdk.native.snapshot(77)
    assert sdk.names[-2:] == ["GetAce", "LocalFree"]
    assert sdk.security_allocations == sdk.freed_local == [sdk.descriptor_address]
    assert sdk.closed == []


@pytest.mark.parametrize("error", [RuntimeError, KeyboardInterrupt])
def test_sdk_known_folder_provider_exception_frees_returned_com_pointer(sdk, error):
    sdk.token()
    sdk.folder(r"C:\Data")
    query = sdk.handlers["SHGetKnownFolderPath"]

    def fail_query(*arguments):
        query(*arguments)
        raise error("controlled-folder-provider-fault")

    sdk.allow("SHGetKnownFolderPath", fail_query)
    with pytest.raises(error, match="^controlled-folder-provider-fault$"):
        sdk.native.known_folder("local")
    assert sdk.names[-2:] == ["SHGetKnownFolderPath", "CoTaskMemFree"]
    assert sdk.freed_com == sdk.folder_addresses and sdk.closed == [101]


@pytest.mark.parametrize("descriptor,handle", [(0, 0), (3, 137)])
def test_sdk_descriptor_handle_queries_exact_crt_descriptor_and_borrows_handle(sdk, descriptor, handle):
    sdk.crt_result = handle
    assert sdk.module.descriptor_handle(descriptor) == handle
    assert sdk.crt_calls == [descriptor] and sdk.calls == [] and sdk.closed == []


@pytest.mark.parametrize("platform,descriptor", [("posix", 3), ("nt", -1), ("nt", True), ("nt", "3"), ("nt", None)])
def test_sdk_descriptor_handle_invalid_request_never_reaches_crt(sdk, platform, descriptor):
    sdk.os.name = platform
    with refused(sdk, "native-descriptor-required"):
        sdk.module.descriptor_handle(descriptor)
    assert sdk.crt_calls == [] and sdk.calls == []


@pytest.mark.parametrize("handle", [-1, -2, True, "137"])
def test_sdk_descriptor_handle_refuses_invalid_crt_result_without_owning_it(sdk, handle):
    sdk.crt_result = handle
    with refused(sdk, "native-descriptor-refused"):
        sdk.module.descriptor_handle(3)
    assert sdk.crt_calls == [3] and sdk.calls == [] and sdk.closed == []


def test_sdk_descriptor_handle_preserves_crt_exception_without_native_side_effect(sdk):
    sdk.crt_result = OSError("controlled-crt-fault")
    with pytest.raises(OSError, match="^controlled-crt-fault$"):
        sdk.module.descriptor_handle(3)
    assert sdk.crt_calls == [3] and sdk.calls == [] and sdk.closed == []
