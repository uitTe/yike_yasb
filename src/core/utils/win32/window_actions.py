import ctypes
import logging
from collections.abc import Iterable
from ctypes.wintypes import DWORD, RECT

from core.utils.win32.bindings.dwmapi import DwmGetWindowAttribute
from core.utils.win32.bindings.kernel32 import kernel32 as k32
from core.utils.win32.bindings.user32 import (
    GetMonitorInfo,
    GetWindowLong,
    IsHungAppWindow,
    IsWindowEnabled,
    PostMessage,
    enum_windows,
    get_window_thread_process_id,
)
from core.utils.win32.bindings.user32 import user32 as u32
from core.utils.win32.constants import (
    DWMWA_CLOAKED,
    GA_ROOT,
    GA_ROOTOWNER,
    GWL_EXSTYLE,
    GWL_STYLE,
    HWND_NOTOPMOST,
    HWND_TOP,
    PROCESS_TERMINATE,
    SC_CLOSE,
    SC_MAXIMIZE,
    SC_MINIMIZE,
    SC_RESTORE,
    SMTO_ABORTIFHUNG,
    SW_MAXIMIZE,
    SW_MINIMIZE,
    SW_RESTORE,
    SW_SHOW,
    SWP_ASYNCWINDOWPOS,
    SWP_NOACTIVATE,
    SWP_NOMOVE,
    SWP_NOSIZE,
    SWP_NOZORDER,
    WM_CLOSE,
    WM_SYSCOMMAND,
    WS_EX_TOOLWINDOW,
    WS_EX_TOPMOST,
    WS_MINIMIZEBOX,
)
from core.utils.win32.structs import WINDOWPLACEMENT


def resolve_base_and_focus(hwnd: int) -> tuple[int, int]:
    """Return (base_owner_root, focus_target). Focus target is the last active visible popup if any."""
    base = hwnd
    try:
        base = u32.GetAncestor(hwnd, GA_ROOTOWNER) or u32.GetAncestor(hwnd, GA_ROOT) or hwnd
    except Exception:
        base = hwnd

    focus_target = base
    try:
        last = u32.GetLastActivePopup(base)
        if last and u32.IsWindowVisible(last):
            focus_target = last
    except Exception:
        pass
    return int(base), int(focus_target)


def is_owner_root_active(base: int) -> bool:
    """Check if the owner-root of the current foreground window matches base."""
    fg = u32.GetForegroundWindow()
    if not fg:
        return False
    try:
        fg_top = u32.GetAncestor(fg, GA_ROOTOWNER) or u32.GetAncestor(fg, GA_ROOT) or fg
    except Exception:
        fg_top = fg
    return int(fg_top) == int(base)


def can_minimize(hwnd: int) -> bool:
    style = GetWindowLong(int(hwnd), GWL_STYLE)
    return bool(style & WS_MINIMIZEBOX) and bool(IsWindowEnabled(int(hwnd)))


def _post_sys_command(hwnd: int, cmd: int, fallback_show_cmd: int) -> None:
    # elevated apps don't take posted messages (UIPI), ShowWindowAsync still works on them
    if not PostMessage(int(hwnd), WM_SYSCOMMAND, cmd, 0):
        u32.ShowWindowAsync(int(hwnd), fallback_show_cmd)


def restore_window(hwnd: int) -> None:
    _post_sys_command(hwnd, SC_RESTORE, SW_RESTORE)


def minimize_window(hwnd: int) -> None:
    _post_sys_command(hwnd, SC_MINIMIZE, SW_MINIMIZE)


def maximize_window(hwnd: int) -> None:
    _post_sys_command(hwnd, SC_MAXIMIZE, SW_MAXIMIZE)


def show_window(hwnd: int) -> None:
    u32.ShowWindowAsync(int(hwnd), SW_SHOW)


def set_foreground(hwnd: int) -> None:
    """Bring the window to the front and focus it, without waiting for it."""
    flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS
    u32.SetWindowPos(int(hwnd), HWND_TOP, 0, 0, 0, 0, flags)
    u32.SetForegroundWindow(int(hwnd))


def fit_window_to_monitor(
    hwnd: int, reference_hwnd: int, normal_position: tuple[int, int, int, int] | None = None
) -> bool:
    """在目标屏幕恢复窗口，保持最大化状态并限制普通窗口边界。"""
    source_monitor = u32.MonitorFromWindow(hwnd, 2)
    target_monitor = u32.MonitorFromWindow(reference_hwnd, 2)
    source = GetMonitorInfo(source_monitor)
    target = GetMonitorInfo(target_monitor)
    if source is None or target is None:
        raise ctypes.WinError(ctypes.get_last_error())
    placement = WINDOWPLACEMENT(length=ctypes.sizeof(WINDOWPLACEMENT))
    if not u32.GetWindowPlacement(hwnd, ctypes.byref(placement)):
        raise ctypes.WinError(ctypes.get_last_error())
    rect = placement.rcNormalPosition
    current_bounds = (rect.left, rect.top, rect.right, rect.bottom)
    if normal_position is not None:
        rect.left, rect.top, rect.right, rect.bottom = normal_position
    source_dpi = u32.GetDpiForWindow(hwnd)
    target_dpi = u32.GetDpiForWindow(reference_hwnd)
    if not source_dpi or not target_dpi:
        raise ctypes.WinError(ctypes.get_last_error())
    scale = target_dpi / source_dpi
    work = target.rcWork
    width = min(round((rect.right - rect.left) * scale), work.right - work.left)
    height = min(round((rect.bottom - rect.top) * scale), work.bottom - work.top)
    # WINDOWPLACEMENT 的普通窗口位置使用工作区坐标，工具窗口使用屏幕坐标。
    tool_window = bool(GetWindowLong(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW)
    source_origin = source.rcWork if tool_window else source.rcMonitor
    target_origin = target.rcWork if tool_window else target.rcMonitor
    left = target_origin.left + min(
        max(0, round((rect.left - source_origin.left) * scale)), work.right - work.left - width
    )
    top = target_origin.top + min(
        max(0, round((rect.top - source_origin.top) * scale)), work.bottom - work.top - height
    )
    bounds = (left, top, left + width, top + height)
    maximized = placement.showCmd == SW_MAXIMIZE or (placement.showCmd == 2 and placement.flags & 2)
    maximized_overflow = False
    if placement.showCmd == SW_MAXIMIZE:
        visible = RECT()
        result = DwmGetWindowAttribute(hwnd, 9, ctypes.byref(visible), ctypes.sizeof(visible))
        if result != 0:
            raise ctypes.WinError(result)
        maximized_overflow = (
            visible.left < work.left or visible.top < work.top
            or visible.right > work.right or visible.bottom > work.bottom
        )
    if (
        source_monitor == target_monitor
        and not u32.IsIconic(hwnd)
        and bounds == current_bounds
        and not maximized_overflow
    ):
        return False
    rect.left, rect.top, rect.right, rect.bottom = bounds
    placement.ptMaxPosition.x = placement.ptMaxPosition.y = -1
    placement.showCmd = 4  # 先在目标位置恢复，避免最大化窗口停留在原屏幕。
    placement.flags = 0
    if not u32.SetWindowPlacement(hwnd, ctypes.byref(placement)):
        raise ctypes.WinError(ctypes.get_last_error())
    screen_left = left + work.left - target_origin.left
    screen_top = top + work.top - target_origin.top
    # DPI 切换完成后校正物理尺寸，避免应用处理缩放时重复调整。
    if not u32.SetWindowPos(hwnd, 0, screen_left, screen_top, width, height, SWP_NOZORDER | SWP_NOACTIVATE):
        raise ctypes.WinError(ctypes.get_last_error())
    if maximized:
        u32.ShowWindow(hwnd, SW_MAXIMIZE)
    return True


def release_covering_app_windows(hwnd: int, app_windows: Iterable[int]) -> bool:
    """解除覆盖目标的普通应用置顶状态，返回是否存在遮挡。"""
    tracked = set(app_windows)
    target = RECT()
    if not u32.GetWindowRect(hwnd, ctypes.byref(target)):
        raise ctypes.WinError(ctypes.get_last_error())
    minimized = bool(u32.IsIconic(hwnd))
    monitor = u32.MonitorFromWindow(hwnd, 2)
    covered = False
    flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS
    for other in enum_windows():
        if other == hwnd or other not in tracked or not u32.IsWindowVisible(other) or u32.IsIconic(other):
            continue
        if not GetWindowLong(other, GWL_EXSTYLE) & WS_EX_TOPMOST:
            continue
        cloaked = DWORD()
        result = DwmGetWindowAttribute(other, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        if result != 0:
            raise ctypes.WinError(result)
        if cloaked.value:
            continue
        rect = RECT()
        if not u32.GetWindowRect(other, ctypes.byref(rect)):
            raise ctypes.WinError(ctypes.get_last_error())
        overlaps = (target.left < rect.right and target.right > rect.left
                    and target.top < rect.bottom and target.bottom > rect.top)
        if not overlaps and not (minimized and u32.MonitorFromWindow(other, 2) == monitor):
            continue
        if not u32.SetWindowPos(other, HWND_NOTOPMOST, 0, 0, 0, 0, flags):
            raise ctypes.WinError(ctypes.get_last_error())
        covered = True
    return covered


def force_foreground_focus(hwnd: int) -> None:
    """
    Force a window to foreground with focus.

    Args:
        hwnd: Window handle to set as foreground
    """
    if not hwnd:
        return

    try:
        # Get the current foreground window
        fg_hwnd = u32.GetForegroundWindow()

        if fg_hwnd:
            fg_tid, _ = get_window_thread_process_id(fg_hwnd)
            my_tid = k32.GetCurrentThreadId()
            if fg_tid and my_tid and fg_tid != my_tid:
                u32.AttachThreadInput(my_tid, fg_tid, True)
                u32.SetForegroundWindow(hwnd)
                u32.SetFocus(hwnd)
                u32.AttachThreadInput(my_tid, fg_tid, False)
            else:
                u32.SetForegroundWindow(hwnd)
                u32.SetFocus(hwnd)
        else:
            u32.SetForegroundWindow(hwnd)
            u32.SetFocus(hwnd)
    except Exception as e:
        logging.debug("Failed to force foreground focus: %s", e)


def close_application(hwnd: int, force: bool = False):
    """
    Close the application associated with the given HWND.

    Args:
        hwnd: The window handle of the application to close
        force: If True, forcefully terminates the process (like Task Manager's End Task)
               If False, tries graceful close methods first

    Graceful close (force=False):
    - SendMessageTimeout(WM_SYSCOMMAND, SC_CLOSE) to the root owner window
    - If the window is hung, fall back to PostMessage(WM_CLOSE)
    - As a last resort, call EndTask (graceful attempt)

    Forced termination (force=True):
    - Tries EndTask with force flag
    - Falls back to direct TerminateProcess
    """
    try:
        if not hwnd or hwnd == 0:
            logging.warning("Invalid HWND: %s", hwnd)
            return

        # Resolve a better target: prefer GA_ROOTOWNER, then GA_ROOT
        try:
            root_owner = u32.GetAncestor(int(hwnd), GA_ROOTOWNER)
        except Exception:
            root_owner = 0
        try:
            root = u32.GetAncestor(int(hwnd), GA_ROOT)
        except Exception:
            root = 0
        target_hwnd = int(root_owner or root or hwnd)

        if force:
            # Forced termination path
            # Get process ID for direct termination
            try:
                _, process_id = get_window_thread_process_id(hwnd)
            except Exception as e:
                logging.error("Failed to get process ID for HWND %s: %s", hwnd, e)
                return

            if not process_id:
                logging.warning("No process ID found for HWND: %s", hwnd)
                return

            # Try forced EndTask first (Windows shell approach)
            try:
                # BOOL EndTask(HWND hWnd, BOOL fShutDown, BOOL fForce)
                # fForce=True makes it more aggressive
                endtask_ok = u32.EndTask(int(target_hwnd), False, True)
                if endtask_ok:
                    logging.info("Successfully ended task via forced EndTask for HWND: %s", hwnd)
                    return
            except Exception as et_ex:
                logging.warning("Forced EndTask failed for HWND %s: %s", target_hwnd, et_ex)

            # Fallback: Direct process termination
            try:
                # Open process handle with terminate rights
                process_handle = k32.OpenProcess(PROCESS_TERMINATE, False, process_id)
                if not process_handle:
                    logging.error("Failed to open process %s for termination", process_id)
                    return

                # Terminate the process with exit code 1
                terminated = k32.TerminateProcess(process_handle, 1)
                if terminated:
                    logging.info("Successfully terminated process %s for HWND: %s", process_id, hwnd)
                else:
                    logging.warning("TerminateProcess returned False for process %s", process_id)

                # Close the process handle
                k32.CloseHandle(process_handle)

            except Exception as term_ex:
                logging.error("Failed to terminate process %s: %s", process_id, term_ex)

        else:
            # Graceful close path
            # First try: SC_CLOSE via SendMessageTimeout to avoid hangs
            lpdw_result = ctypes.c_size_t()
            sent = u32.SendMessageTimeoutW(
                int(target_hwnd),
                int(WM_SYSCOMMAND),
                int(SC_CLOSE),
                0,
                int(SMTO_ABORTIFHUNG),
                2000,
                ctypes.byref(lpdw_result),
            )

            if sent:
                return

            # SendMessageTimeout also gives up while the app shows a modal prompt for SC_CLOSE
            # ("Save changes?"). Only a hung window needs the fallback; a responsive one would
            # get a second close request on top of the open prompt.
            if not IsHungAppWindow(int(target_hwnd)):
                return

            # Fallback: WM_CLOSE via PostMessage
            posted = PostMessage(int(target_hwnd), int(WM_CLOSE), 0, 0)
            if posted:
                return

            # Last resort: EndTask (graceful attempt, not forced)
            # BOOL EndTask(HWND hWnd, BOOL fShutDown, BOOL fForce)
            try:
                endtask_ok = u32.EndTask(int(target_hwnd), False, False)
                if not endtask_ok:
                    logging.warning("EndTask failed for HWND: %s", target_hwnd)
            except Exception as et_ex:
                logging.warning("EndTask unavailable/failed for HWND %s: %s", target_hwnd, et_ex)

    except Exception as e:
        logging.error("Failed to close window %s: %s", hwnd, e)
