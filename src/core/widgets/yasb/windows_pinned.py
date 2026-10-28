import os
from pathlib import Path
from typing import ClassVar, override

from pydantic import BaseModel, Field
from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QFileSystemWatcher,
    QIODevice,
    QMimeData,
    QObject,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSaveFile,
    QSize,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QDrag,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QEnterEvent,
    QIcon,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QShowEvent,
)
from PyQt6.QtWidgets import QApplication, QFrame, QMenu, QPushButton

from core.utils.icons.service import IconService
from core.utils.icons.sources import FileIcon
from core.utils.win32.system_function import start_menu
from core.utils.win32.utils import apply_qmenu_style
from core.validation.widgets.yasb.windows_pinned import WindowsPinnedConfig
from core.widgets.base import BaseWidget
from settings import SCRIPT_PATH


class PinnedAppsState(BaseModel, extra="forbid"):
    order: list[str] = Field(default_factory=list)
    excluded: list[str] = Field(default_factory=list)


class WindowsPinnedSource(QObject):
    changed = pyqtSignal()
    _instance: ClassVar[WindowsPinnedSource | None] = None

    def __init__(self) -> None:
        super().__init__()
        self.directory = Path(os.environ["APPDATA"]) / "Microsoft/Internet Explorer/Quick Launch/User Pinned/TaskBar"
        self.entries: tuple[Path, ...] = ()
        self.state_path = (
            Path(os.environ.get("YASB_DATA_HOME", str(Path(SCRIPT_PATH) / "data"))) / "windows_pinned.json"
        )
        self._state = (
            PinnedAppsState.model_validate_json(self.state_path.read_bytes())
            if self.state_path.exists()
            else PinnedAppsState()
        )
        if len(self._state.order) != len(set(self._state.order)):
            raise ValueError("固定应用排序文件包含重复项目")
        self._snapshot: tuple[tuple[str, int, int], ...] = ()
        self._watcher = QFileSystemWatcher(self)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(150)
        self._debounce.timeout.connect(self.refresh)
        self._watcher.directoryChanged.connect(lambda _path: self._debounce.start())
        self._watcher.fileChanged.connect(lambda _path: self._debounce.start())
        self._poll = QTimer(self)
        self._poll.setInterval(2000)
        self._poll.timeout.connect(self.refresh)
        self._poll.start()
        self.refresh()

    @classmethod
    def instance(cls) -> WindowsPinnedSource:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def refresh(self) -> None:
        ranks = {name: index for index, name in enumerate(self._state.order)}
        paths = sorted(
            (path for path in self.directory.glob("*.lnk") if path.name not in self._state.excluded),
            key=lambda path: (ranks.get(path.name, len(ranks)), path.name.casefold()),
        )
        snapshot = tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in paths)
        watched: set[str] = set()
        if self.directory.is_dir():
            watched.add(str(self.directory))
        current = set(self._watcher.files()) | set(self._watcher.directories())
        if current - watched:
            self._watcher.removePaths(sorted(current - watched))
        if watched - current:
            failed = self._watcher.addPaths(sorted(watched - current))
            if failed:
                raise OSError(f"无法监听系统固定快捷方式：{failed}")
        if snapshot != self._snapshot:
            self._snapshot = snapshot
            self.entries = tuple(paths)
            self.changed.emit()

    def move(self, path: Path, index: int) -> None:
        entries = list(self.entries)
        entries.remove(path)
        entries.insert(index, path)
        if tuple(entries) == self.entries:
            return
        self._save_state(PinnedAppsState(order=[entry.name for entry in entries], excluded=self._state.excluded))
        self.entries = tuple(entries)
        self.changed.emit()

    def unpin(self, path: Path) -> None:
        if path not in self.entries:
            raise ValueError(f"应用未在 Dock 固定：{path}")
        self._save_state(PinnedAppsState(order=self._state.order, excluded=[*self._state.excluded, path.name]))
        self.refresh()

    def _save_state(self, state: PinnedAppsState) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        output = QSaveFile(str(self.state_path))
        if not output.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError(output.errorString())
        data = state.model_dump_json().encode("utf-8")
        if output.write(data) != len(data) or not output.commit():
            raise OSError(output.errorString())
        self._state = state


class DockButton(QPushButton):
    def __init__(self, icon_size: int) -> None:
        super().__init__()
        self.base_icon_size = icon_size
        self.maximum_icon_size = round(icon_size * 1.5)
        self._hovered = False
        self.setIconSize(QSize(icon_size, icon_size))
        self.setFixedSize(self.base_icon_size + 16, self.maximum_icon_size + 8)
        self._hover_animation = QPropertyAnimation(self, b"iconSize", self)
        self._hover_animation.setDuration(140)
        self._hover_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_animation.valueChanged.connect(lambda _size: self.update())

    @override
    def paintEvent(self, event: QPaintEvent | None) -> None:
        size = self.iconSize().width()
        pixmap = self.icon().pixmap(QSize(self.maximum_icon_size, self.maximum_icon_size), self.devicePixelRatioF())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        target = QRect((self.width() - size) // 2, self.height() - size - 4, size, size)
        painter.drawPixmap(target, pixmap, pixmap.rect())

    def set_hovered(self, hovered: bool) -> None:
        if self._hovered == hovered:
            return
        self._hovered = hovered
        size = self.maximum_icon_size if hovered else self.base_icon_size
        self._hover_animation.stop()
        self._hover_animation.setStartValue(self.iconSize())
        self._hover_animation.setEndValue(QSize(size, size))
        self._hover_animation.start()

    @override
    def enterEvent(self, event: QEnterEvent | None) -> None:
        super().enterEvent(event)
        self.set_hovered(True)

    @override
    def leaveEvent(self, event: QEvent | None) -> None:
        super().leaveEvent(event)
        self.set_hovered(False)


class PinnedAppButton(DockButton):
    def __init__(self, path: Path, icon_size: int) -> None:
        super().__init__(icon_size)
        self.path = path
        self._press_position: QPoint | None = None

    @override
    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event is not None and event.button() == Qt.MouseButton.LeftButton:
            self._press_position = event.position().toPoint()
        super().mousePressEvent(event)

    @override
    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if event is not None and event.buttons() & Qt.MouseButton.LeftButton and self._press_position is not None:
            distance = (event.position().toPoint() - self._press_position).manhattanLength()
            if distance >= QApplication.startDragDistance():
                self._press_position = None
                self.setDown(False)
                drag = QDrag(self)
                mime = QMimeData()
                mime.setData("application/x-yasb-pinned-app", b"")
                drag.setMimeData(mime)
                drag.setPixmap(self.icon().pixmap(self.iconSize()))
                drag.setHotSpot(QPoint(self.iconSize().width() // 2, self.iconSize().height() // 2))
                drag.exec(Qt.DropAction.MoveAction)
                return
        super().mouseMoveEvent(event)


class WindowsPinnedWidget(BaseWidget):
    validation_schema = WindowsPinnedConfig

    def __init__(self, config: WindowsPinnedConfig) -> None:
        super().__init__(class_name="windows-pinned-widget")
        self.config = config
        self.buttons: dict[Path, PinnedAppButton] = {}
        self.source = WindowsPinnedSource.instance()
        self._icons = IconService.instance()
        self.setAcceptDrops(True)
        self.setMinimumHeight(round(self.config.icon_size * 1.5) + 8)
        self.start_button = DockButton(self.config.icon_size)
        self.start_button.setProperty("class", "pinned-app")
        self.start_button.setObjectName("dock-start-button")
        self.start_button.setAccessibleName("开始")
        icon = QIcon(str(Path(SCRIPT_PATH) / "assets/images/start.svg"))
        if icon.isNull():
            raise RuntimeError("开始按钮图标无法加载")
        self.start_button.setIcon(icon)
        if self.config.tooltip:
            self.start_button.setToolTip("开始")
        self.start_button.clicked.connect(lambda: start_menu(int(self.window().winId())))
        self.widget_layout.addWidget(self.start_button, 0, Qt.AlignmentFlag.AlignBottom)
        self._drop_indicator = QFrame(self)
        self._drop_indicator.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._drop_indicator.setStyleSheet("background-color: #8bbcff; border: none; border-radius: 1px;")
        self._drop_indicator.hide()
        self.source.changed.connect(self._refresh_entries)
        self._icons.icons_changed.connect(self._refresh_icons)
        self._refresh_entries()

    def _refresh_entries(self) -> None:
        for path in self.buttons.keys() - set(self.source.entries):
            button = self.buttons.pop(path)
            self.widget_layout.removeWidget(button)
            button.deleteLater()
        for index, path in enumerate(self.source.entries):
            if path not in self.buttons:
                button = PinnedAppButton(path, self.config.icon_size)
                button.setProperty("class", "pinned-app")
                button.setProperty("shortcut_path", str(path))
                button.setAccessibleName(path.stem)
                if self.config.tooltip:
                    button.setToolTip(path.stem)
                button.clicked.connect(lambda _checked=False, shortcut=path: os.startfile(shortcut))
                button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                button.customContextMenuRequested.connect(
                    lambda position, shortcut=path, target=button: self._show_app_menu(
                        shortcut, target.mapToGlobal(position)
                    )
                )
                self.buttons[path] = button
            self.widget_layout.insertWidget(index + 1, self.buttons[path], 0, Qt.AlignmentFlag.AlignBottom)
        self._refresh_icons()

    def _show_app_menu(self, path: Path, position: QPoint) -> None:
        menu = QMenu(self)
        apply_qmenu_style(menu)
        menu.setProperty("class", "context-menu dark")
        action = menu.addAction("从 Dock 取消固定")
        action.triggered.connect(lambda: self.source.unpin(path))
        menu.exec(position)
        menu.deleteLater()

    def _drop_index(self, position: QPoint, source: PinnedAppButton) -> int:
        remaining = [path for path in self.source.entries if path != source.path]
        for index, path in enumerate(remaining):
            button = self.buttons[path]
            center = button.mapTo(self, button.rect().center())
            if position.x() < center.x():
                return index
        return len(remaining)

    @override
    def dragEnterEvent(self, event: QDragEnterEvent | None) -> None:
        if event is not None:
            source = event.source()
            if isinstance(source, PinnedAppButton) and source.path in self.buttons:
                event.acceptProposedAction()
            else:
                event.ignore()

    @override
    def dragMoveEvent(self, event: QDragMoveEvent | None) -> None:
        if event is None:
            return
        source = event.source()
        if not isinstance(source, PinnedAppButton) or source.path not in self.buttons:
            event.ignore()
            return
        index = self._drop_index(event.position().toPoint(), source)
        remaining = [self.buttons[path] for path in self.source.entries if path != source.path]
        if remaining:
            button = remaining[min(index, len(remaining) - 1)]
            position = button.mapTo(self, QPoint(0, 0))
            x = position.x() - 1 if index < len(remaining) else position.x() + button.width() + 1
            self._drop_indicator.setGeometry(x, position.y() + 4, 2, button.height() - 8)
            self._drop_indicator.show()
            self._drop_indicator.raise_()
        event.acceptProposedAction()

    @override
    def dragLeaveEvent(self, event: QDragLeaveEvent | None) -> None:
        self._drop_indicator.hide()
        if event is not None:
            event.accept()

    @override
    def dropEvent(self, event: QDropEvent | None) -> None:
        self._drop_indicator.hide()
        if event is None:
            return
        source = event.source()
        if isinstance(source, PinnedAppButton) and source.path in self.buttons:
            self.source.move(source.path, self._drop_index(event.position().toPoint(), source))
            event.acceptProposedAction()
        else:
            event.ignore()

    def _refresh_icons(self) -> None:
        for path, button in self.buttons.items():
            icon = self._icons.get_icon(FileIcon(str(path)), button.maximum_icon_size, self.devicePixelRatioF())
            if icon is None:
                raise RuntimeError(f"系统固定快捷方式没有可用图标：{path}")
            button.setIcon(QIcon(icon))

    @override
    def showEvent(self, event: QShowEvent | None) -> None:
        super().showEvent(event)
        self._refresh_icons()
