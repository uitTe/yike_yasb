import ctypes
import os
from ctypes.wintypes import DWORD, POINT, RECT

from PyQt6.QtCore import QObject, QTimer, pyqtSlot

from core.utils.win32.bindings.dwmapi import DwmGetWindowAttribute
from core.utils.win32.bindings.user32 import (
    GetClassName,
    GetCursorPos,
    GetForegroundWindow,
    GetWindowLong,
    GetWindowRect,
    IsIconic,
    IsWindowVisible,
    MonitorFromRect,
    MonitorFromWindow,
    SetWindowPos,
    enum_windows,
    get_window_thread_process_id,
    user32,
)
from core.utils.win32.system_function import start_menu
from core.utils.win32.utils import get_process_info
from core.utils.win32.win_key import WinKeyListener


class DockWindowController(QObject):
    def __init__(self, bars, parent=None):
        super().__init__(parent)
        self._bars = bars
        self._revealed = None
        self._desktop_visible = False
        self._foreground = GetForegroundWindow()
        self._listener = WinKeyListener(self)
        self._listener.pressed.connect(self._on_win_key)
        self._listener.mouse_pressed.connect(self._on_mouse_pressed)
        self._listener.failed.connect(self._fail)
        self._timer = QTimer(self)
        self._timer.setInterval(80)
        self._timer.timeout.connect(self._sync)

    def start(self):
        self._lower()
        self._timer.start()
        self._listener.start()

    def stop(self):
        self._timer.stop()
        self._listener.stop()

    @pyqtSlot(str)
    def _fail(self, message):
        raise RuntimeError(message)

    @staticmethod
    def _position(bar, after):
        if not SetWindowPos(int(bar.winId()), after, 0, 0, 0, 0, 0x13):
            raise ctypes.WinError(ctypes.get_last_error())

    def _lower(self):
        docks = {int(bar.winId()) for bar in self._bars}
        anchor = -2
        for hwnd in enum_windows():
            if hwnd in docks or not IsWindowVisible(hwnd) or IsIconic(hwnd):
                continue
            cloaked = DWORD()
            if DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) == 0 and cloaked.value:
                continue
            if GetClassName(hwnd) in {"Progman", "WorkerW"}:
                break
            if not GetWindowLong(hwnd, -20) & 8:
                anchor = hwnd
        # 显示桌面会抬高桌面窗口；Dock 保持在桌面之前及可见应用之后。
        for bar in self._bars:
            self._position(bar, anchor)
            anchor = int(bar.winId())
        self._revealed = None

    def _desktop_covered_bars(self):
        rectangles = []
        for hwnd in enum_windows():
            if not IsWindowVisible(hwnd) or IsIconic(hwnd):
                continue
            if GetClassName(hwnd) in {"Progman", "WorkerW"}:
                break
            if get_window_thread_process_id(hwnd)[1] == os.getpid() or GetWindowLong(hwnd, -20) & 0x20:
                continue
            cloaked = DWORD()
            if DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) == 0 and cloaked.value:
                continue
            rect = RECT()
            if GetWindowRect(hwnd, ctypes.byref(rect)):
                rectangles.append(rect)
        covered = set()
        for bar in self._bars:
            rect = RECT()
            if not GetWindowRect(int(bar.winId()), ctypes.byref(rect)):
                raise ctypes.WinError(ctypes.get_last_error())
            if any(
                rect.left < other.right
                and rect.right > other.left
                and rect.top < other.bottom
                and rect.bottom > other.top
                for other in rectangles
            ):
                covered.add(int(bar.winId()))
        return covered

    @staticmethod
    def _shell_panel(hwnd):
        return (get_process_info(hwnd)["name"] or "").lower() in {
            "startmenuexperiencehost.exe",
            "searchhost.exe",
            "shellexperiencehost.exe",
        }

    def _active_bar(self):
        foreground = GetForegroundWindow()
        if GetClassName(foreground) in {"Progman", "WorkerW"}:
            x, y = GetCursorPos()
            monitor = MonitorFromRect((x, y, x + 1, y + 1), 2)
        else:
            monitor = MonitorFromWindow(foreground)
        return next((bar for bar in self._bars if MonitorFromWindow(int(bar.winId())) == monitor), self._bars[0])

    @staticmethod
    def _unobstructed(bar, allow_desktop=False):
        hwnd = int(bar.winId())
        rect = RECT()
        if not GetWindowRect(hwnd, ctypes.byref(rect)):
            raise ctypes.WinError(ctypes.get_last_error())
        # 检查透明 Dock 的原生接收窗口，兼容部分覆盖和不同屏幕缩放。
        step = max(1, round(8 * bar.devicePixelRatioF()))
        for x in range(rect.left + 1, rect.right - 1, step):
            for y in range(rect.top + 1, rect.bottom - 1, step):
                hit = user32.WindowFromPoint(POINT(x, y))
                root = user32.GetAncestor(hit, 2)
                if root != hwnd and not (allow_desktop and GetClassName(root) in {"Progman", "WorkerW"}):
                    return False
        return True

    @pyqtSlot()
    def _on_win_key(self):
        self._sync()
        if self._shell_panel(GetForegroundWindow()):
            start_menu()
            return
        bar = self._revealed or self._active_bar()
        if self._unobstructed(bar):
            start_menu(int(bar.winId()))
            return
        self._lower()
        self._foreground = GetForegroundWindow()
        self._position(bar, -1)
        self._revealed = bar

    @pyqtSlot(int, int)
    def _on_mouse_pressed(self, x, y):
        if self._revealed is not None:
            hit = user32.WindowFromPoint(POINT(x, y))
            _, pid = get_window_thread_process_id(hit)
            if pid != os.getpid():
                self._lower()

    def _sync(self):
        foreground = GetForegroundWindow()
        _, pid = get_window_thread_process_id(foreground)
        own_window = pid == os.getpid()
        shell_panel = self._shell_panel(foreground)
        if self._revealed is None:
            if GetClassName(foreground) in {"Progman", "WorkerW"}:
                # 显示桌面期间，Windows 会把桌面窗口放在普通工具窗口之前。
                covered = self._desktop_covered_bars()
                if any(int(bar.winId()) in covered and GetWindowLong(int(bar.winId()), -20) & 8 for bar in self._bars):
                    self._lower()
                for bar in self._bars:
                    if (
                        int(bar.winId()) not in covered
                        and not GetWindowLong(int(bar.winId()), -20) & 8
                        and self._unobstructed(bar, allow_desktop=True)
                    ):
                        self._position(bar, -1)
                self._desktop_visible = True
                self._foreground = foreground
                return
            if self._desktop_visible and (not foreground or own_window or shell_panel):
                return
            self._desktop_visible = False
        if self._revealed is not None:
            application_changed = foreground and foreground != self._foreground and not own_window and not shell_panel
            if application_changed:
                self._lower()
            elif foreground == self._foreground and not self._unobstructed(self._revealed):
                self._position(self._revealed, -1)
        else:
            self._lower()
        if self._revealed is None:
            self._foreground = foreground
