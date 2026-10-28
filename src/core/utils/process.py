import ctypes
import subprocess
from contextlib import ExitStack
from ctypes.wintypes import HANDLE

from core.utils.win32.bindings.kernel32 import GetLastError, kernel32, snapshot_processes
from core.utils.win32.bindings.user32 import GetShellWindow, get_window_thread_process_id
from core.utils.win32.constants import (
    EXTENDED_STARTUPINFO_PRESENT,
    PROC_THREAD_ATTRIBUTE_PARENT_PROCESS,
    PROCESS_CREATE_PROCESS,
    PROCESS_TERMINATE,
)
from core.utils.win32.structs import PROCESS_INFORMATION, STARTUPINFOEXW


def start_independent_process(command: list[str]) -> int:
    """从桌面进程继承生命周期，同时保留调用方的环境变量和工作目录。"""
    if not command:
        raise ValueError("启动命令不能为空。")
    _, shell_pid = get_window_thread_process_id(GetShellWindow())
    if not shell_pid:
        raise RuntimeError("没有找到 Windows 桌面进程。")

    with ExitStack() as resources:
        parent = kernel32.OpenProcess(PROCESS_CREATE_PROCESS, False, shell_pid)
        if not parent:
            raise ctypes.WinError(GetLastError())
        resources.callback(kernel32.CloseHandle, parent)

        size = ctypes.c_size_t()
        kernel32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
        if not size.value:
            raise ctypes.WinError(GetLastError())
        attributes = ctypes.create_string_buffer(size.value)
        if not kernel32.InitializeProcThreadAttributeList(attributes, 1, 0, ctypes.byref(size)):
            raise ctypes.WinError(GetLastError())
        resources.callback(kernel32.DeleteProcThreadAttributeList, attributes)
        parent_handle = HANDLE(parent)
        if not kernel32.UpdateProcThreadAttribute(
            attributes,
            0,
            PROC_THREAD_ATTRIBUTE_PARENT_PROCESS,
            ctypes.byref(parent_handle),
            ctypes.sizeof(parent_handle),
            None,
            None,
        ):
            raise ctypes.WinError(GetLastError())

        startup = STARTUPINFOEXW(lpAttributeList=ctypes.addressof(attributes))
        startup.StartupInfo.cb = ctypes.sizeof(startup)
        process = PROCESS_INFORMATION()
        flags = EXTENDED_STARTUPINFO_PRESENT | subprocess.DETACHED_PROCESS
        if not kernel32.CreateProcessW(
            command[0],
            ctypes.create_unicode_buffer(subprocess.list2cmdline(command)),
            None,
            None,
            False,
            flags,
            None,
            None,
            ctypes.byref(startup),
            ctypes.byref(process),
        ):
            raise ctypes.WinError(GetLastError())
        resources.callback(kernel32.CloseHandle, process.hProcess)
        resources.callback(kernel32.CloseHandle, process.hThread)
        return process.dwProcessId


def is_process_running(process_name: str) -> bool:
    target = process_name.lower()
    return any(process.exe.lower() == target for process in snapshot_processes())


def terminate_process(pid: int) -> bool:
    handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if not handle:
        return False
    try:
        return bool(kernel32.TerminateProcess(handle, 1))
    finally:
        kernel32.CloseHandle(handle)
