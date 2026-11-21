"""Preserve inherited environment values between tests on Windows."""

from __future__ import annotations

import os
import sys

import pytest

if sys.platform == "win32":
    import ctypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _get_environment_variable = _kernel32.GetEnvironmentVariableW
    _get_environment_variable.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint)
    _get_environment_variable.restype = ctypes.c_uint
    _set_environment_variable = _kernel32.SetEnvironmentVariableW
    _set_environment_variable.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p)
    _set_environment_variable.restype = ctypes.c_int

    @pytest.fixture(autouse=True)
    def restore_windows_empty_environment():
        # Restoring os.environ after a test's full-environment patch uses
        # _wputenv, which deletes empty values from the Win32 process environment.
        # Preserve values that were actually present for later child processes.
        inherited_empty = [
            name for name, value in os.environ.items()
            if value == "" and _get_environment_variable(name, None, 0) == 1
        ]
        yield
        for name in inherited_empty:
            if os.environ.get(name) == "" and not _set_environment_variable(name, ""):
                raise ctypes.WinError(ctypes.get_last_error())
