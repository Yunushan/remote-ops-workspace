from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import subprocess
import time
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path


def utc():
    return datetime.now(timezone.utc).isoformat()


MAX_TIMEOUT_SECONDS = 3600


def validate_timeout(timeout):
    if type(timeout) is not int or not 1 <= timeout <= MAX_TIMEOUT_SECONDS:
        raise ValueError(f"timeout must be an integer from 1 to {MAX_TIMEOUT_SECONDS} seconds")
    return timeout


def timeout_argument(value):
    try:
        return validate_timeout(int(value))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def owned_result_succeeded(evidence):
    return (
        evidence.get("child_created") is True
        and evidence.get("job_assigned") is True
        and evidence.get("wait_result") == 0
        and evidence.get("exit_code") == 0
        and evidence.get("owned_parent_cleanup_wait") == 0
        and evidence.get("active_owned_processes_after_cleanup") == 0
        and evidence.get("job_closed") is True
        and not evidence.get("error")
        and evidence.get("cleanup_errors") == []
    )


class BasicLimits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_int64),
        ("job_time", ctypes.c_int64),
        ("flags", wintypes.DWORD),
        ("min_working_set", ctypes.c_size_t),
        ("max_working_set", ctypes.c_size_t),
        ("active_limit", wintypes.DWORD),
        ("affinity", ctypes.c_size_t),
        ("priority", wintypes.DWORD),
        ("scheduling", wintypes.DWORD),
    ]


class IoCounters(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_uint64)
        for name in (
            "read_operations",
            "write_operations",
            "other_operations",
            "read_bytes",
            "write_bytes",
            "other_bytes",
        )
    ]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("basic", BasicLimits),
        ("io", IoCounters),
        ("process_memory", ctypes.c_size_t),
        ("job_memory", ctypes.c_size_t),
        ("peak_process_memory", ctypes.c_size_t),
        ("peak_job_memory", ctypes.c_size_t),
    ]


class StartupInfo(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("reserved", wintypes.LPWSTR),
        ("desktop", wintypes.LPWSTR),
        ("title", wintypes.LPWSTR),
        ("x", wintypes.DWORD),
        ("y", wintypes.DWORD),
        ("xsize", wintypes.DWORD),
        ("ysize", wintypes.DWORD),
        ("xchars", wintypes.DWORD),
        ("ychars", wintypes.DWORD),
        ("fill", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("show", wintypes.WORD),
        ("reserved_bytes", wintypes.WORD),
        ("reserved_pointer", ctypes.POINTER(ctypes.c_byte)),
        ("stdin", wintypes.HANDLE),
        ("stdout", wintypes.HANDLE),
        ("stderr", wintypes.HANDLE),
    ]


class ProcessInformation(ctypes.Structure):
    _fields_ = [
        ("process", wintypes.HANDLE),
        ("thread", wintypes.HANDLE),
        ("pid", wintypes.DWORD),
        ("tid", wintypes.DWORD),
    ]


class Accounting(ctypes.Structure):
    _fields_ = [
        ("user_time", ctypes.c_int64),
        ("kernel_time", ctypes.c_int64),
        ("user_period", ctypes.c_int64),
        ("kernel_period", ctypes.c_int64),
        ("page_faults", wintypes.DWORD),
        ("total", wintypes.DWORD),
        ("active", wintypes.DWORD),
        ("terminated", wintypes.DWORD),
    ]


def run_owned(executable, cli_arguments, env, output, timeout):
    validate_timeout(timeout)
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    declarations = {
        "CreateFileW": (
            [
                wintypes.LPCWSTR,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.c_void_p,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.HANDLE,
            ],
            wintypes.HANDLE,
        ),
        "CreateJobObjectW": ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
        "SetInformationJobObject": (
            [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD],
            wintypes.BOOL,
        ),
        "AssignProcessToJobObject": ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
        "QueryInformationJobObject": (
            [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p],
            wintypes.BOOL,
        ),
        "TerminateJobObject": ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
        "CreateProcessW": (
            [
                wintypes.LPCWSTR,
                wintypes.LPWSTR,
                ctypes.c_void_p,
                ctypes.c_void_p,
                wintypes.BOOL,
                wintypes.DWORD,
                ctypes.c_void_p,
                wintypes.LPCWSTR,
                ctypes.POINTER(StartupInfo),
                ctypes.POINTER(ProcessInformation),
            ],
            wintypes.BOOL,
        ),
        "ResumeThread": ([wintypes.HANDLE], wintypes.DWORD),
        "WaitForSingleObject": ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        "GetExitCodeProcess": ([wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
        "TerminateProcess": ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
        "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
    }
    for name, (arguments, result_type) in declarations.items():
        getattr(api, name).argtypes = arguments
        getattr(api, name).restype = result_type
    evidence = {
        "started_at_utc": utc(),
        "argv": [str(executable), *cli_arguments],
        "start_hidden": True,
        "start_suspended": True,
        "kill_on_job_close": True,
        "timeout_seconds": timeout,
        "child_created": False,
        "job_assigned": False,
        "cleanup_errors": [],
    }
    job = None
    information = ProcessInformation()
    output_handle = input_handle = None
    try:
        job = api.CreateJobObjectW(None, None)
        if not job:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000
        if not api.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise ctypes.WinError(ctypes.get_last_error())
        startup = StartupInfo()
        startup.cb = ctypes.sizeof(startup)

        class SecurityAttributes(ctypes.Structure):
            _fields_ = [
                ("size", wintypes.DWORD),
                ("descriptor", ctypes.c_void_p),
                ("inherit", wintypes.BOOL),
            ]

        security = SecurityAttributes(ctypes.sizeof(SecurityAttributes), None, True)
        output_handle = api.CreateFileW(
            str(output.with_suffix(".log")), 0x40000000, 3, ctypes.byref(security), 2, 0x80, None
        )
        input_handle = api.CreateFileW("NUL", 0x80000000, 3, ctypes.byref(security), 3, 0x80, None)
        if output_handle in (None, ctypes.c_void_p(-1).value) or input_handle in (
            None,
            ctypes.c_void_p(-1).value,
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        startup.stdin = input_handle
        startup.stdout = startup.stderr = output_handle
        startup.flags = 0x00000001 | 0x00000100
        startup.show = 0
        command = ctypes.create_unicode_buffer(subprocess.list2cmdline(evidence["argv"]))
        environment = ctypes.create_unicode_buffer(
            "\0".join(
                key + "=" + value
                for key, value in sorted(env.items(), key=lambda item: item[0].upper())
            )
            + "\0\0"
        )
        if not api.CreateProcessW(
            str(executable),
            command,
            None,
            None,
            True,
            0x08000000 | 0x00000004 | 0x00000400,
            ctypes.cast(environment, ctypes.c_void_p),
            str(Path.cwd()),
            ctypes.byref(startup),
            ctypes.byref(information),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        evidence.update({"child_created": True, "pid": information.pid})
        if not api.AssignProcessToJobObject(job, information.process):
            raise ctypes.WinError(ctypes.get_last_error())
        evidence["job_assigned"] = True
        if api.ResumeThread(information.thread) == 0xFFFFFFFF:
            raise ctypes.WinError(ctypes.get_last_error())
        waited = api.WaitForSingleObject(information.process, timeout * 1000)
        evidence["wait_result"] = waited
        if waited != 0:
            if waited == 258:
                raise TimeoutError("owned command exceeded its bounded timeout")
            raise ctypes.WinError(ctypes.get_last_error())
        exit_code = wintypes.DWORD()
        if not api.GetExitCodeProcess(information.process, ctypes.byref(exit_code)):
            raise ctypes.WinError(ctypes.get_last_error())
        evidence["exit_code"] = exit_code.value
    except Exception as exc:
        evidence["error"] = f"{type(exc).__name__}: {exc}"
        evidence["winerror"] = getattr(exc, "winerror", None)
    finally:
        if information.process:
            if evidence["job_assigned"]:
                accounting = Accounting()
                if api.QueryInformationJobObject(
                    job, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None
                ):
                    evidence["active_owned_processes_before_cleanup"] = accounting.active
                    if accounting.active and not api.TerminateJobObject(job, 1):
                        evidence["cleanup_errors"].append(
                            f"TerminateJobObject: {ctypes.get_last_error()}"
                        )
                    deadline = time.monotonic() + 5
                    while accounting.active and time.monotonic() < deadline:
                        time.sleep(0.02)
                        if not api.QueryInformationJobObject(
                            job, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None
                        ):
                            evidence["cleanup_errors"].append(
                                f"QueryInformationJobObject: {ctypes.get_last_error()}"
                            )
                            break
                    evidence["active_owned_processes_after_cleanup"] = accounting.active
                    if accounting.active:
                        evidence["cleanup_errors"].append(
                            "owned processes remain after bounded cleanup"
                        )
                else:
                    evidence["cleanup_errors"].append(
                        f"QueryInformationJobObject: {ctypes.get_last_error()}"
                    )
                    if not api.TerminateJobObject(job, 1):
                        evidence["cleanup_errors"].append(
                            f"TerminateJobObject: {ctypes.get_last_error()}"
                        )
            else:
                state = api.WaitForSingleObject(information.process, 0)
                if state != 0:
                    if state != 258:
                        evidence["cleanup_errors"].append(
                            f"unassigned owned process state query: {state}"
                        )
                    if not api.TerminateProcess(information.process, 1):
                        evidence["cleanup_errors"].append(
                            f"TerminateProcess: {ctypes.get_last_error()}"
                        )
            evidence["owned_parent_cleanup_wait"] = api.WaitForSingleObject(
                information.process, 5000
            )
            if evidence["owned_parent_cleanup_wait"] != 0:
                evidence["cleanup_errors"].append(
                    f"owned parent cleanup wait: {evidence['owned_parent_cleanup_wait']}"
                )
            if not api.CloseHandle(information.process):
                evidence["cleanup_errors"].append(
                    f"CloseHandle(process): {ctypes.get_last_error()}"
                )
        if information.thread:
            if not api.CloseHandle(information.thread):
                evidence["cleanup_errors"].append(f"CloseHandle(thread): {ctypes.get_last_error()}")
        if job:
            evidence["job_closed"] = bool(api.CloseHandle(job))
            if not evidence["job_closed"]:
                evidence["cleanup_errors"].append(f"CloseHandle(job): {ctypes.get_last_error()}")
        for standard_handle in (output_handle, input_handle):
            if standard_handle and standard_handle != ctypes.c_void_p(-1).value:
                if not api.CloseHandle(standard_handle):
                    evidence["cleanup_errors"].append(
                        f"CloseHandle(stdio): {ctypes.get_last_error()}"
                    )
        evidence["finished_at_utc"] = utc()
    evidence["success"] = owned_result_succeeded(evidence)
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Bounded Windows Job Object ownership for candidate validation only"
    )
    parser.add_argument("--timeout", type=timeout_argument, default=1200)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if os.name != "nt":
        raise RuntimeError("native Windows required")
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command executable is required")
    executable = shutil.which(command[0])
    if not executable:
        raise RuntimeError("command executable missing")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    result = run_owned(Path(executable), command[1:], os.environ.copy(), args.out, args.timeout)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if owned_result_succeeded(result) else 1)
