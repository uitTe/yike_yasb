"""托盘启动的简易组件配置页面。"""

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from PyQt6.QtCore import QSignalBlocker, QSize, Qt
from PyQt6.QtGui import QAction, QCloseEvent
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from ruamel.yaml.error import YAMLError

from core.config import get_config_path
from core.i18n import get_language, initialize_language, set_language
from core.ui.components.toggle_switch import ToggleSwitch
from core.ui.config_document import ConfigChangedError, ConfigDocument, ConfigPath, widget_models
from core.ui.views.view_base import ViewBase
from core.ui.widget_catalog import CATALOG, initial_options, text, words
from core.ui.widget_inputs import WidgetInputs, validate_inputs
from settings import APP_NAME, IS_FROZEN, SCRIPT_PATH

STYLE = """
QWidget#settings-root { background: #202020; color: #ededed; font-family: 'Segoe UI'; font-size: 13px; }
QFrame[role="sidebar"] { background: #181818; border-right: 1px solid #303030; }
QLabel { background: transparent; color: #ededed; }
QLabel[role="title"] { font-size: 24px; font-weight: 600; }
QLabel[role="brand"] { font-size: 18px; font-weight: 600; }
QLabel[role="muted"] { color: #aaaaaa; font-size: 12px; }
QFrame[role="card"] { background: #262626; border: 1px solid #393939; border-radius: 8px; }
QTreeWidget, QListWidget { background: #202020; border: none; color: #ededed; outline: none; }
QTreeWidget::item { min-height: 34px; border-radius: 6px; padding-left: 6px; }
QListWidget::item { padding: 10px; border-bottom: 1px solid #343434; }
QTreeWidget::item:selected, QListWidget::item:selected { background: #383838; color: white; }
QTreeWidget::item:hover:!selected, QListWidget::item:hover:!selected { background: #2b2b2b; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: #202020; }
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox { background: #292929; border: 1px solid #454545;
    border-radius: 6px; color: #ededed; padding: 7px 9px; min-height: 18px; selection-background-color: #555555; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border-color: #aaaaaa; }
QComboBox QAbstractItemView { background: #292929; color: #ededed; selection-background-color: #494949; }
QPushButton { background: #303030; border: 1px solid #434343; border-radius: 6px;
    color: #ededed; padding: 7px 10px; }
QPushButton:hover { background: #414141; }
QPushButton:disabled { color: #737373; background: #242424; }
QPushButton[role="primary"] { color: #181818; background: #eeeeee; border-color: #eeeeee; font-weight: 600; }
QPushButton[role="primary"]:disabled { color: #777777; background: #404040; border-color: #404040; }
QScrollBar:vertical { width: 8px; background: transparent; }
QScrollBar::handle:vertical { background: #555555; border-radius: 4px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""

SIDES = ("left", "center", "right")


def side_title(side: str) -> str:
    return words({"left": ("左侧", "Left"), "center": ("居中", "Center"), "right": ("右侧", "Right")}[side])


def clear_layout(layout: QVBoxLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget() is not None:
            item.widget().deleteLater()


def bar_title(document: ConfigDocument, name: str) -> str:
    index = list(document.data["bars"]).index(name) + 1
    position = document.value(("bars", name, "alignment", "position"), "top")
    title = text("Bottom bar", "底部状态栏") if position == "bottom" else text("Top bar", "顶部状态栏")
    return f"{title} {index}"


def widget_title(document: ConfigDocument, name: str) -> str:
    kind = document.value(("widgets", name, "type"))
    title = words(CATALOG[kind].title)
    matches = [key for key, entry in document.data["widgets"].items() if entry["type"] == kind]
    return f"{title} {matches.index(name) + 1}" if len(matches) > 1 else title


class AddWidgetDialog(QDialog):
    def __init__(self, document: ConfigDocument, bar: str | None, parent: QWidget):
        super().__init__(parent)
        self.document = document
        self.inputs: WidgetInputs | None = None
        self.options: dict[str, Any] = {}
        self.kind = ""
        self.setWindowTitle(text("Add widget", "添加组件"))
        self.setObjectName("settings-root")
        self.setStyleSheet(STYLE)
        self.resize(980, 720)
        self.setMinimumSize(880, 600)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        heading = QLabel(text("Choose a widget", "选择要添加的组件"))
        heading.setProperty("role", "title")
        outer.addWidget(heading)
        body = QHBoxLayout()
        left = QVBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(text("Search widgets", "搜索组件"))
        self.search.setClearButtonEnabled(True)
        left.addWidget(self.search)
        self.catalog = QListWidget()
        self.catalog.setWordWrap(True)
        self.catalog.setMinimumWidth(320)
        common = ("codex_usage", "clock", "cpu", "memory", "volume", "open_meteo", "taskbar", "quick_launch")
        ordered = sorted(CATALOG, key=lambda kind: (
            common.index(kind.split(".")[1]) if kind.split(".")[1] in common else len(common),
            kind.startswith(("glazewm.", "komorebi.")), CATALOG[kind].title[1],
        ))
        for kind in ordered:
            info = CATALOG[kind]
            item = QListWidgetItem(words(info.title) + "\n" + words(info.description))
            item.setData(Qt.ItemDataRole.UserRole, kind)
            item.setSizeHint(QSize(320, 86))
            self.catalog.addItem(item)
        self.catalog.currentItemChanged.connect(self._selected)
        left.addWidget(self.catalog, 1)
        body.addLayout(left, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.details = QWidget()
        self.details_layout = QVBoxLayout(self.details)
        self.details_layout.setContentsMargins(22, 8, 10, 8)
        scroll.setWidget(self.details)
        body.addWidget(scroll, 1)
        outer.addLayout(body, 1)
        placement = QHBoxLayout()
        placement.addWidget(QLabel(text("Add to", "添加到")))
        self.target_bar = QComboBox()
        for name in document.data["bars"]:
            self.target_bar.addItem(bar_title(document, name), name)
        if bar is not None:
            self.target_bar.setCurrentIndex(self.target_bar.findData(bar))
        placement.addWidget(self.target_bar, 1)
        self.target_side = QComboBox()
        for side in SIDES:
            self.target_side.addItem(side_title(side), side)
        self.target_side.setCurrentIndex(2)
        placement.addWidget(self.target_side)
        outer.addLayout(placement)
        self.error = QLabel()
        self.error.setStyleSheet("color: #ff9696;")
        self.error.setWordWrap(True)
        outer.addWidget(self.error)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton(text("Cancel", "取消"))
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        self.add_button = QPushButton(text("Add widget", "添加组件"))
        self.add_button.setProperty("role", "primary")
        self.add_button.clicked.connect(self.accept)
        buttons.addWidget(self.add_button)
        outer.addLayout(buttons)
        self.search.textChanged.connect(self._filter)
        self.catalog.setCurrentRow(0)

    def _selected(self, item: QListWidgetItem | None, _previous=None) -> None:
        clear_layout(self.details_layout)
        self.inputs = None
        self.kind = "" if item is None else item.data(Qt.ItemDataRole.UserRole)
        self.error.clear()
        self.add_button.setEnabled(bool(self.kind))
        if not self.kind:
            self.details_layout.addWidget(QLabel(text("No matching widgets", "没有匹配的组件")))
            return
        info = CATALOG[self.kind]
        title = QLabel(words(info.title))
        title.setProperty("role", "brand")
        self.details_layout.addWidget(title)
        description = QLabel(words(info.description))
        description.setWordWrap(True)
        self.details_layout.addWidget(description)
        self.inputs = WidgetInputs(info, initial_options(self.kind), self.document.data.get("widgets", {}))
        self.details_layout.addWidget(self.inputs)
        self.details_layout.addStretch()

    def _filter(self, query: str) -> None:
        query = query.strip().casefold()
        first = None
        current = self.catalog.currentItem()
        for index in range(self.catalog.count()):
            item = self.catalog.item(index)
            info = CATALOG[item.data(Qt.ItemDataRole.UserRole)]
            item.setHidden(query not in " ".join((*info.title, *info.description)).casefold())
            if not item.isHidden() and first is None:
                first = item
        if current is None or current.isHidden():
            self.catalog.setCurrentItem(first)

    def accept(self) -> None:
        if self.inputs is None:
            return
        try:
            self.options = self.inputs.collected()
            widget_models()[self.kind].model_validate(self.options)
        except ValidationError:
            self.error.setText(text("Complete the required information and check the addresses.", "请填写必填信息，并检查输入的地址。"))
            return
        except ValueError as error:
            self.error.setText(str(error))
            return
        super().accept()


class SettingsWindow(ViewBase, QMainWindow):
    def __init__(self, document: ConfigDocument | None = None):
        super().__init__()
        self.document = document if document is not None else ConfigDocument()
        set_language(self.document.data.get("language", "en"))
        if set(CATALOG) != set(widget_models()):
            raise RuntimeError("组件目录与程序内置组件不一致。")
        self.current_path: ConfigPath = ()
        self.form: WidgetInputs | None = None
        self.edited_widgets: set[str] = set()
        self.resize(1120, 780)
        self.setMinimumSize(920, 620)
        self.build_app_icon()
        action = QAction(self)
        action.setShortcut("Ctrl+S")
        action.triggered.connect(self.save)
        self.addAction(action)
        self._build()
        self._navigation()
        self._dirty_changed()

    def _build(self) -> None:
        self.setWindowTitle(f"{APP_NAME} · {text('Settings', '设置')}")
        root = QWidget()
        root.setObjectName("settings-root")
        root.setStyleSheet(STYLE)
        previous = self.takeCentralWidget()
        if previous is not None:
            previous.deleteLater()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = QFrame()
        sidebar.setProperty("role", "sidebar")
        sidebar.setFixedWidth(244)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 24, 16, 18)
        side.setSpacing(14)
        brand = QLabel("YASB")
        brand.setProperty("role", "brand")
        side.addWidget(brand)
        self.language_button = QPushButton("English" if get_language() == "zh_CN" else "简体中文")
        self.language_button.setObjectName("switch-language")
        self.language_button.clicked.connect(self.switch_language)
        side.addWidget(self.language_button)
        self.search = QLineEdit()
        self.search.setPlaceholderText(text("Search added widgets", "搜索已添加的组件"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._navigation)
        side.addWidget(self.search)
        self.navigation = QTreeWidget()
        self.navigation.setHeaderHidden(True)
        self.navigation.setIndentation(10)
        self.navigation.currentItemChanged.connect(self._selected)
        side.addWidget(self.navigation, 1)
        self.add_button = QPushButton(text("Add widget", "添加组件"))
        self.add_button.setProperty("role", "primary")
        self.add_button.clicked.connect(self._add_widget)
        side.addWidget(self.add_button)
        add_bar = QPushButton(text("Add status bar", "添加状态栏"))
        add_bar.clicked.connect(self._add_bar)
        side.addWidget(add_bar)
        layout.addWidget(sidebar)
        main = QVBoxLayout()
        main.setContentsMargins(32, 28, 32, 20)
        self.title = QLabel()
        self.title.setProperty("role", "title")
        self.title.setWordWrap(True)
        main.addWidget(self.title)
        self.description = QLabel()
        self.description.setProperty("role", "muted")
        self.description.setWordWrap(True)
        main.addWidget(self.description)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 16, 8, 8)
        self.content_layout.setSpacing(18)
        scroll.setWidget(self.content)
        main.addWidget(scroll, 1)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.hide()
        main.addWidget(self.message)
        footer = QHBoxLayout()
        self.status = QLabel()
        self.status.setProperty("role", "muted")
        footer.addWidget(self.status, 1)
        self.reload_button = QPushButton(text("Reload file", "重新读取"))
        self.reload_button.clicked.connect(self.reload_file)
        footer.addWidget(self.reload_button)
        self.save_button = QPushButton(text("Save changes", "保存配置"))
        self.save_button.setProperty("role", "primary")
        self.save_button.clicked.connect(self.save)
        footer.addWidget(self.save_button)
        main.addLayout(footer)
        layout.addLayout(main, 1)

    def switch_language(self) -> None:
        language = "en" if get_language() == "zh_CN" else "zh_CN"
        self.document.assign(("language",), language)
        set_language(language)
        selected = self.current_path
        self._build()
        self._navigation(select=selected)
        self._dirty_changed()

    def _navigation(self, _query: str = "", select: ConfigPath | None = None) -> None:
        chosen = self.current_path if select is None else select
        query = self.search.text().strip().casefold()
        with QSignalBlocker(self.navigation):
            self.navigation.clear()
            overview = QTreeWidgetItem([text("Overview", "概览")])
            overview.setData(0, Qt.ItemDataRole.UserRole, ())
            self.navigation.addTopLevelItem(overview)
            selected = overview if not chosen else None
            for category, title in (("bars", text("Status bars", "状态栏")), ("widgets", text("Added widgets", "已添加的组件"))):
                group = QTreeWidgetItem([title])
                group.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.navigation.addTopLevelItem(group)
                for name in self.document.data.get(category, {}):
                    path = (category, name)
                    label = bar_title(self.document, name) if category == "bars" else widget_title(self.document, name)
                    info = None if category == "bars" else CATALOG[self.document.value((*path, "type"))]
                    searchable = label if info is None else " ".join((*info.title, *info.description))
                    if query and query not in searchable.casefold():
                        continue
                    item = QTreeWidgetItem([label])
                    item.setData(0, Qt.ItemDataRole.UserRole, path)
                    group.addChild(item)
                    if path == chosen:
                        selected = item
                group.setExpanded(True)
                group.setHidden(not group.childCount())
            if selected is None:
                selected = overview
                for index in range(1, self.navigation.topLevelItemCount()):
                    group = self.navigation.topLevelItem(index)
                    if group.childCount():
                        selected = group.child(0)
                        break
            self.navigation.setCurrentItem(selected)
        self._selected(selected)

    def _selected(self, item: QTreeWidgetItem | None, _previous=None) -> None:
        if item is None or item.data(0, Qt.ItemDataRole.UserRole) is None:
            return
        clear_layout(self.content_layout)
        self.form = None
        self.current_path = tuple(item.data(0, Qt.ItemDataRole.UserRole))
        path = self.current_path
        if not path:
            self.title.setText(text("Make your bar your own", "管理状态栏与组件"))
            self.description.setText(text("Choose a widget, select a bar and position, then save.", "选择组件，指定状态栏与位置，保存后即可使用。"))
            note = QLabel(text("Most widgets work automatically. Only paths, credentials, or service addresses need input.", "大部分组件添加后即可使用。需要填写的内容仅包括程序路径、访问凭据或服务地址。"))
            note.setWordWrap(True)
            self.content_layout.addWidget(note)
            animation_row = QWidget()
            animation_layout = QHBoxLayout(animation_row)
            animation_label = QLabel(text("Window minimize and restore animation", "窗口收放动画"))
            animation_layout.addWidget(animation_label, 1)
            animation_toggle = ToggleSwitch(checked=self.document.value(("window_animations",), False))
            animation_toggle.setObjectName("window-animations")
            animation_toggle.setAccessibleName(animation_label.text())
            animation_toggle.toggled.connect(lambda checked: self._set(("window_animations",), checked))
            animation_layout.addWidget(animation_toggle)
            self.content_layout.addWidget(animation_row)
            animation_note = QLabel(text(
                "Use macOS-style animations between application windows and their top bar tabs.",
                "最小化和还原时，使用连接窗口与顶部对应页签的 macOS 风格动画。",
            ))
            animation_note.setProperty("role", "muted")
            animation_note.setWordWrap(True)
            self.content_layout.addWidget(animation_note)
            restore = QPushButton(text("Restore default configuration", "恢复默认配置"))
            restore.setObjectName("restore-defaults")
            restore.clicked.connect(self.restore_defaults)
            self.content_layout.addWidget(restore, alignment=Qt.AlignmentFlag.AlignLeft)
            restore_note = QLabel(text(
                "Confirm to restore and apply the default bars, widgets, and global settings.",
                "确认后立即恢复默认的状态栏、组件和全局设置。",
            ))
            restore_note.setProperty("role", "muted")
            restore_note.setWordWrap(True)
            self.content_layout.addWidget(restore_note)
            for name in self.document.data["bars"]:
                button = QPushButton(bar_title(self.document, name) + text(" · Manage widgets", " · 管理组件"))
                button.clicked.connect(lambda checked=False, name=name: self._navigation(select=("bars", name)))
                self.content_layout.addWidget(button)
        elif path[0] == "bars":
            self._bar_page(str(path[1]))
        else:
            self._widget_page(str(path[1]))
        self.content_layout.addStretch()

    def _bar_page(self, name: str) -> None:
        self.title.setText(bar_title(self.document, name))
        self.description.setText(text("Choose where this bar appears and arrange its widgets.", "选择状态栏显示位置，并管理各区域的组件顺序。"))
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.addWidget(QLabel(text("Show this bar", "显示此状态栏")), 1)
        enabled = self.document.value(("bars", name, "enabled"), True)
        screens = self.document.value(("bars", name, "screens"), ["*"])
        toggle = ToggleSwitch(checked=enabled and bool(screens))
        toggle.setObjectName("bar-enabled")
        toggle.toggled.connect(lambda checked: self.set_bar_enabled(name, checked))
        layout.addWidget(toggle)
        self.content_layout.addWidget(row)
        self.content_layout.addWidget(QLabel(text("Display", "显示器")))
        display = QComboBox()
        display.setObjectName("bar-display")
        display.addItem(text("All displays", "全部显示器"), ["**"])
        display.addItem(text("Primary display", "主显示器"), ["primary"])
        for screen in QApplication.screens():
            if screen.name():
                display.addItem(screen.name(), [screen.name()])
        selected = display.findData(["**"] if screens == ["*"] else screens)
        if not screens:
            selected = 0
        elif selected < 0:
            display.addItem(text("Current display selection", "当前显示器选择"), screens)
            selected = display.count() - 1
        display.setCurrentIndex(selected)
        display.currentIndexChanged.connect(lambda index: self._set(("bars", name, "screens"), display.itemData(index)))
        self.content_layout.addWidget(display)
        self.content_layout.addWidget(QLabel(text("Bar position", "状态栏位置")))
        position = QComboBox()
        position.addItem(text("Top", "顶部"), "top")
        position.addItem(text("Bottom", "底部"), "bottom")
        position.setCurrentIndex(position.findData(self.document.value(("bars", name, "alignment", "position"), "top")))
        position.currentIndexChanged.connect(lambda index: self._set(("bars", name, "alignment", "position"), position.itemData(index)))
        self.content_layout.addWidget(position)
        for side in SIDES:
            card = QFrame()
            card.setProperty("role", "card")
            box = QVBoxLayout(card)
            heading = QWidget()
            heading_layout = QHBoxLayout(heading)
            heading_layout.addWidget(QLabel(side_title(side)), 1)
            add = QPushButton(text("Add widget", "添加组件"))
            add.clicked.connect(lambda checked=False, side=side: self._add_widget(side=side))
            heading_layout.addWidget(add)
            box.addWidget(heading)
            items = self.document.value(("bars", name, "widgets", side), [])
            if not items:
                box.addWidget(QLabel(text("No widgets in this area", "此区域尚未添加组件")))
            for index, widget in enumerate(items):
                item = QWidget()
                item_layout = QHBoxLayout(item)
                detail = QPushButton(widget_title(self.document, widget))
                detail.clicked.connect(lambda checked=False, widget=widget: self._navigation(select=("widgets", widget)))
                item_layout.addWidget(detail, 1)
                for direction, label in ((-1, text("Up", "上移")), (1, text("Down", "下移"))):
                    move = QPushButton(label)
                    move.setEnabled(0 <= index + direction < len(items))
                    move.clicked.connect(lambda checked=False, index=index, direction=direction, side=side: self.move_widget(name, side, index, direction))
                    item_layout.addWidget(move)
                remove = QPushButton(text("Remove", "移除"))
                remove.clicked.connect(lambda checked=False, side=side, index=index: self.remove_from_bar(name, side, index))
                item_layout.addWidget(remove)
                box.addWidget(item)
            self.content_layout.addWidget(card)

    def _widget_page(self, name: str) -> None:
        kind = self.document.value(("widgets", name, "type"))
        info = CATALOG[kind]
        self.title.setText(widget_title(self.document, name))
        self.description.setText(words(info.description))
        self.form = WidgetInputs(info, self.document.value(("widgets", name, "options"), {}), self.document.data["widgets"], name)
        self.form.option_changed.connect(lambda path, value: self._edit_widget(name, path, value))
        self.content_layout.addWidget(self.form)
        self.content_layout.addWidget(QLabel(text("Show on a bar", "添加到状态栏")))
        placement = QWidget()
        row = QHBoxLayout(placement)
        bar = QComboBox()
        for bar_name in self.document.data["bars"]:
            bar.addItem(bar_title(self.document, bar_name), bar_name)
        side = QComboBox()
        for side_name in SIDES:
            side.addItem(side_title(side_name), side_name)
        side.setCurrentIndex(2)
        add = QPushButton(text("Add", "添加"))
        add.clicked.connect(lambda: self.attach_widget(name, bar.currentData(), side.currentData()))
        row.addWidget(bar, 1)
        row.addWidget(side)
        row.addWidget(add)
        self.content_layout.addWidget(placement)
        locations = []
        for bar_name, entry in self.document.data["bars"].items():
            for side_name in SIDES:
                if name in entry.get("widgets", {}).get(side_name, []):
                    locations.append(f"{bar_title(self.document, bar_name)} · {side_title(side_name)}")
        status = QLabel("\n".join(locations) if locations else text("This widget has not been added to a bar.", "此组件尚未添加到状态栏。"))
        status.setWordWrap(True)
        status.setProperty("role", "muted")
        self.content_layout.addWidget(status)
        remove = QPushButton(text("Delete widget", "删除组件"))
        remove.clicked.connect(self._delete_widget)
        self.content_layout.addWidget(remove, alignment=Qt.AlignmentFlag.AlignLeft)

    def _set(self, path: ConfigPath, value: Any) -> None:
        self.document.assign(path, value)
        self.message.hide()
        self._dirty_changed()

    def _edit_widget(self, name: str, path: tuple[str, ...], value: Any) -> None:
        self.edited_widgets.add(name)
        self._set(("widgets", name, "options", *path), value)

    def set_bar_enabled(self, name: str, enabled: bool) -> None:
        if enabled and not self.document.value(("bars", name, "screens"), ["*"]):
            self.document.assign(("bars", name, "screens"), ["**"])
        self._set(("bars", name, "enabled"), enabled)
        self._navigation(select=("bars", name))

    def attach_widget(self, name: str, bar: str, side: str) -> None:
        for other in SIDES:
            if other != side:
                other_path = ("bars", bar, "widgets", other)
                previous = self.document.value(other_path, [])
                if name in previous:
                    self.document.assign(other_path, [item for item in previous if item != name])
        path = ("bars", bar, "widgets", side)
        items = list(self.document.value(path, []))
        if name not in items:
            items.append(name)
            self.document.assign(path, items)
        self.set_bar_enabled(bar, True)

    def add_widget_to_bar(self, kind: str, bar: str, side: str, options: dict[str, Any]) -> ConfigPath:
        validate_inputs(CATALOG[kind], options)
        widget_models()[kind].model_validate(options)
        if bar not in self.document.data["bars"] or side not in SIDES:
            raise ValueError(text("Choose a bar and position.", "请选择状态栏和位置。"))
        base = kind.split(".")[1]
        name = base
        counter = 2
        while name in self.document.data.get("widgets", {}):
            name = f"{base}_{counter}"
            counter += 1
        path = self.document.add("widgets", name, kind)
        self.document.assign((*path, "options"), options)
        self.attach_widget(name, bar, side)
        self.search.clear()
        self._navigation(select=path)
        return path

    def move_widget(self, bar: str, side: str, index: int, direction: int) -> None:
        path = ("bars", bar, "widgets", side)
        items = list(self.document.value(path, []))
        items[index], items[index + direction] = items[index + direction], items[index]
        self._set(path, items)
        self._navigation(select=("bars", bar))

    def remove_from_bar(self, bar: str, side: str, index: int) -> None:
        path = ("bars", bar, "widgets", side)
        items = list(self.document.value(path, []))
        del items[index]
        self._set(path, items)
        self._navigation(select=("bars", bar))

    def _add_widget(self, _checked=False, side: str = "right") -> None:
        bar = str(self.current_path[1]) if self.current_path and self.current_path[0] == "bars" else None
        dialog = AddWidgetDialog(self.document, bar, self)
        dialog.target_side.setCurrentIndex(SIDES.index(side))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.add_widget_to_bar(dialog.kind, dialog.target_bar.currentData(), dialog.target_side.currentData(), dialog.options)

    def _add_bar(self) -> None:
        counter = len(self.document.data["bars"]) + 1
        while f"bar_{counter}" in self.document.data["bars"]:
            counter += 1
        path = self.document.add("bars", f"bar_{counter}")
        self.document.assign((*path, "screens"), ["**"])
        self.search.clear()
        self._navigation(select=path)
        self._dirty_changed()

    def _delete_widget(self) -> None:
        if QMessageBox.question(
            self, text("Delete widget", "删除组件"),
            text("Delete this widget from all bars and groups?", "从所有状态栏和分组中删除此组件？"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            self.edited_widgets.discard(str(self.current_path[1]))
            self.document.remove(self.current_path)
            self._navigation(select=())
            self._dirty_changed()

    def _dirty_changed(self) -> None:
        self.save_button.setEnabled(self.document.dirty)
        self.status.setText(text("Unsaved changes", "有未保存的修改") if self.document.dirty else text("All changes saved", "全部修改已保存"))

    def _show_error(self, message: str) -> None:
        self.message.setStyleSheet("color: #ff9696;")
        self.message.setText(message)
        self.message.show()

    def save(self) -> bool:
        try:
            for name in self.edited_widgets:
                entry = self.document.value(("widgets", name))
                validate_inputs(CATALOG[entry["type"]], entry.get("options", {}))
            self.document.save()
        except ConfigChangedError:
            self._show_error(text("The file was changed by another program. Reload it before saving.", "配置文件已被其他程序修改，请重新读取后再保存。"))
            return False
        except OSError:
            self._show_error(text("Unable to write the configuration. Check folder access permissions.", "无法写入配置文件，请检查程序配置文件夹的访问权限。"))
            return False
        except (ValueError, YAMLError):
            self._show_error(text("Unable to save. Complete required information and check component references.", "无法保存，请填写必填信息并检查组件引用。"))
            return False
        self.edited_widgets.clear()
        self.message.setStyleSheet("color: #9ddcaf;")
        watching = self.document.data.get("watch_config", True)
        self.message.setText(
            text("Saved. YASB will apply the changes automatically.", "已保存，YASB 将自动应用修改。") if watching
            else text("Saved. Reload YASB from the tray menu to apply changes.", "已保存，请通过托盘菜单重新加载 YASB。")
        )
        self.message.show()
        self._dirty_changed()
        return True

    def restore_defaults(self) -> None:
        confirmation = QMessageBox(
            QMessageBox.Icon.Question,
            text("Restore default configuration", "恢复默认配置"),
            text("Restore default bars, widgets, and global settings? Unsaved changes will be replaced.",
                 "是否恢复默认的状态栏、组件和全局设置？尚未保存的修改也将被替换。"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            self,
        )
        confirmation.button(QMessageBox.StandardButton.Yes).setText(text("Confirm", "确定"))
        confirmation.button(QMessageBox.StandardButton.No).setText(text("Cancel", "取消"))
        confirmation.setDefaultButton(QMessageBox.StandardButton.No)
        if confirmation.exec() != QMessageBox.StandardButton.Yes:
            return
        was_watching = self.document.original.get("watch_config", True)
        self.document.restore_defaults()
        self.edited_widgets.clear()
        self.search.clear()
        set_language(self.document.data.get("language", "en"))
        self._build()
        self._navigation(select=())
        self._dirty_changed()
        if self.save() and not was_watching and self.document.path == Path(get_config_path()):
            command = ([str(Path(SCRIPT_PATH) / "yasbc.exe")] if IS_FROZEN
                       else [sys.executable, str(Path(SCRIPT_PATH) / "cli.py")])
            subprocess.run([*command, "reload"], check=True, creationflags=subprocess.CREATE_NO_WINDOW)

    def reload_file(self) -> None:
        if self.document.dirty and QMessageBox.question(
            self, text("Reload file", "重新读取"), text("Discard unsaved changes and reload?", "放弃未保存的修改并重新读取？"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.document.reload()
        except (ValueError, OSError, YAMLError):
            self._show_error(text("Unable to read a valid configuration file.", "无法读取有效的配置文件。"))
            return
        self.edited_widgets.clear()
        set_language(self.document.data.get("language", "en"))
        self._build()
        self._navigation()
        self._dirty_changed()

    def closeEvent(self, event: QCloseEvent | None) -> None:
        if event is None:
            return
        if self.document.dirty:
            choice = QMessageBox.question(
                self, text("Unsaved changes", "未保存的修改"), text("Save changes before closing?", "关闭前保存修改？"),
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if choice == QMessageBox.StandardButton.Cancel or (choice == QMessageBox.StandardButton.Save and not self.save()):
                event.ignore()
                return
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    name = "yasb-settings-" + hashlib.sha256(str(Path(SCRIPT_PATH).resolve()).encode()).hexdigest()[:16]
    socket = QLocalSocket()
    socket.connectToServer(name)
    if socket.waitForConnected(300):
        socket.disconnectFromServer()
        return 0
    try:
        initialize_language()
        window = SettingsWindow()
    except (ValueError, OSError, YAMLError):
        QMessageBox.critical(None, text("Configuration error", "配置错误"), text("Unable to read the program configuration file.", "无法读取程序配置文件，请检查配置文件内容及访问权限。"))
        return 1
    server = QLocalServer(window)
    if not server.listen(name):
        raise RuntimeError(server.errorString())

    def activate() -> None:
        while server.hasPendingConnections():
            connection = server.nextPendingConnection()
            connection.disconnectFromServer()
            connection.deleteLater()
        window.showNormal()
        window.raise_()
        window.activateWindow()

    server.newConnection.connect(activate)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
