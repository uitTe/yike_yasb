from pathlib import Path
from string import Formatter

import pytest
from pydantic import ValidationError
from PyQt6.QtWidgets import QDialogButtonBox, QPushButton
from yaml import safe_load

from core.i18n import set_language, tr, tr_default
from core.locales.zh_cn import MESSAGES
from core.setup.builder import build_config
from core.ui.views.welcome import WelcomeWizard
from core.validation.config import YasbConfig
from core.validation.widgets.yasb.home import HomeConfig, MenuLabelsConfig


def test_language_config_and_examples():
    assert YasbConfig().language == "en"
    root = Path(__file__).resolve().parents[1]
    for language in ("en", "zh_CN"):
        sample = safe_load((root / "docs" / "examples" / f"config.{language}.yaml").read_text(encoding="utf-8"))
        assert YasbConfig.model_validate(sample).language == language
    for language in ("zh", "fr", "", None):
        with pytest.raises(ValidationError):
            YasbConfig(language=language)


def test_catalog_keeps_format_parameters():
    formatter = Formatter()
    for source, translated in MESSAGES.items():
        assert translated.strip()
        assert {field for _, field, _, _ in formatter.parse(source) if field} == {
            field for _, field, _, _ in formatter.parse(translated) if field
        }, source


def test_localized_defaults_preserve_custom_text(qapp):
    try:
        set_language("zh_CN")
        assert tr_default(HomeConfig().menu_labels, "shutdown") == "关机"
        assert tr_default(MenuLabelsConfig(shutdown="Shutdown"), "shutdown") == "Shutdown"
        assert tr("Week {number}", number=42) == "第 42 周"
    finally:
        set_language("en")
    assert tr("Open Config") == "Open Config"


def test_generated_presets_do_not_modify_english(qapp):
    chinese = safe_load(build_config(language="zh_CN"))
    english = safe_load(build_config(language="en"))
    assert chinese["widgets"]["home"]["options"]["menu_list"][0]["title"] == "用户主目录"
    assert english["widgets"]["home"]["options"]["menu_list"][0]["title"] == "User Home"
    assert chinese["widgets"]["power_menu"]["options"]["buttons"]["shutdown"][1] == "关机"
    assert english["widgets"]["power_menu"]["options"]["buttons"]["shutdown"][1] == "Shut Down"
    assert "home" not in chinese["bars"]["primary-bar"]["widgets"]["left"]
    assert "home" not in english["bars"]["primary-bar"]["widgets"]["left"]
    assert YasbConfig.model_validate(chinese).language == "zh_CN"


def test_wizard_switches_both_languages_and_native_controls(qapp):
    try:
        set_language("en")
        wizard = WelcomeWizard()
        assert wizard.windowTitle() == "Welcome to YASB"
        wizard._change_language("zh_CN")
        assert wizard.windowTitle() == "欢迎使用 YASB"
        assert "启动 YASB" in {button.text() for button in wizard.findChildren(QPushButton)}
        native = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        assert native.buttons()[0].text() == "取消"
        wizard._change_language("en")
        assert wizard._stack.count() == 6
        assert "Start YASB" in {button.text() for button in wizard.findChildren(QPushButton)}
        wizard.close()
    finally:
        set_language("en")
