"""使用独立进程中的真实窗口验证应用切换的层级处理。"""
import ctypes
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from core.utils.win32.bindings.user32 import (
    GetMonitorInfo,
    GetWindowLong,
    IsIconic,
    PostMessage,
    enum_display_monitors,
    user32,
)
from core.utils.win32.structs import WINDOWPLACEMENT
from core.utils.win32.window_actions import fit_window_to_monitor, release_covering_app_windows


def wait_until(predicate):
    deadline = time.monotonic() + 5
    while not predicate():
        assert time.monotonic() < deadline, "原生窗口状态没有按时更新"
        time.sleep(0.02)


@pytest.fixture
def windows():
    processes = []
    handles = []
    try:
        for title in ("YASB activation target", "YASB activation cover"):
            process = subprocess.Popen(
                [sys.executable, "-B", str(Path(__file__).parents[1] / "support/native_task_window.py"), title],
                env={**os.environ, "QT_QPA_PLATFORM": "windows"},
                stdout=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            processes.append(process)
            handles.append(int(process.stdout.readline()))
        target, cover = handles
        assert user32.SetWindowPos(cover, -1, 300, 200, 280, 140, 0x10)
        wait_until(lambda: bool(GetWindowLong(cover, -20) & 8))
        yield target, cover
    finally:
        for handle in handles:
            PostMessage(handle, 0x10, 0, 0)
        for process in processes:
            assert process.wait(timeout=5) == 0


def test_covering_tracked_application_returns_to_normal_layer(windows):
    target, cover = windows
    assert release_covering_app_windows(target, windows)
    wait_until(lambda: not GetWindowLong(cover, -20) & 8)
    assert not GetWindowLong(target, -20) & 8


def test_untracked_topmost_window_keeps_its_layer(windows):
    target, cover = windows
    assert not release_covering_app_windows(target, [target])
    assert GetWindowLong(cover, -20) & 8


def test_non_overlapping_application_keeps_its_layer(windows):
    target, cover = windows
    assert user32.SetWindowPos(cover, -1, 1200, 650, 280, 140, 0x10)
    assert not release_covering_app_windows(target, windows)
    assert GetWindowLong(cover, -20) & 8


def test_minimized_target_releases_cover_on_its_monitor(windows):
    target, cover = windows
    user32.ShowWindowAsync(target, 6)
    wait_until(lambda: IsIconic(target))
    assert release_covering_app_windows(target, windows)
    wait_until(lambda: not GetWindowLong(cover, -20) & 8)


@pytest.mark.parametrize("show_cmd", [1, 2, 3])
def test_window_restores_on_requested_monitor_without_overflow(windows, show_cmd):
    target, reference = windows
    monitors = enum_display_monitors()
    if len(monitors) < 2:
        pytest.skip("需要两个真实显示器")
    for monitor, _ in monitors:
        work = GetMonitorInfo(monitor).rcWork
        user32.ShowWindow(target, 9)
        assert user32.SetWindowPos(reference, 0, work.left + 100, work.top + 100, 280, 180, 0x14)
        user32.ShowWindow(target, show_cmd)
        fit_window_to_monitor(target, reference)
        if IsIconic(target):
            user32.ShowWindow(target, 9)
        wait_until(lambda: user32.MonitorFromWindow(target, 2) == monitor and not IsIconic(target))
        placement = WINDOWPLACEMENT(length=ctypes.sizeof(WINDOWPLACEMENT))
        assert user32.GetWindowPlacement(target, ctypes.byref(placement))
        if show_cmd == 3:
            assert placement.showCmd == 3
        else:
            rect = ctypes.wintypes.RECT()
            assert user32.GetWindowRect(target, ctypes.byref(rect))
            assert work.left <= rect.left < rect.right <= work.right
            assert work.top <= rect.top < rect.bottom <= work.bottom
            assert not fit_window_to_monitor(target, reference)
            user32.ShowWindow(target, 6)
            wait_until(lambda: IsIconic(target))
            assert fit_window_to_monitor(target, reference)
            assert not IsIconic(target)
            restored = ctypes.wintypes.RECT()
            assert user32.GetWindowRect(target, ctypes.byref(restored))
            assert (restored.right - restored.left, restored.bottom - restored.top) == (
                rect.right - rect.left, rect.bottom - rect.top
            )


def test_oversized_window_fits_current_monitor(windows):
    target, reference = windows
    monitor = user32.MonitorFromWindow(reference, 2)
    work = GetMonitorInfo(monitor).rcWork
    assert user32.SetWindowPos(target, 0, work.left + 150, work.top + 150,
                              work.right - work.left + 300, work.bottom - work.top + 300, 0x14)
    assert fit_window_to_monitor(target, reference)
    rect = ctypes.wintypes.RECT()
    assert user32.GetWindowRect(target, ctypes.byref(rect))
    assert work.left <= rect.left < rect.right <= work.right
    assert work.top <= rect.top < rect.bottom <= work.bottom


def test_saved_restore_bounds_preserve_size(windows):
    target, reference = windows
    saved = WINDOWPLACEMENT(length=ctypes.sizeof(WINDOWPLACEMENT))
    assert user32.GetWindowPlacement(target, ctypes.byref(saved))
    normal = saved.rcNormalPosition
    bounds = (normal.left, normal.top, normal.right, normal.bottom)
    original = ctypes.wintypes.RECT()
    assert user32.GetWindowRect(target, ctypes.byref(original))
    assert user32.SetWindowPos(target, 0, original.left, original.top,
                              2 * (original.right - original.left), 2 * (original.bottom - original.top), 0x14)
    assert fit_window_to_monitor(target, reference, bounds)
    restored = ctypes.wintypes.RECT()
    assert user32.GetWindowRect(target, ctypes.byref(restored))
    assert (restored.left, restored.top, restored.right, restored.bottom) == (
        original.left, original.top, original.right, original.bottom
    )
