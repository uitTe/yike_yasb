import asyncio
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication
from winrt.runtime import ApartmentType, init_apartment, uninit_apartment
from winrt.windows.ui.notifications import NotificationKinds
from winrt.windows.ui.notifications.management import UserNotificationListener, UserNotificationListenerAccessStatus


@dataclass(frozen=True)
class NotificationRecord:
    id: int
    app_id: str
    app_name: str
    created: datetime
    texts: tuple[str, ...]


@dataclass(frozen=True)
class NotificationSnapshot:
    allowed: bool
    records: tuple[NotificationRecord, ...] = ()


class NotificationQuery(QThread):
    loaded = pyqtSignal(object)

    def __init__(self, actions: tuple[int, ...], parent: QObject):
        super().__init__(parent)
        self.actions = actions

    async def _read(self) -> NotificationSnapshot:
        listener = UserNotificationListener.current
        if listener.get_access_status() != UserNotificationListenerAccessStatus.ALLOWED:
            return NotificationSnapshot(allowed=False)
        for notification_id in self.actions:
            listener.remove_notification(notification_id)
        records = []
        for notification in await listener.get_notifications_async(NotificationKinds.TOAST):
            texts = tuple(
                dict.fromkeys(
                    element.text
                    for binding in notification.notification.visual.bindings
                    for element in binding.get_text_elements()
                )
            )
            records.append(
                NotificationRecord(
                    notification.id,
                    notification.app_info.app_user_model_id,
                    notification.app_info.display_info.display_name,
                    notification.creation_time,
                    texts,
                )
            )
        records.sort(key=lambda record: record.created, reverse=True)
        return NotificationSnapshot(allowed=True, records=tuple(records))

    def run(self):
        init_apartment(ApartmentType.MULTI_THREADED)
        try:
            self.loaded.emit(asyncio.run(self._read()))
        finally:
            uninit_apartment()


class NotificationService(QObject):
    changed = pyqtSignal(object)
    _instance = None

    @classmethod
    def instance(cls) -> NotificationService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("通知服务需要 QApplication。")
        super().__init__(app)
        self.snapshot: NotificationSnapshot | None = None
        self._worker: NotificationQuery | None = None
        self._actions: deque[int] = deque()
        self._pending = False
        app.aboutToQuit.connect(self._shutdown)

    def refresh(self):
        if self._worker is not None:
            self._pending = True
            return
        actions = tuple(self._actions)
        self._actions.clear()
        self._pending = False
        self._worker = NotificationQuery(actions, self)
        self._worker.loaded.connect(self._receive)
        self._worker.finished.connect(self._finished)
        self._worker.start()

    def dismiss(self, notification_id: int):
        self.dismiss_many((notification_id,))

    def clear(self):
        notification_ids = tuple(record.id for record in self.snapshot.records) if self.snapshot is not None else ()
        self.dismiss_many(notification_ids)

    def dismiss_many(self, notification_ids: Iterable[int]):
        self._actions.extend(notification_ids)
        self.refresh()

    def _receive(self, snapshot: NotificationSnapshot):
        if snapshot != self.snapshot:
            self.snapshot = snapshot
            self.changed.emit(snapshot)

    def _finished(self):
        self._worker.deleteLater()
        self._worker = None
        if self._pending:
            self.refresh()

    def _shutdown(self):
        if self._worker is not None:
            self._worker.wait()
