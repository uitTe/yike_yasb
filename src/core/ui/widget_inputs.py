"""仅编辑组件目录允许用户填写的必要信息。"""

from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.ui.widget_catalog import CATALOG, InputField, WidgetInfo, text, words


def option_value(options: dict[str, Any], field: InputField) -> Any:
    current = options
    for key in field.path:
        if key not in current:
            return deepcopy(field.default)
        current = current[key]
    return current


def set_option(options: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    target = options
    for key in path[:-1]:
        if key not in target:
            target[key] = {}
        target = target[key]
    target[path[-1]] = deepcopy(value)


def validate_inputs(info: WidgetInfo, options: dict[str, Any]) -> None:
    for field in info.fields:
        value = option_value(options, field)
        if field.required and (not value or isinstance(value, str) and not value.strip()):
            raise ValueError(text(f"Enter {words(field.title)}.", f"请填写{words(field.title)}。"))
        if field.kind == "servers":
            for entry in value:
                url = urlsplit(entry["url"])
                if url.scheme not in ("http", "https") or not url.hostname:
                    raise ValueError(text("Enter a full HTTP or HTTPS URL for each server.", "请为每个服务器填写完整的 HTTP 或 HTTPS 地址。"))


class WidgetInputs(QWidget):
    option_changed = pyqtSignal(object, object)

    def __init__(
        self, info: WidgetInfo, options: dict[str, Any], widgets: dict[str, Any], excluded: str | None = None,
    ):
        super().__init__()
        self.info = info
        self.options = deepcopy(options)
        self.widgets = widgets
        self.excluded = excluded
        self.controls: dict[tuple[str, ...], QWidget] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        if not info.fields:
            note = QLabel(text("Ready to use. No configuration is needed.", "添加后即可使用，无需填写配置。"))
            note.setProperty("role", "muted")
            note.setWordWrap(True)
            layout.addWidget(note)
        for field in info.fields:
            title = QLabel(words(field.title) + (text(" (required)", "（必填）") if field.required else ""))
            layout.addWidget(title)
            help_label = QLabel(words(field.help))
            help_label.setProperty("role", "muted")
            help_label.setWordWrap(True)
            layout.addWidget(help_label)
            self._field(layout, field)

    def _change(self, field: InputField, value: Any) -> None:
        set_option(self.options, field.path, value)
        self.option_changed.emit(field.path, value)

    def collected(self) -> dict[str, Any]:
        result = deepcopy(self.options)
        for field in self.info.fields:
            set_option(result, field.path, option_value(result, field))
        validate_inputs(self.info, result)
        return result

    def _field(self, layout: QVBoxLayout, field: InputField) -> None:
        value = option_value(self.options, field)
        if field.kind == "widgets":
            control = QListWidget()
            for name, entry in self.widgets.items():
                if name == self.excluded:
                    continue
                names = [key for key, value in self.widgets.items() if value["type"] == entry["type"]]
                title = words(CATALOG[entry["type"]].title)
                if len(names) > 1:
                    title += f" {names.index(name) + 1}"
                item = QListWidgetItem(title)
                item.setData(Qt.ItemDataRole.UserRole, name)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if name in value else Qt.CheckState.Unchecked)
                control.addItem(item)

            def members_changed():
                selected = [control.item(index).data(Qt.ItemDataRole.UserRole) for index in range(control.count())
                            if control.item(index).checkState() == Qt.CheckState.Checked]
                self._change(field, selected)

            control.itemChanged.connect(members_changed)
            layout.addWidget(control)
        elif field.kind in ("applications", "servers") or field.kind == "folder" and isinstance(value, list):
            control = QPlainTextEdit()
            control.setMaximumHeight(170)
            key = "launch" if field.kind == "applications" else "url"
            control.setPlainText("\n".join(value if field.kind == "folder" else (item[key] for item in value)))

            def lines_changed():
                if field.kind == "folder":
                    self._change(field, [line.strip() for line in control.toPlainText().splitlines() if line.strip()])
                    return
                previous = {item[key]: item for item in option_value(self.options, field)}
                entries = []
                for line in control.toPlainText().splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    if line in previous:
                        entries.append(deepcopy(previous[line]))
                    elif field.kind == "applications":
                        entries.append({"launch": line, "icon": "↗", "name": Path(line).stem})
                    else:
                        entries.append({"url": line, "name": line})
                self._change(field, entries)

            control.textChanged.connect(lines_changed)
            layout.addWidget(control)
        elif field.kind == "port":
            control = QSpinBox()
            control.setRange(1, 65535)
            control.setValue(value)
            control.valueChanged.connect(lambda number: self._change(field, number))
            layout.addWidget(control)
        else:
            control = QLineEdit(str(value or ""))
            control.textChanged.connect(lambda raw: self._change(field, raw))
            row = QHBoxLayout()
            row.addWidget(control, 1)
            if field.kind == "secret":
                control.setEchoMode(QLineEdit.EchoMode.Password)
                reveal = QPushButton(text("Show", "显示"))
                reveal.setCheckable(True)

                def reveal_secret(checked: bool):
                    control.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password)
                    reveal.setText(text("Hide", "隐藏") if checked else text("Show", "显示"))

                reveal.toggled.connect(reveal_secret)
                row.addWidget(reveal)
            elif field.kind in ("file", "folder"):
                browse = QPushButton(text("Browse", "浏览"))

                def choose():
                    if field.kind == "folder":
                        chosen = QFileDialog.getExistingDirectory(self, words(field.title))
                    else:
                        chosen, _ = QFileDialog.getOpenFileName(self, words(field.title))
                    if chosen:
                        control.setText(chosen)

                browse.clicked.connect(choose)
                row.addWidget(browse)
            layout.addLayout(row)
        control.setObjectName("input:" + ".".join(field.path))
        self.controls[field.path] = control
