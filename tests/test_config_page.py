from copy import deepcopy
from pathlib import Path
from shutil import copyfile

import pytest
import yaml
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
)

from core.i18n import get_language
from core.ui.components.toggle_switch import ToggleSwitch
from core.ui.config_document import ConfigChangedError, ConfigDocument, validate_config, widget_models
from core.ui.views.preferences import AddWidgetDialog, SettingsWindow
from core.ui.widget_catalog import CATALOG, initial_options, words
from core.ui.widget_inputs import WidgetInputs


@pytest.fixture
def document(tmp_path):
    path = tmp_path / "config.yaml"
    copyfile(Path(__file__).parents[1] / "src/defaults/config.yaml", path)
    return ConfigDocument(path)


def complete_options(kind, widgets):
    options = initial_options(kind)
    for field in CATALOG[kind].fields:
        if not field.required:
            continue
        value = {
            "applications": [{"launch": "notepad.exe", "icon": "↗"}],
            "servers": [{"name": "Local service", "url": "http://localhost:8080"}],
            "folder": str(Path(__file__).parent),
        }.get(field.kind, "configured")
        target = options
        for key in field.path[:-1]:
            target = target.setdefault(key, {})
        target[field.path[-1]] = value
    editor = WidgetInputs(CATALOG[kind], options, widgets)
    return editor, editor.collected()


def test_catalog_covers_all_widgets_with_localized_minimal_fields(qapp, document):
    assert set(CATALOG) == set(widget_models())
    hidden = {"label", "label_alt", "class_name", "callbacks", "keybindings", "icons", "menu", "tooltip",
              "progress_bar", "update_interval", "cache_ttl", "timeout", "animation"}
    for kind, info in CATALOG.items():
        assert all(info.title) and all(info.description)
        assert any("\u4e00" <= char <= "\u9fff" for char in info.title[0])
        assert not hidden.intersection(field.path[0] for field in info.fields)
        editor, options = complete_options(kind, document.data["widgets"])
        widget_models()[kind].model_validate(options)
        assert len(editor.controls) == len(info.fields)
        editor.deleteLater()
    assert [field.path for field in CATALOG["yasb.codex_usage.CodexUsageWidget"].fields] == [("codex_path",)]


def test_round_trip_and_external_conflict(document):
    original = document.path.read_text(encoding="utf-8")
    document.path.write_text("# 配置页面保存检查\n" + original, encoding="utf-8")
    document.reload()
    untouched = deepcopy(document.data["widgets"])
    document.assign(("debug",), True)
    document.save()
    assert document.path.read_text(encoding="utf-8").startswith("# 配置页面保存检查\n")
    assert yaml.safe_load(document.path.read_text(encoding="utf-8"))["widgets"] == untouched
    assert not document.dirty
    document.assign(("debug",), False)
    external = document.path.read_bytes() + b"\n# external\n"
    document.path.write_bytes(external)
    with pytest.raises(ConfigChangedError):
        document.save()
    assert document.path.read_bytes() == external


def test_overview_window_animation_defaults_off_and_persists(qapp, document):
    from core.validation.config import YasbConfig

    assert YasbConfig().window_animations is False
    unchanged = deepcopy({key: value for key, value in document.data.items() if key != "window_animations"})
    window = SettingsWindow(document)
    toggle = window.findChild(ToggleSwitch, "window-animations")
    assert toggle is not None and not toggle.isChecked()
    toggle.click()
    assert window.save()
    reloaded = ConfigDocument(document.path)
    assert reloaded.value(("window_animations",)) is True
    window.close()
    window = SettingsWindow(reloaded)
    toggle = window.findChild(ToggleSwitch, "window-animations")
    assert toggle.isChecked()
    toggle.click()
    assert window.save()
    saved = ConfigDocument(document.path)
    assert saved.value(("window_animations",)) is False
    assert {key: value for key, value in saved.data.items() if key != "window_animations"} == unchanged
    window.close()


def test_restore_defaults_confirmation_saves_immediately(qapp, document):
    defaults = deepcopy(document.data)
    document.assign(("debug",), True)
    document.assign(("window_animations",), True)
    document.save()
    original_bytes = document.path.read_bytes()
    window = SettingsWindow(document)
    button = window.findChild(QPushButton, "restore-defaults")
    assert button is not None
    def respond(answer):
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, QMessageBox)
        dialog.button(answer).click()
    QTimer.singleShot(0, lambda: respond(QMessageBox.StandardButton.No))
    button.click()
    assert document.path.read_bytes() == original_bytes
    assert document.value(("window_animations",)) is True
    QTimer.singleShot(0, lambda: respond(QMessageBox.StandardButton.Yes))
    button.click()
    assert document.data == defaults
    assert not document.dirty and not window.save_button.isEnabled()
    assert not window.findChild(ToggleSwitch, "window-animations").isChecked()
    assert window.current_path == ()
    assert ConfigDocument(document.path).data == defaults
    window.close()


def test_restore_defaults_keeps_external_save_conflict_protection(document):
    document.assign(("debug",), True)
    document.save()
    document.restore_defaults()
    external = document.path.read_bytes() + b"\n# external\n"
    document.path.write_bytes(external)
    with pytest.raises(ConfigChangedError):
        document.save()
    assert document.path.read_bytes() == external


def test_add_codex_attaches_and_preserves_hidden_options(qapp, document):
    window = SettingsWindow(document)
    bar = next(iter(document.data["bars"]))
    document.assign(("bars", bar, "screens"), [])
    before = deepcopy(document.data["widgets"])
    kind = "yasb.codex_usage.CodexUsageWidget"
    path = window.add_widget_to_bar(kind, bar, "right", {"codex_path": "codex", "update_interval": 180})
    assert document.value(("bars", bar, "screens")) == ["**"]
    assert path[1] in document.value(("bars", bar, "widgets", "right"))
    assert len(window.form.controls) == 1
    field = window.form.findChild(QLineEdit, "input:codex_path")
    field.setText("codex.exe")
    assert window.save()
    reloaded = ConfigDocument(document.path)
    assert reloaded.value((*path, "options")) == {"codex_path": "codex.exe", "update_interval": 180}
    assert all(reloaded.data["widgets"][name] == entry for name, entry in before.items())
    second = window.add_widget_to_bar(kind, bar, "left", {"codex_path": "codex"})
    assert second != path
    assert window.save()
    window.close()


def test_add_every_component_to_a_real_configuration(qapp, document):
    window = SettingsWindow(document)
    bar = next(iter(document.data["bars"]))
    for kind in CATALOG:
        editor, options = complete_options(kind, document.data["widgets"])
        path = window.add_widget_to_bar(kind, bar, "right", options)
        assert path[1] in document.value(("bars", bar, "widgets", "right"))
        assert window.save(), kind
        validate_config(ConfigDocument(document.path).data)
        editor.deleteLater()
        qapp.processEvents()
    window.close()


def test_catalog_selection_lists_names_and_only_essential_inputs(qapp, document):
    window = SettingsWindow(document)
    dialog = AddWidgetDialog(document, None, window)
    assert dialog.catalog.count() == len(CATALOG)
    for index in range(dialog.catalog.count()):
        dialog.catalog.setCurrentRow(index)
        assert dialog.inputs is not None
        kind = dialog.catalog.item(index).data(Qt.ItemDataRole.UserRole)
        assert len(dialog.inputs.controls) == len(CATALOG[kind].fields)
        assert words(CATALOG[kind].title) in dialog.catalog.item(index).text()
        qapp.processEvents()
    dialog.search.setText("Codex")
    visible = [dialog.catalog.item(index) for index in range(dialog.catalog.count()) if not dialog.catalog.item(index).isHidden()]
    assert len(visible) == 1
    assert dialog.inputs.findChild(QLineEdit, "input:codex_path") is not None
    dialog.reject()
    window.close()


def test_required_information_blocks_addition_without_writing(qapp, document):
    window = SettingsWindow(document)
    dialog = AddWidgetDialog(document, None, window)
    dialog.search.setText("壁纸")
    assert dialog.kind == "yasb.wallpapers.WallpapersWidget"
    dialog.accept()
    assert dialog.result() == 0
    assert dialog.error.text()
    assert not document.dirty
    dialog.inputs.findChild(QLineEdit, "input:image_path").setText(str(Path(__file__).parent))
    dialog.accept()
    assert dialog.result() == 1
    window.close()


def test_existing_wallpaper_folder_list_is_preserved(qapp, document):
    kind = "yasb.wallpapers.WallpapersWidget"
    folders = [str(Path(__file__).parent), str(Path(__file__).parents[1] / "src/assets")]
    editor = WidgetInputs(CATALOG[kind], {"image_path": folders}, document.data["widgets"])
    control = editor.findChild(QPlainTextEdit, "input:image_path")
    assert control.toPlainText().splitlines() == folders
    assert editor.collected()["image_path"] == folders
    control.setPlainText(folders[0])
    assert editor.collected()["image_path"] == folders[:1]
    editor.deleteLater()


def test_language_switch_updates_window_catalog_and_preserves_draft(qapp, document):
    window = SettingsWindow(document)
    assert get_language() == "zh_CN"
    window.language_button.click()
    assert get_language() == "en"
    assert window.add_button.text() == "Add widget"
    assert window.save_button.text() == "Save changes"
    assert document.data["language"] == "en"
    dialog = AddWidgetDialog(document, None, window)
    assert dialog.windowTitle() == "Add widget"
    assert all("\u4e00" > char or char > "\u9fff" for char in dialog.catalog.item(0).text())
    dialog.reject()
    window.language_button.click()
    assert get_language() == "zh_CN"
    assert window.add_button.text() == "添加组件"
    assert window.save_button.text() == "保存配置"
    assert not document.dirty
    window.close()


def test_bar_order_removal_and_safe_display_selection(qapp, document):
    window = SettingsWindow(document)
    bar = next(iter(document.data["bars"]))
    window._navigation(select=("bars", bar))
    combo = window.content.findChild(QComboBox, "bar-display")
    assert all(combo.itemData(index) for index in range(combo.count()))
    original = list(document.value(("bars", bar, "widgets", "left")))
    window.move_widget(bar, "left", 0, 1)
    assert document.value(("bars", bar, "widgets", "left"))[:2] == original[1::-1]
    window.remove_from_bar(bar, "left", 0)
    assert len(document.value(("bars", bar, "widgets", "left"))) == len(original) - 1
    assert original[1] in document.data["widgets"]
    assert window.save()
    window.close()


def test_reading_and_switching_pages_does_not_modify_configuration(qapp, document):
    window = SettingsWindow(document)
    window.show()
    qapp.processEvents()
    for category in range(window.navigation.topLevelItemCount()):
        group = window.navigation.topLevelItem(category)
        for index in range(group.childCount()):
            window.navigation.setCurrentItem(group.child(index))
            qapp.processEvents()
            if window.form is not None:
                assert not window.form.findChildren(QPlainTextEdit) or window.form.info.fields
    assert not document.dirty
    assert window.width() >= 1000
    window.close()


def test_group_members_are_named_and_cycles_are_rejected(qapp, document):
    window = SettingsWindow(document)
    bar = next(iter(document.data["bars"]))
    name = next(iter(document.data["widgets"]))
    path = window.add_widget_to_bar("yasb.grouper.GrouperWidget", bar, "right", {"widgets": [name]})
    chooser = window.form.findChild(QListWidget, "input:widgets")
    assert chooser.count() == len(document.data["widgets"]) - 1
    document.assign((*path, "options", "widgets"), [path[1]])
    assert not window.save()
    assert "无法保存" in window.message.text()
    document.assign((*path, "options", "widgets"), [name])
    assert window.save()
    window.close()


def test_conflict_message_is_localized(qapp, document):
    window = SettingsWindow(document)
    window.switch_language()
    document.path.write_bytes(document.path.read_bytes() + b"\n# external edit\n")
    assert not window.save()
    assert "another program" in window.message.text()
    document.original = deepcopy(document.data)
    window.close()


def test_automatic_widget_has_no_component_configuration(qapp, document):
    window = SettingsWindow(document)
    name = next(name for name, entry in document.data["widgets"].items() if entry["type"] == "yasb.cpu.CpuWidget")
    window._navigation(select=("widgets", name))
    assert not window.form.controls
    assert not window.form.findChildren(QLineEdit)
    assert any("无需填写配置" in label.text() for label in window.form.findChildren(QLabel))
    window.close()
