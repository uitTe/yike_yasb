"""应用信息窗口。"""

from collections.abc import Callable
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr
from core.ui.components.button import Button
from core.ui.components.text_block import TextBlock
from core.ui.views.view_base import ViewBase
from core.utils.system import get_architecture
from settings import (
    APP_NAME,
    BUILD_VERSION,
    RELEASE_CHANNEL,
)

ARCHITECTURE = get_architecture()

if TYPE_CHECKING:
    from core.tray import SystemTrayManager


class AboutDialog(ViewBase, QDialog):
    def __init__(self, tray_manager: SystemTrayManager):
        parent_widget: QWidget | None = tray_manager if isinstance(tray_manager, QWidget) else None
        super().__init__(parent_widget)
        self._tray = tray_manager
        self._secondary_buttons: list[Button] = []

        self._build_window()
        self._build_ui()

    def _build_window(self) -> None:
        self.setWindowTitle(tr("About {app}", app=APP_NAME))
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMinimumSize(360, 480)
        self.build_view()
        self._window_icon = self.build_app_icon()

    def _build_ui(self) -> None:

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if not self._window_icon.isNull():
            icon_label.setPixmap(self._window_icon.pixmap(90, 90))
        layout.addWidget(icon_label)

        title_label = TextBlock(APP_NAME, variant="title")
        title_label.setContentsMargins(0, 8, 0, 0)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        arch_suffix = f" {ARCHITECTURE}" if ARCHITECTURE else ""
        version_label = TextBlock(
            tr("Version {version}{arch} ({channel})", version=BUILD_VERSION, arch=arch_suffix, channel=RELEASE_CHANNEL),
            variant="caption",
        )
        version_label.setContentsMargins(0, 4, 0, 6)
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version_label)

        button_layout = QVBoxLayout()
        button_layout.setContentsMargins(0, 12, 0, 0)
        button_layout.setSpacing(8)
        button_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._support_project_button = self._create_action_button(
            "Support the Project",
            lambda: self._tray.open_in_browser("https://github.com/uitTe/yike_yasb"),
        )
        self._open_config_button = self._create_action_button("Open Config", self._tray.open_config)
        for button in (
            self._support_project_button,
            self._open_config_button,
        ):
            button.setMinimumWidth(180)
            button_layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignHCenter)

        layout.addLayout(button_layout)

    def _create_action_button(self, text: str, callback: Callable[[], object]) -> Button:
        button = Button(tr(text), font_size=12, font_weight="demibold")
        button.clicked.connect(callback)
        self._secondary_buttons.append(button)
        return button
