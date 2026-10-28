from PyQt6.QtWidgets import QLabel, QPushButton

from core.bar_manager import BarManager
from core.i18n import set_language
from core.tray import SystemTrayManager
from core.ui.components.link import Link
from core.ui.views.about import AboutDialog
from core.validation.config import YasbConfig


def test_about_displays_app_and_two_actions(qapp):
    manager = BarManager(YasbConfig(), "")
    tray = SystemTrayManager(manager)
    try:
        for language, actions in (
            ("en", {"Support the Project", "Open Config"}),
            ("zh_CN", {"支持项目", "打开配置文件夹"}),
        ):
            set_language(language)
            dialog = AboutDialog(tray)
            assert "YASB" in {label.text() for label in dialog.findChildren(QLabel)}
            assert {button.text() for button in dialog.findChildren(QPushButton)} == actions
            assert not dialog.findChildren(Link)
            dialog.close()
    finally:
        set_language("en")
        tray.deleteLater()
        manager.deleteLater()
