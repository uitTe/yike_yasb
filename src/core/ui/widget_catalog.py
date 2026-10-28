"""组件目录与用户必须提供的外部信息。"""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from core.i18n import get_language

type Words = tuple[str, str]


def words(value: Words) -> str:
    return value[0] if get_language() == "zh_CN" else value[1]


def text(english: str, chinese: str) -> str:
    return words((chinese, english))


@dataclass(frozen=True)
class InputField:
    path: tuple[str, ...]
    title: Words
    help: Words
    kind: str = "text"
    default: Any = ""
    required: bool = False


@dataclass(frozen=True)
class WidgetInfo:
    title: Words
    description: Words
    fields: tuple[InputField, ...] = ()


CODEX_PATH = InputField(
    ("codex_path",), ("Codex 程序路径", "Codex executable"),
    ("选择 codex.exe；已加入系统 PATH 时使用 codex 即可。", "Choose codex.exe, or use codex when it is available on PATH."),
    "file", "codex",
)
TOKEN = InputField(
    ("token",), ("访问令牌", "Access token"),
    ("已有登录信息时可以留空；也可以填写该服务的访问令牌。", "Leave blank to use existing sign-in, or enter an access token."), "secret",
)
GLAZE_SERVER = InputField(
    ("glazewm_server_uri",), ("GlazeWM 服务地址", "GlazeWM server"),
    ("本机默认地址可以直接使用；连接其他服务时填写对应地址。", "Use the local default, or enter the address of another server."),
    default="ws://localhost:6123",
)

# 每个组件明确列出必要输入；未列出的选项由程序默认值和现有配置管理。
CATALOG: dict[str, WidgetInfo] = {
    "glazewm.binding_mode.GlazewmBindingModeWidget": WidgetInfo(("GlazeWM 操作模式", "GlazeWM binding mode"), ("查看并切换窗口管理器的操作模式。", "View and switch window manager binding modes."), (GLAZE_SERVER,)),
    "glazewm.tiling_direction.GlazewmTilingDirectionWidget": WidgetInfo(("GlazeWM 平铺方向", "GlazeWM tiling direction"), ("查看和切换窗口的平铺方向。", "View and change the window tiling direction."), (GLAZE_SERVER,)),
    "glazewm.workspaces.GlazewmWorkspacesWidget": WidgetInfo(("GlazeWM 工作区", "GlazeWM workspaces"), ("查看和切换 GlazeWM 工作区。", "View and switch GlazeWM workspaces."), (GLAZE_SERVER,)),
    "komorebi.active_layout.ActiveLayoutWidget": WidgetInfo(("Komorebi 布局", "Komorebi layout"), ("切换 Komorebi 窗口布局；需要运行 Komorebi。", "Switch layouts; requires a running Komorebi instance.")),
    "komorebi.control.KomorebiControlWidget": WidgetInfo(("Komorebi 控制", "Komorebi controls"), ("启动、停止和重新加载 Komorebi。", "Start, stop, and reload Komorebi.")),
    "komorebi.stack.StackWidget": WidgetInfo(("Komorebi 窗口组", "Komorebi window group"), ("查看 Komorebi 分组中的窗口。", "View windows in a Komorebi group.")),
    "komorebi.workspaces.WorkspaceWidget": WidgetInfo(("Komorebi 工作区", "Komorebi workspaces"), ("查看和切换 Komorebi 工作区。", "View and switch Komorebi workspaces.")),
    "yasb.active_window.ActiveWindowWidget": WidgetInfo(("当前窗口", "Active window"), ("自动显示当前窗口的图标和标题。", "Automatically show the active window icon and title.")),
    "yasb.applications.ApplicationsWidget": WidgetInfo(("应用快捷方式", "Application shortcuts"), ("添加需要固定显示的应用启动命令。", "Pin launch commands for your applications."), (
        InputField(("app_list",), ("应用程序", "Applications"), ("每行填写一个程序路径或启动命令。", "Enter one executable path or launch command per line."), "applications", [], True),
    )),
    "yasb.audio_visualizer.AudioVisualizerWidget": WidgetInfo(("音频可视化", "Audio visualizer"), ("自动读取系统音频并显示动态波形。", "Visualize audio from the default system output.")),
    "yasb.battery.BatteryWidget": WidgetInfo(("电池", "Battery"), ("自动显示电量和充电状态。", "Automatically show battery and charging status.")),
    "yasb.bluetooth.BluetoothWidget": WidgetInfo(("蓝牙", "Bluetooth"), ("查看蓝牙状态并连接设备。", "View Bluetooth status and connect devices.")),
    "yasb.brightness.BrightnessWidget": WidgetInfo(("屏幕亮度", "Brightness"), ("自动检测显示器并调节亮度。", "Detect displays and adjust brightness.")),
    "yasb.cava.CavaWidget": WidgetInfo(("Cava 音频频谱", "Cava spectrum"), ("显示音频频谱；需要将 Cava 程序加入系统 PATH。", "Show an audio spectrum; requires Cava on PATH.")),
    "yasb.claude_usage.ClaudeUsageWidget": WidgetInfo(("Claude 用量", "Claude usage"), ("使用本机 Claude 登录信息显示账户用量。", "Show account usage using local Claude credentials.")),
    "yasb.clock.ClockWidget": WidgetInfo(("时钟与日历", "Clock and calendar"), ("自动使用系统时间和时区。", "Use the system clock and timezone automatically.")),
    "yasb.codex_usage.CodexUsageWidget": WidgetInfo(("Codex 用量", "Codex usage"), ("显示 Codex 账户用量，只需指定 Codex 程序。", "Show Codex usage; only the executable path is needed."), (CODEX_PATH,)),
    "yasb.control_center.ControlCenterWidget": WidgetInfo(("控制中心", "Control center"), ("集中调节音量、亮度和系统常用功能。", "Access volume, brightness, and system controls.")),
    "yasb.copilot.CopilotWidget": WidgetInfo(("Copilot 用量", "Copilot usage"), ("使用访问令牌查询 GitHub Copilot 用量。", "Check GitHub Copilot usage with an access token."), (TOKEN,)),
    "yasb.cpu.CpuWidget": WidgetInfo(("处理器", "CPU"), ("自动显示处理器使用率。", "Automatically show CPU utilization.")),
    "yasb.custom.CustomWidget": WidgetInfo(("自定义命令", "Custom command"), ("执行自定义命令并显示输出内容。", "Run a command and display its output."), (
        InputField(("exec_options", "run_cmd"), ("执行命令", "Command"), ("填写需要执行的命令，输出内容将显示在状态栏。", "Enter a command whose output will appear on the bar."), required=True),
    )),
    "yasb.disk.DiskWidget": WidgetInfo(("磁盘空间", "Disk space"), ("自动显示系统磁盘的空间使用情况。", "Show storage usage for the system drive.")),
    "yasb.dnd.DndWidget": WidgetInfo(("勿扰模式", "Do not disturb"), ("查看和切换 Windows 勿扰模式。", "View and toggle Windows do not disturb.")),
    "yasb.github.GithubWidget": WidgetInfo(("GitHub 通知", "GitHub notifications"), ("通过访问令牌获取 GitHub 通知。", "Read GitHub notifications using an access token."), (TOKEN,)),
    "yasb.glucose_monitor.GlucoseMonitor": WidgetInfo(("血糖监测", "Glucose monitor"), ("连接个人 Nightscout 服务查看血糖数据。", "Read glucose data from your Nightscout server."), (
        InputField(("host",), ("服务地址", "Server address"), ("填写个人 Nightscout 服务的完整地址。", "Enter the full URL of your Nightscout server."), required=True),
        InputField(("secret",), ("访问密钥", "API secret"), ("服务要求身份验证时填写。", "Enter the secret if your server requires authentication."), "secret"),
    )),
    "yasb.gpu.GpuWidget": WidgetInfo(("显卡", "GPU"), ("自动读取显卡使用率和显存信息。", "Automatically read GPU and video memory utilization.")),
    "yasb.grouper.GrouperWidget": WidgetInfo(("组件分组", "Widget group"), ("将已经添加的组件组合显示。", "Display existing widgets as a group."), (
        InputField(("widgets",), ("分组成员", "Group members"), ("选择需要放入该分组的组件。", "Select the widgets to include in this group."), "widgets", []),
    )),
    "yasb.home.HomeWidget": WidgetInfo(("系统菜单", "System menu"), ("打开常用系统功能和电源菜单。", "Access common system tools and power actions.")),
    "yasb.language.LanguageWidget": WidgetInfo(("输入语言", "Input language"), ("自动显示和切换系统输入语言。", "Show and switch system input languages.")),
    "yasb.launchpad.LaunchpadWidget": WidgetInfo(("应用启动台", "Launchpad"), ("自动发现本机应用并提供搜索启动。", "Discover installed applications and launch them.")),
    "yasb.libre_monitor.LibreHardwareMonitorWidget": WidgetInfo(("硬件传感器", "Hardware sensor"), ("从 Libre Hardware Monitor 服务读取指定传感器。", "Read a sensor from Libre Hardware Monitor."), (
        InputField(("sensor_id",), ("传感器标识", "Sensor ID"), ("填写服务中需要读取的传感器标识。", "Enter the ID of the sensor to read."), default="/amdcpu/0/load/0", required=True),
        InputField(("server_host",), ("服务主机", "Server host"), ("填写运行硬件监控服务的主机地址。", "Enter the host running the monitoring service."), default="localhost"),
        InputField(("server_port",), ("服务端口", "Server port"), ("填写硬件监控服务使用的端口。", "Enter the monitoring service port."), "port", 8085),
        InputField(("server_username",), ("用户名", "Username"), ("服务启用身份验证时填写。", "Enter a username if authentication is enabled.")),
        InputField(("server_password",), ("密码", "Password"), ("服务启用身份验证时填写。", "Enter a password if authentication is enabled."), "secret"),
    )),
    "yasb.media.MediaWidget": WidgetInfo(("媒体播放", "Media playback"), ("自动显示正在播放的媒体并控制播放。", "Show and control the current media session.")),
    "yasb.media_lite.MediaWidget": WidgetInfo(("简洁媒体播放", "Compact media"), ("以简洁形式显示当前媒体和播放控制。", "Show compact media details and playback controls.")),
    "yasb.memory.MemoryWidget": WidgetInfo(("内存", "Memory"), ("自动显示系统内存使用情况。", "Automatically show system memory usage.")),
    "yasb.microphone.MicrophoneWidget": WidgetInfo(("麦克风", "Microphone"), ("调节默认麦克风音量和静音状态。", "Control the default microphone volume and mute state.")),
    "yasb.notes.NotesWidget": WidgetInfo(("便笺", "Notes"), ("创建和管理本地便笺，自动使用默认保存位置。", "Manage local notes in the default storage location.")),
    "yasb.notification_clock.NotificationClockWidget": WidgetInfo(("日期与通知", "Date and notifications"), ("合并显示日期和通知铃铛，打开通知与农历日历面板。", "Show the date and notification bell with a notification and lunar calendar panel.")),
    "yasb.notifications.NotificationsWidget": WidgetInfo(("系统通知", "Notifications"), ("自动显示 Windows 通知数量。", "Automatically show Windows notification counts.")),
    "yasb.obs.ObsWidget": WidgetInfo(("OBS 状态", "OBS status"), ("连接 OBS WebSocket 服务查看录制和直播状态。", "Connect to OBS WebSocket to view recording and streaming status."), (
        InputField(("connection", "host"), ("OBS 主机", "OBS host"), ("本机使用 localhost，远程连接填写对应主机。", "Use localhost for this computer, or enter a remote host."), default="localhost"),
        InputField(("connection", "port"), ("OBS 端口", "OBS port"), ("填写 OBS WebSocket 服务端口。", "Enter the OBS WebSocket port."), "port", 4455),
        InputField(("connection", "password"), ("OBS 密码", "OBS password"), ("填写 OBS WebSocket 设置中的密码。", "Enter the password from OBS WebSocket settings."), "secret"),
    )),
    "yasb.open_meteo.OpenMeteoWidget": WidgetInfo(("天气（免密钥）", "Weather (no API key)"), ("使用 Open-Meteo；在天气弹窗的位置设置中搜索地点或填写经纬度。", "Use Open-Meteo; search a location or enter coordinates in the weather popup settings.")),
    "yasb.pomodoro.PomodoroWidget": WidgetInfo(("番茄钟", "Pomodoro timer"), ("使用默认专注与休息时长，点击组件开始计时。", "Use default focus and break periods; click to start.")),
    "yasb.power_menu.PowerMenuWidget": WidgetInfo(("电源菜单", "Power menu"), ("提供锁定、睡眠、重新启动和关机操作。", "Access lock, sleep, restart, and shutdown actions.")),
    "yasb.power_plan.PowerPlanWidget": WidgetInfo(("电源计划", "Power plan"), ("自动读取并切换 Windows 电源计划。", "Read and switch Windows power plans.")),
    "yasb.quick_launch.QuickLaunchWidget": WidgetInfo(("快速启动器", "Quick launcher"), ("搜索并启动本机已安装的应用。", "Search and launch installed applications.")),
    "yasb.recycle_bin.RecycleBinWidget": WidgetInfo(("回收站", "Recycle bin"), ("显示回收站状态并提供打开操作。", "Show recycle bin status and open it.")),
    "yasb.server_monitor.ServerMonitor": WidgetInfo(("服务器监控", "Server monitor"), ("检查指定网址是否可以访问。", "Check availability of specified web addresses."), (
        InputField(("servers",), ("监控地址", "Server URLs"), ("每行填写一个完整网址，例如 https://example.com。", "Enter one full URL per line, such as https://example.com."), "servers", [], True),
    )),
    "yasb.systray.SystrayWidget": WidgetInfo(("系统托盘", "System tray"), ("自动显示系统托盘中的应用图标。", "Automatically show application tray icons.")),
    "yasb.system_monitor.SystemMonitorWidget": WidgetInfo(("处理器与内存", "CPU and memory"), ("合并显示处理器和内存使用情况。", "Show CPU and memory usage in one component.")),
    "yasb.system_status.SystemStatusWidget": WidgetInfo(("网络、音量与电量", "Network, volume and battery"), ("合并显示网络、音量和电量，并提供声音与麦克风控制。", "Show network, volume and battery with audio and microphone controls.")),
    "yasb.taskbar.TaskbarWidget": WidgetInfo(("任务栏", "Taskbar"), ("自动显示运行中的应用窗口。", "Automatically show running application windows.")),
    "yasb.todo.TodoWidget": WidgetInfo(("待办事项", "To-do list"), ("管理本地待办事项，自动使用默认保存位置。", "Manage tasks in the default local storage location.")),
    "yasb.traffic.TrafficWidget": WidgetInfo(("网络速度", "Network traffic"), ("自动检测网络接口并显示上传下载速度。", "Detect network interfaces and show transfer speeds.")),
    "yasb.update_check.UpdateCheckWidget": WidgetInfo(("Windows 更新", "Windows updates"), ("检查 Windows 系统更新。", "Check available Windows system updates.")),
    "yasb.volume.VolumeWidget": WidgetInfo(("音量", "Volume"), ("调节默认音频设备的音量和静音状态。", "Control default audio volume and mute state.")),
    "yasb.vscode.VSCodeWidget": WidgetInfo(("VS Code 最近项目", "VS Code recent projects"), ("自动读取 VS Code 最近打开的文件和项目。", "Read recently opened VS Code files and projects.")),
    "yasb.wallpapers.WallpapersWidget": WidgetInfo(("壁纸", "Wallpapers"), ("浏览和设置指定文件夹中的壁纸。", "Browse and apply wallpapers from a folder."), (
        InputField(("image_path",), ("壁纸文件夹", "Wallpaper folder"), ("选择存放壁纸图片的文件夹。", "Choose a folder containing wallpaper images."), "folder", required=True),
    )),
    "yasb.weather.WeatherWidget": WidgetInfo(("天气（WeatherAPI）", "Weather (WeatherAPI)"), ("使用 WeatherAPI 提供的天气数据，需要密钥和城市。", "Read WeatherAPI data using an API key and location."), (
        InputField(("api_key",), ("天气服务密钥", "Weather API key"), ("填写个人 WeatherAPI 密钥。", "Enter your WeatherAPI key."), "secret", required=True),
        InputField(("location",), ("城市", "City"), ("填写城市名称或经纬度。", "Enter a city name or latitude and longitude."), required=True),
    )),
    "yasb.whkd.WhkdWidget": WidgetInfo(("快捷键查看器", "Keyboard shortcuts"), ("读取本机 whkd 配置并显示快捷键。", "Read and display shortcuts from local whkd configuration.")),
    "yasb.wifi.WifiWidget": WidgetInfo(("网络连接", "Network connection"), ("自动显示无线或有线网络连接状态。", "Automatically show Wi-Fi or Ethernet status.")),
    "yasb.window_controls.WindowControlsWidget": WidgetInfo(("窗口控制", "Window controls"), ("控制当前窗口的最小化、最大化和关闭。", "Minimize, maximize, or close the current window.")),
    "yasb.window_switcher.WindowSwitcherWidget": WidgetInfo(("窗口切换器", "Window switcher"), ("自动列出正在运行的窗口供切换。", "List running windows for quick switching.")),
    "yasb.windows_desktops.WorkspaceWidget": WidgetInfo(("虚拟桌面", "Virtual desktops"), ("查看和切换 Windows 虚拟桌面。", "View and switch Windows virtual desktops.")),
    "yasb.windows_pinned.WindowsPinnedWidget": WidgetInfo(("固定应用", "Pinned applications"), ("自动读取 Windows 固定的应用。", "Automatically read applications pinned in Windows.")),
}


def initial_options(kind: str) -> dict[str, Any]:
    presets = {
        "yasb.applications.ApplicationsWidget": {"label": "", "app_list": []},
        "yasb.custom.CustomWidget": {"class_name": "custom", "label": "{data}", "exec_options": {"return_format": "string"}},
        "yasb.notification_clock.NotificationClockWidget": {"label": "{%H:%M %Y/%m/%d}", "label_alt": "{%H:%M %Y/%m/%d}"},
        "yasb.power_menu.PowerMenuWidget": {"buttons": {
            "lock": ["\ue72e", text("Lock", "锁定")],
            "sleep": ["\ue708", text("Sleep", "睡眠")],
            "restart": ["\ue777", text("Restart", "重新启动")],
            "shutdown": ["\ue7e8", text("Shut down", "关机")],
            "cancel": ["\ue711", text("Cancel", "取消")],
        }},
        "yasb.update_check.UpdateCheckWidget": {"windows_update": {"enabled": True}},
        "yasb.open_meteo.OpenMeteoWidget": {"callbacks": {"on_left": "toggle_card"}},
        "yasb.media.MediaWidget": {"callbacks": {"on_left": "toggle_media_menu"}},
    }
    return deepcopy(presets.get(kind, {}))
