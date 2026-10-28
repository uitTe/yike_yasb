"""验证真实 Windows 作业对象终止后的独立进程生命周期。"""

import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes.wintypes import BOOL, DWORD, HANDLE, LPCWSTR, LPVOID
from pathlib import Path

import psutil

from core.utils.win32.bindings.kernel32 import kernel32
from core.utils.win32.structs import PROCESS_INFORMATION, STARTUPINFOW

kernel32.CreateJobObjectW.argtypes = [LPVOID, LPCWSTR]
kernel32.CreateJobObjectW.restype = HANDLE
kernel32.AssignProcessToJobObject.argtypes = [HANDLE, HANDLE]
kernel32.AssignProcessToJobObject.restype = BOOL
kernel32.TerminateJobObject.argtypes = [HANDLE, DWORD]
kernel32.TerminateJobObject.restype = BOOL
kernel32.IsProcessInJob.argtypes = [HANDLE, HANDLE, ctypes.POINTER(BOOL)]
kernel32.IsProcessInJob.restype = BOOL
kernel32.ResumeThread.argtypes = [HANDLE]
kernel32.ResumeThread.restype = DWORD


def test_independent_process_survives_job_termination(tmp_path: Path) -> None:
    job = kernel32.CreateJobObjectW(None, None)
    assert job, ctypes.WinError()
    process = PROCESS_INFORMATION()
    startup = STARTUPINFOW()
    startup.cb = ctypes.sizeof(startup)
    helper = Path(__file__).parent / "support" / "process_lifetime_child.py"
    arguments = ["中文 参数", '双引号"参数', "", "结尾反斜线\\"]
    command = [sys.executable, str(helper), "launcher", str(tmp_path), *arguments]
    previous = os.environ.get("YASB_LIFETIME_TEST")
    os.environ["YASB_LIFETIME_TEST"] = "保留环境变量 中文 空格"
    independent_pid = 0
    try:
        assert kernel32.CreateProcessW(
            sys.executable,
            ctypes.create_unicode_buffer(subprocess.list2cmdline(command)),
            None,
            None,
            False,
            0x00000004 | subprocess.CREATE_NO_WINDOW,
            None,
            str(tmp_path),
            ctypes.byref(startup),
            ctypes.byref(process),
        ), ctypes.WinError()
        assert kernel32.AssignProcessToJobObject(job, process.hProcess), ctypes.WinError()
        assert kernel32.ResumeThread(process.hThread) != 0xFFFFFFFF, ctypes.WinError()

        deadline = time.monotonic() + 25
        while not all((tmp_path / f"{name}.json").exists() for name in ("launcher", "normal", "independent")):
            assert time.monotonic() < deadline, "验证进程没有按时启动。"
            time.sleep(0.05)
        normal = json.loads((tmp_path / "normal.json").read_text(encoding="utf-8"))
        independent = json.loads((tmp_path / "independent.json").read_text(encoding="utf-8"))
        independent_pid = independent["pid"]
        for details, expected in ((normal, True), (independent, False)):
            handle = kernel32.OpenProcess(0x1000, False, details["pid"])
            assert handle, ctypes.WinError()
            try:
                belongs = BOOL()
                assert kernel32.IsProcessInJob(handle, job, ctypes.byref(belongs)), ctypes.WinError()
                assert bool(belongs.value) is expected
            finally:
                kernel32.CloseHandle(handle)
        assert independent["arguments"] == arguments
        assert independent["environment"] == os.environ["YASB_LIFETIME_TEST"]
        assert Path(independent["cwd"]) == tmp_path

        assert kernel32.TerminateJobObject(job, 1), ctypes.WinError()
        assert kernel32.WaitForSingleObject(process.hProcess, 5000) == 0
        if psutil.pid_exists(normal["pid"]):
            psutil.Process(normal["pid"]).wait(timeout=5)
        assert psutil.Process(independent_pid).is_running()
    finally:
        kernel32.TerminateJobObject(job, 1)
        if independent_pid and psutil.pid_exists(independent_pid):
            child = psutil.Process(independent_pid)
            child.terminate()
            child.wait(timeout=5)
        for handle in (process.hThread, process.hProcess, job):
            if handle:
                kernel32.CloseHandle(handle)
        if previous is None:
            os.environ.pop("YASB_LIFETIME_TEST", None)
        else:
            os.environ["YASB_LIFETIME_TEST"] = previous
