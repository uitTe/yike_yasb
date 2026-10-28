import datetime
import os
from pathlib import Path

import PyQt6
from cx_Freeze import Executable, setup  # pyright: ignore[reportUnknownVariableType, reportMissingTypeStubs]

from core.utils.system import detect_architecture
from settings import APP_ID, BUILD_VERSION, RELEASE_CHANNEL

icon_ico = "assets/images/app_icon.ico"
icon_png = "assets/images/app_icon.png"

if RELEASE_CHANNEL != "stable":
    if os.path.exists("assets/images/app_icon_preview.ico"):
        icon_ico = "assets/images/app_icon_preview.ico"
    if os.path.exists("assets/images/app_icon_preview.png"):
        icon_png = "assets/images/app_icon_preview.png"

arch_info = detect_architecture()
if not arch_info:
    raise RuntimeError("Unsupported or undetected architecture. Cannot build MSI package.")

display_arch, msi_arch_suffix = arch_info
build_timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y%m%d-%H%M%S")

hook_dll_name = "YASBTrayHook_arm64.dll" if display_arch == "ARM64" else "YASBTrayHook.dll"
everything_dll_name = "EverythingARM64.dll" if display_arch == "ARM64" else "Everything64.dll"

qt_directory = Path(PyQt6.__file__).parent / "Qt6"
qt_plugins = {"generic", "iconengines", "imageformats", "networkinformation", "platforms", "styles", "tls"}

build_options = {
    "packages": [
        "core.widgets.yasb",
        "core.widgets.komorebi",
        "core.widgets.glazewm",
    ],
    "constants": [f"ARCHITECTURE='{display_arch}'"],
    "silent_level": 1,
    "silent": True,
    "excludes": ["PySide6", "pydoc_data", "email", "tkinter", "PyQt5", "PySide2", "unittest"],
    # Qt 使用 Windows 提供的 ICU，避免包含其他工具的同名 DLL。
    "bin_excludes": ["Qt6Pdf.dll", "_avif.cp314-win_amd64.pyd", "icuuc.dll"],
    # 窗口使用 Widgets；仅包含实际使用的 Qt 模块、平台插件及 TLS 依赖。
    "bin_includes": [
        "Qt6Core.dll", "Qt6Gui.dll", "Qt6Network.dll", "Qt6Svg.dll", "Qt6WebSockets.dll", "Qt6Widgets.dll",
        "libssl*.dll", "libcrypto*.dll",
    ],
    "bin_path_excludes": [
        qt_directory / "bin", qt_directory / "qml",
        *(directory for directory in (qt_directory / "plugins").iterdir() if directory.is_dir() and directory.name not in qt_plugins),
    ],
    "zip_exclude_packages": [],
    "zip_include_packages": ["*"],
    "no_compress": True,
    "zip_filename": "library.zip",
    "zip_includes": [("defaults/config.yaml", "core/default_config.yaml")],
    "build_exe": "dist",
    "include_msvcr": True,
    "includes": [
        "holidays.countries",
        "winrt.windows.applicationmodel",
    ],
    "optimize": 1,
    "include_files": [
        ("defaults", "defaults"),
        ("../docs/examples", "examples"),
        ("../docs/language.md", "language.md"),
        ("../docs/settings-page.md", "settings-page.md"),
        (icon_png, "assets/images/app_icon.png"),
        ("assets/images/start.svg", "assets/images/start.svg"),
        ("assets/images/notification-bell.svg", "assets/images/notification-bell.svg"),
        ("assets/images/app_transparent.png", "assets/images/app_transparent.png"),
        ("assets/images/media.png", "assets/images/media.png"),
        ("assets/sound/notification01.wav", "assets/sound/notification01.wav"),
        ("assets/sound/notification02.wav", "assets/sound/notification02.wav"),
        (f"core/widgets/services/quick_launch/providers/resources/{everything_dll_name}", f"lib/{everything_dll_name}"),
        (f"core/widgets/services/systray/hook/{hook_dll_name}", f"lib/{hook_dll_name}"),
        ("core/widgets/services/quick_launch/providers/resources/emoji.json", "lib/emoji.json"),
    ],
}

directory_table = [
    ("ProgramMenuFolder", "TARGETDIR", "."),
    ("MyProgramMenu", "ProgramMenuFolder", "."),
]

msi_data = {
    "Directory": directory_table,
    "ProgId": [
        ("Prog.Id", None, None, "A highly configurable Windows status bar", "IconId", None),
    ],
    "Icon": [
        ("IconId", icon_ico),
    ],
    "Registry": [
        ("AppUserModelId", -1, f"Software\\Classes\\AppUserModelId\\{APP_ID}", "DisplayName", "YASB", "TARGETDIR"),
        (
            "AppUserModelIdIcon",
            -1,
            f"Software\\Classes\\AppUserModelId\\{APP_ID}",
            "IconUri",
            "[TARGETDIR]assets\\images\\app_icon.png",
            "TARGETDIR",
        ),
    ],
}

bdist_msi_options = {
    "data": msi_data,
    "install_icon": icon_ico,
    "upgrade_code": "{434be2bb-d79b-4848-8556-e81f18ae4f2f}",
    "add_to_path": True,
    "dist_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "releases")),
    "initial_target_dir": r"[ProgramFiles64Folder]\YASB",
    "all_users": True,
    "skip_build": True,
    "output_name": f"yasb-{BUILD_VERSION if RELEASE_CHANNEL == 'stable' else 'preview'}-{msi_arch_suffix}-{build_timestamp}.msi",
    "product_name": "YASB Yike",
    "product_version": BUILD_VERSION,
    "summary_data": {
        "author": "shuf",
        "comments": "YASB Yike status bar",
        "keywords": "windows; statusbar; ricing; customization; topbar; taskbar; yasb",
    },
}

executables = [
    Executable(
        "main.py",
        base="gui",
        icon=icon_ico,
        shortcut_name="YASB",
        shortcut_dir="MyProgramMenu",
        copyright=f"Copyright (C) {datetime.datetime.now().year} shuf",
        target_name="yasb",
    ),
    Executable(
        "cli.py",
        base="Console",
        copyright=f"Copyright (C) {datetime.datetime.now().year} shuf",
        target_name="yasbc",
    ),
    Executable(
        "taskbar_guard.py",
        base="gui",
        icon=icon_ico,
        copyright=f"Copyright (C) {datetime.datetime.now().year} shuf",
        target_name="yasb_taskbar",
    ),
    Executable(
        "core/ui/views/preferences.py",
        base="gui",
        icon=icon_ico,
        copyright=f"Copyright (C) {datetime.datetime.now().year} shuf",
        target_name="yasb_settings",
    ),
]

setup(
    name="YASB Yike",
    version=BUILD_VERSION,
    author="shuf",
    description="YASB Yike",
    executables=executables,
    options={
        "build_exe": build_options,
        "bdist_msi": bdist_msi_options,
    },
)
