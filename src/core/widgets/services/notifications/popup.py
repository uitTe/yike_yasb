import os
from collections.abc import Callable
from functools import lru_cache, partial

from lunar_python import Solar
from PyQt6.QtCore import QDate, QLocale, QPointF, QRect, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QApplication,
    QCalendarWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.utils.utilities import PopupWidget
from core.widgets.services.dnd.dnd_api import DndService
from core.widgets.services.notifications.service import NotificationService, NotificationSnapshot


@lru_cache(maxsize=512)
def lunar_labels(year: int, month: int, day: int) -> tuple[str, str, bool]:
    lunar = Solar.fromYmd(year, month, day).getLunar()
    day_text = lunar.getDayInChinese()
    festivals = lunar.getFestivals() or lunar.getOtherFestivals()
    solar_term = lunar.getJieQi()
    cell_text = (festivals[0] if festivals else solar_term) or (
        f"{lunar.getMonthInChinese()}月" if lunar.getDay() == 1 else day_text
    )
    details = list(dict.fromkeys([*festivals, *([solar_term] if solar_term else [])]))
    full_text = " · ".join([f"{lunar.getMonthInChinese()}月{day_text}", *details])
    return cell_text, full_text, bool(festivals or solar_term)


class NotificationCalendar(QCalendarWidget):
    def __init__(self, parent: QWidget, today: QDate):
        super().__init__(parent)
        self.today = today
        self.setProperty("class", "notification-calendar")
        self.setAccessibleName("日历")
        self.setLocale(QLocale("zh_CN"))
        self.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        self.setNavigationBarVisible(False)
        self.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.NoHorizontalHeader)
        self.setGridVisible(False)
        self.setSelectedDate(today)
        self.setFixedHeight(264)

    def paintCell(self, painter: QPainter, rect: QRect, date: QDate):
        painter.save()
        painter.setClipRect(rect)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(rect, QColor("#242424"))
        diameter = min(rect.width(), rect.height()) - 4
        circle = QRect(0, 0, diameter, diameter)
        circle.moveCenter(rect.center())
        painter.setPen(Qt.PenStyle.NoPen)
        if date == self.today:
            painter.setBrush(QColor("#4cc2ff"))
            painter.drawEllipse(circle)
        elif date == self.selectedDate():
            painter.setPen(QPen(QColor("#4cc2ff"), 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(circle)
        active_month = date.month() == self.monthShown() and date.year() == self.yearShown()
        foreground = "#101010" if date == self.today else ("#f2f2f2" if active_month else "#777777")
        painter.setPen(QColor(foreground))
        font = QFont(self.font())
        font.setPixelSize(14)
        painter.setFont(font)
        day_rect = QRect(rect.left(), circle.center().y() - 17, rect.width(), 19)
        painter.drawText(day_rect, Qt.AlignmentFlag.AlignCenter, str(date.day()))
        font.setPixelSize(10)
        painter.setFont(font)
        lunar_text, _, highlighted = lunar_labels(date.year(), date.month(), date.day())
        if date != self.today:
            painter.setPen(QColor("#4cc2ff" if highlighted else "#bcbcbc" if active_month else "#777777"))
        lunar_rect = QRect(rect.left(), circle.center().y() + 2, rect.width(), 14)
        painter.drawText(lunar_rect, Qt.AlignmentFlag.AlignCenter, lunar_text)
        painter.restore()


def label(text: str, class_name: str, parent: QWidget) -> QLabel:
    result = QLabel(text, parent)
    result.setTextFormat(Qt.TextFormat.PlainText)
    result.setProperty("class", class_name)
    return result


def button(text: str, name: str, action: Callable, parent: QWidget, class_name: str = "panel-button") -> QPushButton:
    result = QPushButton(text, parent)
    result.setProperty("class", class_name)
    result.setAccessibleName(name)
    result.setToolTip(name)
    result.setCursor(Qt.CursorShape.PointingHandCursor)
    result.clicked.connect(action)
    return result


class CalendarCollapseButton(QPushButton):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setProperty("class", "calendar-collapse-button")
        self.setFixedSize(32, 32)
        self.setCheckable(True)
        self.setChecked(True)
        self.setAccessibleName("折叠日历")
        self.setToolTip("折叠日历")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#f2f2f2"), 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        cx, cy = self.width() / 2, self.height() / 2
        direction = 1 if self.isChecked() else -1
        painter.drawPolyline(
            QPolygonF(
                [
                    QPointF(cx - 5, cy + 2.5 * direction),
                    QPointF(cx, cy - 2.5 * direction),
                    QPointF(cx + 5, cy + 2.5 * direction),
                ]
            )
        )


class DateNotificationPopup(PopupWidget):
    def __init__(self, parent: QWidget, today: Callable[[], QDate]):
        super().__init__(parent, round_corners=True, dark_mode=True, persistent=True)
        self.setProperty("class", "date-notification-popup")
        self.setWindowTitle("通知和日历")
        self.setAccessibleName("通知和日历")
        self._today = today
        self.service = NotificationService.instance()
        self.service.changed.connect(self._render_notifications)
        self._snapshot = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self._notifications = QFrame(self)
        self._notifications.setProperty("class", "notification-panel")
        notifications = QVBoxLayout(self._notifications)
        notifications.setContentsMargins(16, 14, 16, 14)
        notifications.setSpacing(12)
        header = QHBoxLayout()
        header.addWidget(label("通知", "panel-title", self))
        header.addStretch()
        self.dnd_button = button("", "请勿打扰", self._toggle_dnd, self)
        self.dnd_button.setCheckable(True)
        header.addWidget(self.dnd_button)
        notifications.addLayout(header)
        self.notification_scroll = QScrollArea(self)
        self.notification_scroll.setProperty("class", "notification-scroll")
        self.notification_scroll.setWidgetResizable(True)
        self.notification_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.notification_scroll.setFixedHeight(164)
        notifications.addWidget(self.notification_scroll)
        footer = QHBoxLayout()
        footer.addStretch()
        self.clear_button = button("全部清除", "清除全部通知", self.service.clear, self)
        self.clear_button.setEnabled(False)
        footer.addWidget(self.clear_button)
        notifications.addLayout(footer)
        layout.addWidget(self._notifications)
        self._calendar_panel = QFrame(self)
        self._calendar_panel.setProperty("class", "calendar-panel")
        calendar_layout = QVBoxLayout(self._calendar_panel)
        calendar_layout.setContentsMargins(16, 14, 16, 14)
        calendar_layout.setSpacing(12)
        date_header = QHBoxLayout()
        today_layout = QVBoxLayout()
        today_layout.setSpacing(4)
        self.date_label = label("", "panel-title", self)
        self.lunar_label = label("", "lunar-date", self)
        today_layout.addWidget(self.date_label)
        today_layout.addWidget(self.lunar_label)
        date_header.addLayout(today_layout)
        date_header.addStretch()
        self.collapse_button = CalendarCollapseButton(self)
        self.collapse_button.toggled.connect(self._toggle_calendar)
        date_header.addWidget(self.collapse_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        calendar_layout.addLayout(date_header)
        self.calendar_body = QWidget(self)
        body = QVBoxLayout(self.calendar_body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(6)
        month_header = QHBoxLayout()
        self.month_label = label("", "month-title", self)
        month_header.addWidget(self.month_label)
        month_header.addStretch()
        self.today_button = button("今天", "返回今天", self._go_today, self)
        month_header.addWidget(self.today_button)
        self.calendar = NotificationCalendar(self, today())
        self.previous_button = button("‹", "上一个月", self.calendar.showPreviousMonth, self, "panel-button chevron")
        self.next_button = button("›", "下一个月", self.calendar.showNextMonth, self, "panel-button chevron")
        month_header.addWidget(self.previous_button)
        month_header.addWidget(self.next_button)
        body.addLayout(month_header)
        weekdays = QHBoxLayout()
        weekdays.setSpacing(0)
        for day in "一二三四五六日":
            weekday = label(day, "weekday", self)
            weekday.setAlignment(Qt.AlignmentFlag.AlignCenter)
            weekdays.addWidget(weekday, 1)
        body.addLayout(weekdays)
        body.addWidget(self.calendar)
        self.calendar.currentPageChanged.connect(self._month_changed)
        calendar_layout.addWidget(self.calendar_body)
        layout.addWidget(self._calendar_panel)
        self._month_changed(self.calendar.yearShown(), self.calendar.monthShown())
        self._timer = QTimer(self)
        self._timer.setInterval(3000)
        self._timer.timeout.connect(self._refresh)
        self._render_notifications(self.service.snapshot)

    def _render_notifications(self, snapshot: NotificationSnapshot | None):
        if self._snapshot is not None and self._snapshot == snapshot:
            return
        self._snapshot = snapshot
        self.clear_button.setEnabled(snapshot is not None and snapshot.allowed and bool(snapshot.records))
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(8)
        if snapshot is None or not snapshot.allowed or not snapshot.records:
            text = (
                "正在读取通知…"
                if snapshot is None
                else ("没有新通知" if snapshot.allowed else "请在 Windows 设置中允许 YASB 访问通知。")
            )
            empty = label(text, "empty-notifications", content)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setWordWrap(True)
            layout.addWidget(empty, 1)
            if snapshot is not None and not snapshot.allowed:
                layout.addWidget(button("通知访问设置", "打开通知访问设置", self._open_access_settings, content))
        else:
            for record in snapshot.records:
                card = QFrame(content)
                card.setProperty("class", "notification-card")
                card.setAccessibleName(f"{record.app_name} 通知")
                card_layout = QVBoxLayout(card)
                card_layout.setContentsMargins(12, 10, 12, 10)
                card_layout.setSpacing(6)
                heading = QHBoxLayout()
                app_name = label(record.app_name, "notification-app", card)
                app_name.setWordWrap(True)
                heading.addWidget(app_name, 1)
                heading.addWidget(label(record.created.astimezone().strftime("%m/%d %H:%M"), "notification-time", card))
                heading.addWidget(
                    button("×", "清除此通知", partial(self.service.dismiss, record.id), card, "dismiss-button")
                )
                card_layout.addLayout(heading)
                for index, text in enumerate(record.texts):
                    line = label(text, "notification-title" if index == 0 else "notification-body", card)
                    line.setWordWrap(True)
                    line.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                    card_layout.addWidget(line)
                layout.addWidget(card)
            layout.addStretch()
        previous = self.notification_scroll.takeWidget()
        self.notification_scroll.setWidget(content)
        if previous is not None:
            previous.deleteLater()

    @staticmethod
    def _open_access_settings():
        os.startfile("ms-settings:privacy-notifications")

    def _month_changed(self, year: int, month: int):
        self.month_label.setText(f"{year}年{month}月")

    def _go_today(self):
        today = self._today()
        self.calendar.setSelectedDate(today)
        self.calendar.setCurrentPage(today.year(), today.month())

    def _toggle_calendar(self, expanded: bool):
        self.calendar_body.setVisible(expanded)
        self.collapse_button.setAccessibleName("折叠日历" if expanded else "展开日历")
        self.collapse_button.setToolTip(self.collapse_button.accessibleName())
        self._fit()

    def _update_dnd(self):
        status = DndService.get_status()
        self.dnd_button.setEnabled(status != "unknown")
        self.dnd_button.setChecked(status in ("priority", "alarms"))
        self.dnd_button.setText("请勿打扰已开启" if self.dnd_button.isChecked() else "请勿打扰")

    def _toggle_dnd(self):
        DndService.set_status("priority" if self.dnd_button.isChecked() else "disabled")
        self._update_dnd()

    def _refresh(self):
        today = self._today()
        self.date_label.setText(QLocale("zh_CN").toString(today, "M月d日 dddd"))
        self.lunar_label.setText(lunar_labels(today.year(), today.month(), today.day())[1])
        if today != self.calendar.today:
            self.calendar.today = today
            self.calendar.updateCells()
        self._update_dnd()
        self.service.refresh()

    def _fit(self):
        screen = QApplication.screenAt(self._parent.mapToGlobal(self._parent.rect().center()))
        if screen is None:
            raise RuntimeError("无法确定日期通知面板所在的屏幕。")
        self.setFixedWidth(min(380, screen.availableGeometry().width() - 16))
        self.notification_scroll.setFixedHeight(max(72, min(164, screen.availableGeometry().height() - 530)))
        self._calendar_panel.layout().activate()
        self.layout().invalidate()
        self.layout().activate()
        self.setFixedHeight(self.sizeHint().height())
        config = self._parent.config.calendar
        self.setPosition(config.alignment, config.direction, config.offset_left, config.offset_top)

    def showEvent(self, event):
        self._refresh()
        self._go_today()
        self._fit()
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)
