from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PyQt6.QtCore import QDate, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QMouseEvent, QPainter, QPaintEvent
from PyQt6.QtWidgets import QPushButton

from core.events.service import EventService
from core.validation.widgets.yasb.clock import ClockConfig
from core.widgets.services.notifications.popup import DateNotificationPopup
from core.widgets.services.notifications.service import NotificationService, NotificationSnapshot
from core.widgets.services.notifications.windows_notification import WindowsNotificationEventListener
from core.widgets.yasb.clock import ClockWidget
from settings import SCRIPT_PATH


class NotificationBell(QPushButton):
    def __init__(self):
        super().__init__()
        path = Path(SCRIPT_PATH) / "assets/images/notification-bell.svg"
        if not path.is_file():
            raise FileNotFoundError(path)
        self._icon = QIcon(str(path))
        if self._icon.isNull():
            raise RuntimeError(f"无法加载通知图标：{path}")
        self._unread = False
        self.setFixedSize(24, 24)
        self.setIconSize(QSize(16, 16))
        self.setAccessibleName("通知铃铛")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
        self.setProperty("class", "notification-bell")

    def set_unread(self, unread: bool):
        self._unread = unread
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent | None):
        if event is not None and event.button() == Qt.MouseButton.RightButton:
            self.clicked.emit(False)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event: QPaintEvent | None):
        painter = QPainter(self)
        icon_rect = QRect(0, 0, self.iconSize().width(), self.iconSize().height())
        icon_rect.moveCenter(self.rect().center())
        self._icon.paint(painter, icon_rect)
        if self._unread:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#4cc2ff"))
            painter.drawEllipse(17, 3, 4, 4)


class NotificationClockWidget(ClockWidget):
    validation_schema = ClockConfig
    event_listener = WindowsNotificationEventListener
    notification_update = pyqtSignal(int)

    def __init__(self, config: ClockConfig):
        super().__init__(config)
        self._widget_frame.setProperty("class", f"widget notification-clock-widget {config.class_name}")
        self.setAccessibleName("日期和通知")
        for label in (*self._widgets, *self._widgets_alt):
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._notification_icon = NotificationBell()
        self._widget_container_layout.addWidget(self._notification_icon)
        self._notification_popup = None
        self._notification_icon.clicked.connect(self._toggle_panel)
        self.register_callback("toggle_calendar", self._toggle_panel)
        self.register_callback("toggle_notification", self._toggle_panel)
        EventService().register_event("WindowsNotificationUpdate", self.notification_update)
        self.notification_update.connect(self._on_notification_update)
        self._notification_service = NotificationService.instance()
        self._notification_service.changed.connect(self._on_snapshot)
        self._notification_service.refresh()

    def _on_notification_update(self, count: int):
        self._notification_icon.set_unread(count > 0)
        self._notification_service.refresh()

    def _on_snapshot(self, snapshot: NotificationSnapshot):
        if snapshot.allowed:
            self._notification_icon.set_unread(bool(snapshot.records))

    def _today(self) -> QDate:
        now = datetime.now(ZoneInfo(self._active_tz)) if self._active_tz else datetime.now().astimezone()
        return QDate(now.year, now.month, now.day)

    def _toggle_panel(self):
        if self._notification_popup is None:
            self._notification_popup = DateNotificationPopup(self, self._today)
        if self._notification_popup.isVisible() and not self._notification_popup._is_closing:
            self._notification_popup.hide_animated()
        else:
            self._notification_popup.show()
