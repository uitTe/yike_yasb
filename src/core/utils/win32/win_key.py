import ctypes
from ctypes.wintypes import MSG

from PyQt6.QtCore import QThread, pyqtSignal

from core.utils.win32.bindings.kernel32 import GetCurrentThreadId, GetModuleHandle
from core.utils.win32.bindings.user32 import SendInput, user32
from core.utils.win32.structs import HOOKPROC, INPUT, KBDLLHOOKSTRUCT, KEYBDINPUT, MSLLHOOKSTRUCT

WIN_KEY_INPUT_MARKER = 0x59415342
WIN_KEYS = (0x5B, 0x5C)


class WinKeyListener(QThread):
    pressed = pyqtSignal()
    mouse_pressed = pyqtSignal(int, int)
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread_id = None
        self._held: dict[int, tuple[int, int]] = {}
        self._forwarded: set[int] = set()
        self._shortcut = False
        self._other_keys: set[int] = set()
        self._replayed_keys: dict[int, tuple[int, int]] = {}
        self._callback = HOOKPROC(self._keyboard_event)
        self._mouse_callback = HOOKPROC(self._mouse_event)

    def _mouse_event(self, code, message, address):
        if code >= 0 and message in {0x201, 0x204, 0x207, 0x20B}:
            event = ctypes.cast(address, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            self.mouse_pressed.emit(event.pt.x, event.pt.y)
        return user32.CallNextHookEx(None, code, message, address)

    def _send(self, events: list[tuple[int, int, int]]) -> None:
        inputs = (INPUT * len(events))()
        for item, (key, scan, flags) in zip(inputs, events):
            item.type = 1
            item.ki = KEYBDINPUT(key, scan, flags, 0, WIN_KEY_INPUT_MARKER)
        if SendInput(inputs) != len(inputs):
            self.failed.emit("发送 Win 组合按键失败")

    def _keyboard_event(self, code, message, address):
        if code < 0:
            return user32.CallNextHookEx(None, code, message, address)
        event = ctypes.cast(address, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        if event.dwExtraInfo == WIN_KEY_INPUT_MARKER:
            return user32.CallNextHookEx(None, code, message, address)
        key = event.vkCode
        released = bool(event.flags & 0x80)
        flags = event.flags & 1
        if key in WIN_KEYS:
            if not released:
                if key not in self._held:
                    self._held[key] = (event.scanCode, flags)
                    if self._other_keys or self._shortcut:
                        self._shortcut = True
                        self._forwarded.add(key)
                        self._send([(key, event.scanCode, flags)])
            elif key in self._held:
                del self._held[key]
                if key in self._forwarded:
                    self._forwarded.remove(key)
                    self._send([(key, event.scanCode, flags | 2)])
                if not self._held:
                    if not self._shortcut:
                        self.pressed.emit()
                    self._shortcut = False
            else:
                return user32.CallNextHookEx(None, code, message, address)
            return 1
        if released:
            self._other_keys.discard(key)
            if key in self._replayed_keys or (self._held and self._shortcut):
                self._replayed_keys.pop(key, None)
                self._send([(key, event.scanCode, flags | 2)])
                return 1
        else:
            self._other_keys.add(key)
            if self._held and not self._shortcut:
                self._shortcut = True
                pending = [(vk, scan, extra) for vk, (scan, extra) in self._held.items()]
                self._forwarded.update(self._held)
                self._replayed_keys[key] = (event.scanCode, flags)
                # 同一次 SendInput 保证 Win 先于组合键进入系统输入队列。
                self._send([*pending, (key, event.scanCode, flags)])
                return 1
            if self._held or key in self._replayed_keys:
                self._replayed_keys[key] = (event.scanCode, flags)
                self._send([(key, event.scanCode, flags)])
                return 1
        return user32.CallNextHookEx(None, code, message, address)

    def run(self):
        self._thread_id = GetCurrentThreadId()
        message = MSG()
        user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
        self._other_keys = {
            key
            for key in range(8, 256)
            if key not in (*WIN_KEYS, 0x10, 0x11, 0x12) and user32.GetAsyncKeyState(key) & 0x8000
        }
        hook = user32.SetWindowsHookExW(13, self._callback, GetModuleHandle(None), 0)
        if not hook:
            self.failed.emit(f"安装 Win 键监听失败：{ctypes.get_last_error()}")
            return
        mouse_hook = user32.SetWindowsHookExW(14, self._mouse_callback, GetModuleHandle(None), 0)
        if not mouse_hook:
            user32.UnhookWindowsHookEx(hook)
            self.failed.emit(f"安装 Dock 鼠标监听失败：{ctypes.get_last_error()}")
            return
        try:
            while True:
                if self.isInterruptionRequested():
                    return
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result == -1:
                    self.failed.emit(f"Win 键消息读取失败：{ctypes.get_last_error()}")
                    return
                if result == 0:
                    return
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        finally:
            user32.UnhookWindowsHookEx(mouse_hook)
            user32.UnhookWindowsHookEx(hook)
            if self._forwarded:
                self._send([(key, self._held[key][0], self._held[key][1] | 2) for key in self._forwarded])
            if self._replayed_keys:
                self._send([(key, scan, flags | 2) for key, (scan, flags) in self._replayed_keys.items()])

    def stop(self):
        self.requestInterruption()
        if self._thread_id is not None:
            if not user32.PostThreadMessageW(self._thread_id, 0x12, 0, 0):
                raise ctypes.WinError(ctypes.get_last_error())
        if not self.wait(3000):
            raise RuntimeError("Win 键监听未按时退出")
