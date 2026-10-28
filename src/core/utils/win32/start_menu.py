"""在指定窗口所在显示器切换 Windows 开始菜单。"""

from ctypes import POINTER
from ctypes.wintypes import BOOL, HMONITOR, UINT

from comtypes import CLSCTX_LOCAL_SERVER, COMMETHOD, GUID, HRESULT, CoCreateInstance, IUnknown

from core.utils.win32.bindings.user32 import MonitorFromWindow

ILSM_STARTBUTTON = 0xB
ILSF_IGNORE_SET_FOREGROUND_ERROR = 4
ILDM_STARTBUTTON = 4


class IServiceProvider(IUnknown):
    _iid_ = GUID("{6d5140c1-7436-11ce-8034-00aa006009fa}")
    _methods_ = [
        COMMETHOD(
            [],
            HRESULT,
            "QueryService",
            (["in"], POINTER(GUID), "service"),
            (["in"], POINTER(GUID), "iid"),
            (["out"], POINTER(POINTER(IUnknown)), "result"),
        ),
    ]


class IImmersiveMonitor(IUnknown):
    _iid_ = GUID("{880b26f8-9197-43d0-8045-8702d0d72000}")
    _methods_ = [
        COMMETHOD([], HRESULT, "GetIdentity", (["out"], POINTER(UINT), "identity")),
        COMMETHOD([], HRESULT, "Append", (["in"], POINTER(IUnknown), "object")),
        COMMETHOD([], HRESULT, "GetHandle", (["out"], POINTER(HMONITOR), "monitor")),
    ]


class IImmersiveMonitorManager(IUnknown):
    _iid_ = GUID("{4d4c1e64-e410-4faa-bafa-59ca069bfec2}")
    _methods_ = [
        COMMETHOD([], HRESULT, "GetCount", (["out"], POINTER(UINT), "count")),
        COMMETHOD([], HRESULT, "GetConnectedCount", (["out"], POINTER(UINT), "count")),
        COMMETHOD(
            [], HRESULT, "GetAt", (["in"], UINT, "index"), (["out"], POINTER(POINTER(IImmersiveMonitor)), "monitor")
        ),
        COMMETHOD(
            [],
            HRESULT,
            "GetFromHandle",
            (["in"], HMONITOR, "handle"),
            (["out"], POINTER(POINTER(IImmersiveMonitor)), "monitor"),
        ),
    ]


class IImmersiveLauncher(IUnknown):
    _iid_ = GUID("{d8d60399-a0f1-f987-5551-321fd1b49864}")
    _methods_ = [
        COMMETHOD([], HRESULT, "ShowStartView", (["in"], UINT, "method"), (["in"], UINT, "flags")),
        COMMETHOD([], HRESULT, "Dismiss", (["in"], UINT, "method")),
        COMMETHOD([], HRESULT, "Dismiss2", (["in"], UINT, "method")),
        COMMETHOD([], HRESULT, "DismissSynchronouslyWithoutTransition"),
        COMMETHOD([], HRESULT, "IsVisible", (["out"], POINTER(BOOL), "visible")),
        COMMETHOD([], HRESULT, "OnStartButtonPressed", (["in"], UINT, "show"), (["in"], UINT, "dismiss")),
        COMMETHOD([], HRESULT, "SetForeground"),
        COMMETHOD([], HRESULT, "ConnectToMonitor", (["in"], POINTER(IImmersiveMonitor), "monitor")),
        COMMETHOD([], HRESULT, "GetMonitor", (["out"], POINTER(POINTER(IImmersiveMonitor)), "monitor")),
    ]


def toggle_start_menu(hwnd: int) -> None:
    monitor = MonitorFromWindow(hwnd)
    if monitor is None:
        raise ValueError("无法确定 Dock 所在的显示器")
    shell = CoCreateInstance(
        GUID("{c2f03a33-21f5-47fa-b4bb-156362a2f239}"),
        interface=IServiceProvider,
        clsctx=CLSCTX_LOCAL_SERVER,
    )
    launcher = shell.QueryService(
        GUID("{6f86e01c-c649-4d61-be23-f1322ddeca9d}"), IImmersiveLauncher._iid_
    ).QueryInterface(IImmersiveLauncher)
    if launcher.IsVisible():
        launcher.Dismiss(ILDM_STARTBUTTON)
        return
    manager = shell.QueryService(
        GUID("{47094e3a-0cf2-430f-806f-cf9e4f0f12dd}"), IImmersiveMonitorManager._iid_
    ).QueryInterface(IImmersiveMonitorManager)
    launcher.ConnectToMonitor(manager.GetFromHandle(monitor))
    # 使用开始按钮的调用方式，Windows 才会保留指定的显示器。
    launcher.ShowStartView(ILSM_STARTBUTTON, ILSF_IGNORE_SET_FOREGROUND_ERROR)
