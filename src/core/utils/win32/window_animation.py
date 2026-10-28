"""窗口收放期间的透明度交接与独立恢复进程。"""

import ctypes
import os
import subprocess
import sys
import uuid
from ctypes.wintypes import BYTE, DWORD, HANDLE, HWND
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QTimer

from core.utils.win32.bindings.kernel32 import CloseHandle, OpenProcess, SetEvent, WaitForSingleObject
from core.utils.win32.bindings.user32 import GetProp, GetWindowLong, SetProp, SetWindowLongPtr, enum_windows, user32
from core.utils.win32.constants import SYNCHRONIZE, WAIT_TIMEOUT
from core.utils.win32.taskbar import _event
from settings import IS_FROZEN, SCRIPT_PATH

PREFIX = "YASB.Genie."
LAYERED = 0x80000
user32.GetLayeredWindowAttributes.argtypes = [HWND, ctypes.POINTER(DWORD), ctypes.POINTER(BYTE), ctypes.POINTER(DWORD)]
user32.GetLayeredWindowAttributes.restype = ctypes.c_int
user32.SetLayeredWindowAttributes.argtypes = [HWND, DWORD, BYTE, DWORD]
user32.SetLayeredWindowAttributes.restype = ctypes.c_int
user32.RemovePropW.argtypes = [HWND, ctypes.c_wchar_p]
user32.RemovePropW.restype = HANDLE


def restore_visibility(hwnd: int, owner_pid: int | None = None) -> None:
    """只恢复本次动画保存的窗口透明度与 layered 标记。"""
    if GetProp(hwnd, PREFIX + "owner") != (os.getpid() if owner_pid is None else owner_pid):
        return
    layered = GetProp(hwnd, PREFIX + "layered") == 2
    alpha = int(GetProp(hwnd, PREFIX + "alpha") or 256) - 1
    color = int(GetProp(hwnd, PREFIX + "color") or 1) - 1
    flags = int(GetProp(hwnd, PREFIX + "flags") or 3) - 1
    user32.SetLayeredWindowAttributes(hwnd, color, alpha, flags)
    if not layered:
        SetWindowLongPtr(hwnd, -20, GetWindowLong(hwnd, -20) & ~LAYERED)
    for key in ("owner", "layered", "alpha", "color", "flags"):
        user32.RemovePropW(hwnd, PREFIX + key)


def hide_for_animation(hwnd: int) -> bool:
    """在修改窗口前保存恢复数据；受保护窗口保持系统行为。"""
    if GetProp(hwnd, PREFIX + "owner"):
        return False
    style = GetWindowLong(hwnd, -20)
    color, alpha, flags = DWORD(), BYTE(255), DWORD(2)
    if style & LAYERED and not user32.GetLayeredWindowAttributes(
        hwnd, ctypes.byref(color), ctypes.byref(alpha), ctypes.byref(flags)
    ):
        return False
    values = {"layered": bool(style & LAYERED) + 1, "alpha": alpha.value + 1,
              "color": color.value + 1, "flags": flags.value + 1, "owner": os.getpid()}
    for key, value in values.items():
        if not SetProp(hwnd, PREFIX + key, value):
            restore_visibility(hwnd)
            return False
    if not style & LAYERED:
        SetWindowLongPtr(hwnd, -20, style | LAYERED)
    if not user32.SetLayeredWindowAttributes(hwnd, color, 0, 2):
        restore_visibility(hwnd)
        return False
    return True


class VisibilityGuard:
    def __init__(self):
        name = f"Local\\YASB.Genie.{uuid.uuid4()}"
        ready = _event(name)
        command = ([str(Path(SCRIPT_PATH) / "yasb_taskbar.exe")] if IS_FROZEN
                   else [sys.executable, "-B", str(Path(SCRIPT_PATH) / "taskbar_guard.py")])
        self.process = subprocess.Popen(
            [*command, "--animation", str(os.getpid()), name], cwd=SCRIPT_PATH,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            if WaitForSingleObject(ready, 10000) != 0:
                raise RuntimeError("窗口动画恢复进程未能就绪")
        finally:
            CloseHandle(ready)


def watch_window_animations(parent_pid: int, name: str) -> int:
    """主程序退出时恢复正在交接的窗口，避免窗口保持透明。"""
    app = QCoreApplication([])
    parent = OpenProcess(SYNCHRONIZE, False, parent_pid)
    if not parent:
        raise ctypes.WinError(ctypes.get_last_error())
    ready = _event(name)
    def check():
        if WaitForSingleObject(parent, 0) != WAIT_TIMEOUT:
            for hwnd in enum_windows():
                if GetProp(hwnd, PREFIX + "owner") == parent_pid:
                    restore_visibility(hwnd, parent_pid)
            app.quit()
    timer = QTimer()
    timer.timeout.connect(check)
    timer.start(100)
    SetEvent(ready)
    try:
        return app.exec()
    finally:
        CloseHandle(parent)
        CloseHandle(ready)
