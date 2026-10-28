"""Dock 接管系统任务栏及进程退出后的状态恢复。"""

import ctypes
import logging
import os
import subprocess
import sys
import time
import uuid
from ctypes.wintypes import HANDLE
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QObject, QTimer

from core.utils.win32.bindings.kernel32 import (
    CloseHandle,
    CreateEvent,
    GetLastError,
    OpenProcess,
    SetEvent,
    WaitForMultipleObjects,
    WaitForSingleObject,
)
from core.utils.win32.bindings.shell32 import SHAppBarMessage
from core.utils.win32.bindings.user32 import (
    FindWindowEx,
    GetClassName,
    GetShellWindow,
    IsWindowVisible,
    ShowWindow,
    get_window_thread_process_id,
    user32,
)
from core.utils.win32.constants import SYNCHRONIZE, WAIT_TIMEOUT
from core.utils.win32.structs import APPBARDATA, WINEVENTPROC
from settings import IS_FROZEN, SCRIPT_PATH

TASKBAR_CLASSES = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd"}


def taskbar_windows() -> list[int]:
    shell = GetShellWindow()
    if not shell:
        return []
    _, shell_pid = get_window_thread_process_id(shell)
    windows: list[int] = []

    for class_name in TASKBAR_CLASSES:
        hwnd = 0
        while hwnd := FindWindowEx(0, hwnd, class_name, None):
            _, pid = get_window_thread_process_id(hwnd)
            if pid == shell_pid:
                windows.append(hwnd)
    return windows


def taskbar_state(state: int | None = None) -> int:
    primary = next((hwnd for hwnd in taskbar_windows() if GetClassName(hwnd) == "Shell_TrayWnd"), 0)
    data = APPBARDATA()
    data.cbSize = ctypes.sizeof(data)
    data.hWnd = primary
    if state is not None and primary:
        data.lParam = state
        SHAppBarMessage(10, data)
    return int(SHAppBarMessage(4, data))


def _event(name: str) -> int:
    handle = CreateEvent(None, True, False, name)
    if not handle:
        raise ctypes.WinError(GetLastError())
    return handle


class WindowsTaskbarController(QObject):
    def __init__(self, parent: QObject):
        super().__init__(parent)
        self._process: subprocess.Popen | None = None
        self._ready = 0
        self._stop = 0
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._check_process)

    def start(self) -> None:
        name = f"Local\\YASB.Taskbar.{uuid.uuid4()}"
        self._ready = _event(name + ".ready")
        self._stop = _event(name + ".stop")
        command = (
            [str(Path(SCRIPT_PATH) / "yasb_taskbar.exe")]
            if IS_FROZEN
            else [sys.executable, str(Path(SCRIPT_PATH) / "taskbar_guard.py")]
        )
        self._process = subprocess.Popen(
            [*command, str(os.getpid()), name, "--restart-wait"],
            cwd=SCRIPT_PATH,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        process_handle = OpenProcess(SYNCHRONIZE, False, self._process.pid)
        if not process_handle:
            raise ctypes.WinError(GetLastError())
        try:
            result = WaitForMultipleObjects(2, (HANDLE * 2)(self._ready, process_handle), False, 15000)
            if result != 0:
                raise RuntimeError(f"系统任务栏接管进程未能就绪，等待结果：{result}")
        finally:
            CloseHandle(process_handle)
        self._timer.start()
        logging.info("Dock 已接管全部显示器的系统任务栏，恢复进程 PID：%s", self._process.pid)

    def _check_process(self) -> None:
        if self._process is not None and self._process.poll() is not None:
            raise RuntimeError(f"系统任务栏接管进程异常退出：{self._process.returncode}")

    def stop(self) -> None:
        self._timer.stop()
        try:
            if self._process is not None:
                if not SetEvent(self._stop):
                    raise ctypes.WinError(GetLastError())
                code = self._process.wait(timeout=5)
                self._process = None
                if code:
                    raise RuntimeError(f"系统任务栏恢复进程退出失败：{code}")
                logging.info("系统任务栏已恢复接管前的状态")
        finally:
            for handle in (self._ready, self._stop):
                if handle:
                    CloseHandle(handle)
            self._ready = self._stop = 0


def watch_taskbars(parent_pid: int, name: str) -> int:
    app = QCoreApplication([])
    parent_handle = OpenProcess(SYNCHRONIZE, False, parent_pid)
    if not parent_handle:
        raise ctypes.WinError(GetLastError())
    ready = _event(name + ".ready")
    stop = _event(name + ".stop")
    original_state = taskbar_state()
    visibility: dict[tuple[int, int], bool] = {}
    for hwnd in taskbar_windows():
        _, pid = get_window_thread_process_id(hwnd)
        visibility[hwnd, pid] = IsWindowVisible(hwnd)
    hook = None
    ready_sent = False
    ready_deadline = time.monotonic() + 3

    def sync() -> None:
        windows = taskbar_windows()
        if taskbar_state() & 1 == 0:
            taskbar_state(original_state | 1)
        for hwnd in windows:
            if IsWindowVisible(hwnd):
                ShowWindow(hwnd, 0)

    def tick() -> None:
        nonlocal ready_sent
        result = WaitForMultipleObjects(2, (HANDLE * 2)(parent_handle, stop), False, 0)
        if result in (0, 1):
            app.quit()
        elif result == WAIT_TIMEOUT:
            sync()
            if not ready_sent:
                if all(not IsWindowVisible(hwnd) for hwnd in taskbar_windows()):
                    if not SetEvent(ready):
                        raise ctypes.WinError(GetLastError())
                    ready_sent = True
                elif time.monotonic() >= ready_deadline:
                    raise RuntimeError("系统任务栏窗口隐藏失败")
        else:
            raise ctypes.WinError(GetLastError())

    @WINEVENTPROC
    def on_show(_hook, _event, hwnd, _object_id, _child_id, _thread, _time):
        if hwnd and GetClassName(hwnd) in TASKBAR_CLASSES:
            _, pid = get_window_thread_process_id(hwnd)
            _, shell_pid = get_window_thread_process_id(GetShellWindow())
            if pid == shell_pid:
                ShowWindow(hwnd, 0)

    def exception_hook(_kind, value, traceback) -> None:
        logging.error("系统任务栏接管失败", exc_info=(type(value), value, traceback))
        app.exit(1)

    sys.excepthook = exception_hook
    timer = QTimer()
    timer.setInterval(100)
    timer.timeout.connect(tick)
    try:
        if not taskbar_windows():
            raise RuntimeError("没有找到 Explorer 的系统任务栏窗口")
        hook = user32.SetWinEventHook(0x8002, 0x8002, 0, on_show, 0, 0, 0)
        if not hook:
            raise ctypes.WinError(GetLastError())
        sync()
        if WaitForSingleObject(parent_handle, 0) != WAIT_TIMEOUT:
            return 0
        timer.start()
        return app.exec()
    finally:
        timer.stop()
        if hook:
            user32.UnhookWinEvent(hook)
        # 恢复进程独立存活，父进程被强制结束时仍然执行此处。
        for hwnd in taskbar_windows():
            _, pid = get_window_thread_process_id(hwnd)
            ShowWindow(hwnd, 8 if visibility.get((hwnd, pid), True) else 0)
        taskbar_state(original_state)
        for handle in (parent_handle, ready, stop):
            CloseHandle(handle)
