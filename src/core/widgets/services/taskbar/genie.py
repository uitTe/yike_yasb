"""使用 DWM 实时画面实现连接顶部页签的双向弯曲动画。"""

import ctypes
import logging
from ctypes.wintypes import HANDLE, RECT

from PyQt6.QtCore import QElapsedTimer, QObject, Qt, QTimer
from PyQt6.QtWidgets import QApplication, QWidget

from core.utils.win32.bindings.dwmapi import (
    DwmQueryThumbnailSourceSize,
    DwmRegisterThumbnail,
    DwmUnregisterThumbnail,
    DwmUpdateThumbnailProperties,
)
from core.utils.win32.bindings.user32 import (
    GetMonitorInfo,
    GetWindowRect,
    IsIconic,
    IsWindow,
    MonitorFromWindow,
    user32,
)
from core.utils.win32.structs import DWM_THUMBNAIL_PROPERTIES, SIZE
from core.utils.win32.structs import RECT as DwmRect
from core.utils.win32.window_animation import VisibilityGuard, hide_for_animation, restore_visibility

logger = logging.getLogger(__name__)


def smooth(value: float) -> float:
    value = min(1.0, max(0.0, value))
    return value * value * (3 - 2 * value)


def strip_rect(source: RECT, target: RECT, progress: float, row: float, next_row: float) -> DwmRect:
    """上缘先收窄，下缘随后沿曲线进入页签；还原使用相反进度。"""
    neck = smooth(progress / 0.55)
    collapse = smooth((progress - 0.25) / 0.75)
    bend = collapse + (1 - collapse) * neck * (1 - (row + next_row) / 2) ** 2
    top = source.top + (target.top - source.top) * neck
    bottom = source.bottom + (target.bottom - source.bottom) * collapse
    left = round(source.left + (target.left - source.left) * bend)
    right = round(source.right + (target.right - source.right) * bend)
    y = round(top + (bottom - top) * row)
    return DwmRect(left, y, max(left + 1, right), max(y + 1, round(top + (bottom - top) * next_row)))


class GenieOverlay(QWidget):
    DURATION = 420
    STRIPS = 192

    def __init__(self, hwnd: int, source: RECT, target: RECT, minimizing: bool):
        super().__init__()
        self.hwnd = hwnd
        self.minimizing = minimizing
        self.source = source
        self.target = target
        self.handles = []
        self.frames = 0
        self.progress = 0.0 if minimizing else 1.0
        self.start_progress = self.progress
        self.duration = self.DURATION
        self.setWindowTitle("YASB 窗口收放动画")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus
                            | Qt.WindowType.WindowTransparentForInput | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.left = min(source.left, target.left)
        self.top = min(source.top, target.top)
        self.physical_width = max(source.right, target.right) - self.left
        self.physical_height = max(source.bottom, target.bottom) - self.top
        native = int(self.winId())
        monitor = GetMonitorInfo(MonitorFromWindow(hwnd, 2))
        screen = next(screen for screen in QApplication.screens()
                      if (screen.geometry().x(), screen.geometry().y()) == (monitor.rcMonitor.left, monitor.rcMonitor.top))
        self.windowHandle().setScreen(screen)
        scale = screen.devicePixelRatio()
        self.setGeometry(screen.geometry().x() + round((self.left - monitor.rcMonitor.left) / scale),
                         screen.geometry().y() + round((self.top - monitor.rcMonitor.top) / scale),
                         round(self.physical_width / scale), round(self.physical_height / scale))
        self.size = SIZE()
        for _ in range(self.STRIPS):
            handle = HANDLE()
            result = DwmRegisterThumbnail(native, hwnd, ctypes.byref(handle))
            if result:
                self.finish()
                raise OSError(result, "无法注册窗口动画画面")
            self.handles.append(handle)
        result = DwmQueryThumbnailSourceSize(self.handles[0], ctypes.byref(self.size))
        if result:
            self.finish()
            raise OSError(result, "无法获取窗口动画尺寸")
        self.clock = QElapsedTimer()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(8)
        self.timer.timeout.connect(self.tick)

    def begin(self):
        self.render(0.0 if self.minimizing else 1.0)
        self.show()
        # 显示后校正到物理像素，处理不同 DPI 下的奇数尺寸。
        user32.SetWindowPos(int(self.winId()), -1, self.left, self.top,
                            self.physical_width, self.physical_height, 0x10)
        self.clock.start()
        self.timer.start()

    def render(self, progress: float):
        self.progress = progress
        for index, handle in enumerate(self.handles):
            row, next_row = index / self.STRIPS, (index + 1) / self.STRIPS
            dest = strip_rect(self.source, self.target, progress, row, next_row)
            props = DWM_THUMBNAIL_PROPERTIES()
            props.dwFlags = 1 | 2 | 4 | 8 | 16
            props.rcDestination = DwmRect(dest.left - self.left, dest.top - self.top,
                                          dest.right - self.left, dest.bottom - self.top)
            props.rcSource = DwmRect(0, round(self.size.cy * row), self.size.cx, round(self.size.cy * next_row))
            props.opacity = round(255 * (1 - smooth((progress - 0.92) / 0.08)))
            props.fVisible = True
            props.fSourceClientAreaOnly = False
            result = DwmUpdateThumbnailProperties(handle, ctypes.byref(props))
            if result:
                self.finish()
                if not IsWindow(self.hwnd):
                    return
                raise OSError(result, "无法绘制窗口动画")
        self.frames += 1

    def tick(self):
        if not IsWindow(self.hwnd):
            self.finish()
            return
        progress = min(1.0, self.clock.elapsed() / self.duration)
        end = 1.0 if self.minimizing else 0.0
        self.render(self.start_progress + (end - self.start_progress) * progress)
        if progress == 1:
            self.finish()

    def reverse(self, minimizing: bool):
        self.minimizing = minimizing
        self.start_progress = self.progress
        end = 1.0 if minimizing else 0.0
        self.duration = max(60, round(abs(end - self.progress) * self.DURATION))
        self.clock.restart()

    def finish(self):
        if hasattr(self, "timer"):
            self.timer.stop()
        restore_visibility(self.hwnd)
        self.hide()
        for handle in self.handles:
            DwmUnregisterThumbnail(handle)
        self.handles.clear()
        logger.debug("窗口动画完成 hwnd=%s minimizing=%s frames=%s", self.hwnd, self.minimizing, self.frames)
        self.deleteLater()


class GenieAnimator(QObject):
    def __init__(self, parent: QObject):
        super().__init__(parent)
        self.bounds: dict[int, RECT] = {}
        self.active: dict[int, GenieOverlay] = {}
        self.pending: dict[int, tuple[RECT, RECT, bool]] = {}
        self.guard = VisibilityGuard()
        QApplication.instance().aboutToQuit.connect(self.stop)

    def remember(self, hwnd: int):
        if not IsIconic(hwnd) and hwnd not in self.active and hwnd not in self.pending:
            rect = RECT()
            if GetWindowRect(hwnd, ctypes.byref(rect)) and rect.right > rect.left and rect.bottom > rect.top:
                self.bounds[hwnd] = rect

    def animate(self, hwnd: int, target: RECT):
        if self.guard.process.poll() is not None:
            raise RuntimeError("窗口动画恢复进程已退出")
        previous = self.active.get(hwnd)
        minimizing = IsIconic(hwnd)
        if previous is not None:
            if previous.minimizing != minimizing:
                previous.reverse(minimizing)
            return
        if hwnd in self.pending:
            source, _, _ = self.pending[hwnd]
            self.pending[hwnd] = source, target, minimizing
            return
        self.remember(hwnd)
        source = self.bounds.get(hwnd)
        if source is None or not hide_for_animation(hwnd):
            return
        self.pending[hwnd] = source, target, minimizing
        # Shell 同步消息中只交接可见性，DWM 与 Qt 窗口创建安排在消息返回后执行。
        QTimer.singleShot(0, lambda: self._start(hwnd))

    def _start(self, hwnd: int):
        pending = self.pending.pop(hwnd, None)
        if pending is None:
            return
        if not IsWindow(hwnd):
            restore_visibility(hwnd)
            return
        source, target, minimizing = pending
        try:
            overlay = GenieOverlay(hwnd, source, target, minimizing)
        except BaseException:
            restore_visibility(hwnd)
            raise
        self.active[hwnd] = overlay
        overlay.destroyed.connect(lambda: self._finished(hwnd, overlay))
        overlay.begin()

    def _finished(self, hwnd: int, overlay: GenieOverlay):
        if self.active.get(hwnd) is overlay:
            self.active.pop(hwnd)

    def forget(self, hwnd: int):
        self.bounds.pop(hwnd, None)
        if self.pending.pop(hwnd, None) is not None:
            restore_visibility(hwnd)
        overlay = self.active.pop(hwnd, None)
        if overlay is not None:
            overlay.finish()

    def stop(self):
        for hwnd in set(self.active) | set(self.pending):
            self.forget(hwnd)
