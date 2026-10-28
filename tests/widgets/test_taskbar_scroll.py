"""使用真实 Windows 窗口验证页签溢出列表和高度。"""

import atexit
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, QRect, Qt
from PyQt6.QtGui import QCursor, QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QLayout, QPushButton, QScrollArea, QWidget

from core.utils.css_processor import CSSProcessor
from core.utils.win32.bindings.user32 import GetForegroundWindow, GetWindowText, user32
from core.validation.widgets.yasb.taskbar import TaskbarConfig
from core.widgets.registry import WIDGET_REGISTRY
from core.widgets.services.taskbar.pin_manager import PinManager
from core.widgets.yasb.taskbar import TaskbarWidget


@pytest.fixture
def tabs(qapp: QApplication) -> Iterator[TaskbarWidget]:
    if qapp.platformName() != "windows":
        pytest.skip("此检查需要 Windows 原生窗口和 ShellHook")
    cursor = QCursor.pos()
    QCursor.setPos(10, 800)

    class MeasuredTaskbar(TaskbarWidget):
        def __init__(self, config: TaskbarConfig):
            self.refreshes = 0
            self.activated = []
            super().__init__(config)

        def _update_tab_overflow(self) -> None:
            self.refreshes += 1
            super()._update_tab_overflow()

        def _activate_overflow_tab(self, hwnd: int, _checked: bool = False) -> None:
            self.activated.append(hwnd)
            super()._activate_overflow_tab(hwnd, _checked)

    windows = []
    for index in range(7):
        window = QWidget()
        window.setWindowTitle(f"YASB 页签列表验证 {index + 1}")
        window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        window.resize(280, 140)
        window.move(300 + index * 10, 200 + index * 10)
        window.show()
        windows.append(window)
    widget = MeasuredTaskbar(
        TaskbarConfig(
            show_pinned=False,
            tab_mode=True,
            animation={"enabled": False},
            title_label={"enabled": True, "show": "always"},
        )
    )
    stylesheet = Path(__file__).resolve().parents[2] / "src/defaults/styles.css"
    widget.setStyleSheet(CSSProcessor(str(stylesheet)).process())
    widget.setFixedHeight(34)
    widget.setFixedWidth(128)
    host = QWidget()
    layout = QHBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
    layout.addWidget(widget)
    host.move(50, 100)
    host.setWindowFlag(Qt.WindowType.Tool)
    host.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
    host.show()
    host.raise_()
    host.activateWindow()
    QTest.qWait(300)
    assert all(int(window.winId()) in widget.hwnd_to_widget for window in windows)
    try:
        yield widget
    finally:
        widget._stop_events()
        atexit.unregister(widget._stop_events)
        if not sip.isdeleted(widget):
            widget.close()
            widget.deleteLater()
        host.close()
        host.deleteLater()
        for window in windows:
            window.close()
            window.deleteLater()
        QCursor.setPos(cursor)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        WIDGET_REGISTRY.pop(f"{__name__}.MeasuredTaskbar")


def test_layout_burst_is_coalesced(tabs: TaskbarWidget):
    previous = tabs.refreshes
    for _ in range(100):
        QCoreApplication.sendEvent(tabs._widget_container, QEvent(QEvent.Type.LayoutRequest))
    QTest.qWait(50)
    assert 1 <= tabs.refreshes - previous <= 3


def test_shutdown_after_tab_controls_are_destroyed(tabs: TaskbarWidget):
    tabs._stop_events()
    sip.delete(tabs)
    tabs._stop_events()


def test_layout_settles_and_only_complete_tabs_are_visible(tabs: TaskbarWidget):
    buttons = [tabs._layout_widget_at(index) for index in range(tabs._widget_container_layout.count())]
    groups = {}
    for button in buttons:
        groups.setdefault(button.property("tab_app_id") or f"window:{button.hwnd}", []).append(button)
    content_width = sum(max(button.width() for button in group) + 15 * (len(group) - 1) for group in groups.values())
    assert content_width > 0
    margins = tabs.width() - tabs.widget_layout.contentsRect().width()
    for width in (28, 120, content_width - 1, content_width, content_width + 1, 200):
        tabs.setFixedWidth(width + margins)
        QTest.qWait(80)
        previous = tabs.refreshes
        QTest.qWait(50)
        assert tabs.refreshes == previous, f"宽度 {width} 下布局持续刷新"
        assert tabs._tab_overflow.isHidden() == (content_width <= width)
        visible = [button for button in buttons if not button.isHidden()]
        assert set(tabs._hidden_tabs) == set(buttons) - set(visible)
        for button in visible:
            assert tabs._widget_container.rect().contains(button.geometry())
        tabs._populate_tab_menu()
        assert [action.data() for action in tabs._tab_menu.actions()] == [button.hwnd for button in tabs._hidden_tabs]


@pytest.mark.parametrize("minimized", [False, True])
def test_hover_list_keeps_open_and_click_activates_real_window(tabs: TaskbarWidget, minimized: bool):
    button = next(tab for tab in tabs._hidden_tabs if str(tab.property("tab_title")).startswith("YASB 页签列表验证"))
    if minimized:
        window = QWidget.find(button.hwnd)
        assert window is not None
        window.showMinimized()
        QTest.qWait(100)
    QCursor.setPos(tabs._tab_overflow.mapToGlobal(tabs._tab_overflow.rect().center()))
    QTest.qWait(100)
    assert QApplication.widgetAt(QCursor.pos()) is tabs._tab_overflow
    assert tabs._tab_menu.isVisible()
    assert tabs._tab_menu.parentWidget() is tabs.window()
    assert not tabs.testAttribute(Qt.WidgetAttribute.WA_NativeWindow)
    assert not any(child.testAttribute(Qt.WidgetAttribute.WA_NativeWindow) for child in tabs.findChildren(QWidget))
    action = next(action for action in tabs._tab_menu.actions() if action.data() == button.hwnd)
    position = tabs._tab_menu.actionGeometry(action).center()
    QCursor.setPos(tabs._tab_menu.mapToGlobal(position))
    QTest.qWait(450)
    assert tabs._tab_menu.isVisible(), (position, tabs._tab_menu.frameGeometry(), QCursor.pos())
    assert tabs._tab_menu.actionAt(position).data() == button.hwnd
    # 使用 Windows 实际输入，使窗口激活获得系统前台权限。
    assert tabs._tab_menu.isAncestorOf(QApplication.widgetAt(QCursor.pos()))
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    QTest.qWait(150)
    assert tabs.activated == [button.hwnd], (tabs._tab_menu.activeAction(), position, tabs._tab_menu.geometry())
    assert GetForegroundWindow() == button.hwnd
    assert not tabs._tab_menu.isVisible()


def test_hover_list_closes_when_pointer_leaves(tabs: TaskbarWidget):
    QCursor.setPos(tabs._tab_overflow.mapToGlobal(tabs._tab_overflow.rect().center()))
    QTest.qWait(100)
    assert QApplication.widgetAt(QCursor.pos()) is tabs._tab_overflow
    assert tabs._tab_menu.isVisible()
    QCursor.setPos(tabs.mapToGlobal(QPoint(0, -50)))
    QTest.qWait(450)
    assert not tabs._tab_menu.isVisible()


def test_visible_list_updates_after_native_window_rename_and_close(tabs: TaskbarWidget):
    button = next(tab for tab in tabs._hidden_tabs if str(tab.property("tab_title")).startswith("YASB 页签列表验证"))
    window = QWidget.find(button.hwnd)
    assert window is not None
    QCursor.setPos(tabs._tab_overflow.mapToGlobal(tabs._tab_overflow.rect().center()))
    QTest.qWait(100)
    assert tabs._tab_menu.isVisible()
    window.setWindowTitle("YASB 隐藏应用标题更新 & 验证")
    QTest.qWait(500)
    action = next(action for action in tabs._tab_menu.actions() if action.data() == button.hwnd)
    assert action.text() == "YASB 隐藏应用标题更新 && 验证"
    window.close()
    QTest.qWait(500)
    assert button.hwnd not in [action.data() for action in tabs._tab_menu.actions()]
    assert tabs._tab_menu.isVisible()
    width = sum(tabs._layout_widget_at(index).width() for index in range(tabs._widget_container_layout.count()))
    tabs.setFixedWidth(width + 100)
    QTest.qWait(100)
    assert tabs._tab_overflow.isHidden()
    assert not tabs._tab_menu.isVisible()
    assert not tabs._hidden_tabs


def test_tab_height_and_position_stay_fixed_when_wheeling(tabs: TaskbarWidget):
    tabs.setFixedWidth(4096)
    QTest.qWait(50)
    assert not tabs.findChildren(QScrollArea)
    for height in (30, 34, 48, 34):
        tabs.setFixedHeight(height)
        QTest.qWait(50)
        before = tabs._widget_container.geometry()
        visible = [tab for tab in tabs.hwnd_to_widget.values() if not tab.isHidden()]
        for delta in (120, -120, 120):
            position = tabs._widget_container.rect().center()
            event = QWheelEvent(
                QPointF(position),
                QPointF(tabs._widget_container.mapToGlobal(position)),
                QPoint(),
                QPoint(0, delta),
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
                Qt.ScrollPhase.NoScrollPhase,
                False,
            )
            QCoreApplication.sendEvent(tabs._widget_container, event)
        assert tabs._widget_container.geometry() == before
        for tab in visible:
            assert tab.height() == tabs.widget_layout.contentsRect().height()
            assert tabs._widget_container.rect().contains(tab.geometry())


def test_close_button_is_centered_inside_tab_content(tabs: TaskbarWidget):
    tabs.setFixedWidth(4096)
    QTest.qWait(50)
    for height in (30, 34, 48):
        tabs.setFixedHeight(height)
        QTest.qWait(50)
        for tab in tabs.hwnd_to_widget.values():
            if tab.isHidden():
                continue
            tabs.set_tab_hover(tab, True)
            QCoreApplication.processEvents()
            close = next(button for button in tab.findChildren(QPushButton) if button.property("tab_action") == "close")
            assert close.isVisible()
            rect = QRect(close.mapTo(tab, QPoint()), close.size())
            assert tab.contentsRect().contains(rect), (tab.contentsRect(), rect)
            assert abs(rect.center().y() - tab.contentsRect().center().y()) <= 1
            title = next(label for label in tab.findChildren(QLabel) if label.property("class") == "app-title")
            title_rect = QRect(title.mapTo(tab, QPoint()), title.size())
            assert title_rect.right() < rect.left()
            tabs.set_tab_hover(tab, False)


def test_overflow_follows_visible_tabs_and_has_hover_background(tabs: TaskbarWidget):
    assert tabs._hidden_tabs
    assert tabs._tab_overflow.x() == tabs._widget_container.geometry().right() + 1, {
        "tab": tabs.geometry(), "frame": tabs._widget_frame.geometry(),
        "layout": tabs.widget_layout.contentsRect(), "overflow": tabs._tab_overflow.geometry(),
        "container": tabs._widget_container.geometry(), "parent": tabs._tab_overflow.parentWidget(),
    }
    normal = tabs._tab_overflow.grab().toImage().pixelColor(5, tabs._tab_overflow.height() // 2)
    tabs._show_tab_overflow()
    QCoreApplication.processEvents()
    assert tabs._tab_menu.isVisible()
    assert tabs._tab_overflow.isDown()
    hovered = tabs._tab_overflow.grab().toImage().pixelColor(5, tabs._tab_overflow.height() // 2)
    assert normal != hovered


def test_overflow_close_button_closes_only_its_native_window(tabs: TaskbarWidget):
    helper = Path(__file__).resolve().parents[1] / "support/native_task_window.py"
    process = subprocess.Popen([sys.executable, str(helper), "YASB 独立窗口关闭验证"], stdout=subprocess.PIPE, text=True)
    try:
        assert process.stdout is not None
        hwnd = int(process.stdout.readline())
        QTest.qWait(300)
        assert hwnd in tabs.hwnd_to_widget
        tabs._show_tab_overflow()
        QCoreApplication.processEvents()
        action = next(action for action in tabs._tab_menu.actions() if action.data() == hwnd)
        row = action.defaultWidget()
        close = next(button for button in row.findChildren(QPushButton) if button.property("class") == "tab-overflow-close")
        others = set(tabs.hwnd_to_widget) - {hwnd}
        assert close.isVisible()
        QTest.mouseClick(close, Qt.MouseButton.LeftButton)
        QTest.qWait(500)
        assert process.poll() == 0
        assert hwnd not in tabs.hwnd_to_widget
        assert others <= set(tabs.hwnd_to_widget)
        tabs._show_tab_overflow()
        QCoreApplication.processEvents()
        assert hwnd not in [action.data() for action in tabs._tab_menu.actions()]
        assert tabs._tab_menu.isVisible()
        assert not tabs.activated
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=5)


def test_overflow_application_button_restores_its_window(tabs: TaskbarWidget):
    tab = next(tab for tab in tabs._hidden_tabs if str(tab.property("tab_title")).startswith("YASB 页签列表验证"))
    hwnd = tab.hwnd
    window = QWidget.find(hwnd)
    assert window is not None
    window.showMinimized()
    QTest.qWait(100)
    assert window.isMinimized()
    tabs._show_tab_overflow()
    QCoreApplication.processEvents()
    action = next(action for action in tabs._tab_menu.actions() if action.data() == hwnd)
    application = next(button for button in action.defaultWidget().findChildren(QPushButton)
                       if button.property("class") == "tab-overflow-application")
    QTest.mouseClick(application, Qt.MouseButton.LeftButton)
    QTest.qWait(150)
    assert tabs.activated == [hwnd]
    assert not window.isMinimized()
    assert not tabs._tab_menu.isVisible()


def test_same_application_tabs_overlap_by_fifteen_pixels(tabs: TaskbarWidget):
    tabs.setFixedWidth(4096)
    QTest.qWait(80)
    native = sorted((tab for tab in tabs.hwnd_to_widget.values()
                     if str(tab.property("tab_title")).startswith("YASB 页签列表验证")), key=lambda tab: tab.x())
    assert len(native) == 7
    assert len({tab.property("tab_app_id") for tab in native}) == 1
    assert all(not tab.isHidden() for tab in native)
    assert [tab.x() - native[0].x() for tab in native] == [index * 15 for index in range(7)]
    assert len({tab.width() for tab in native}) == 1
    assert native[-1].geometry().right() - native[0].x() + 1 == native[0].width() + 90
    assert native[0].width() + 90 < sum(tab.width() for tab in native)
    for tab in native[:-1]:
        position = QPoint(tab.x() + 10, tab.geometry().center().y())
        assert tabs._widget_container._find_button_at(position) is tab
    assert tabs._widget_container._find_button_at(native[-1].geometry().center()) is native[-1]


def test_selected_window_moves_to_front_of_its_application(tabs: TaskbarWidget):
    tabs.setFixedWidth(4096)
    QTest.qWait(80)
    native = sorted((tab for tab in tabs.hwnd_to_widget.values()
                     if str(tab.property("tab_title")).startswith("YASB 页签列表验证")), key=lambda tab: tab.x())
    target = native[0]
    tabs.ensure_foreground(target.hwnd)
    QTest.qWait(100)
    assert target.x() == max(tab.x() for tab in native)
    assert tabs._widget_container._find_button_at(target.geometry().center()) is target
    assert len(tabs.hwnd_to_widget) == len(set(tabs.hwnd_to_widget.values()))


def test_partial_application_group_keeps_the_selected_window_visible(tabs: TaskbarWidget):
    tabs.setFixedWidth(4096)
    QTest.qWait(80)
    native = sorted((tab for tab in tabs.hwnd_to_widget.values()
                     if str(tab.property("tab_title")).startswith("YASB 页签列表验证")), key=lambda tab: tab.x())
    target = native[0]
    tabs.ensure_foreground(target.hwnd)
    QTest.qWait(100)
    group_left = min(tab.x() for tab in native)
    margins = tabs.width() - tabs.widget_layout.contentsRect().width()
    tabs.setFixedWidth(group_left + target.width() + 30 + tabs._tab_overflow.width() + margins)
    QTest.qWait(80)
    visible = sorted((tab for tab in native if not tab.isHidden()), key=lambda tab: tab.x())
    assert len(visible) == 3
    assert visible[-1] is target
    assert [tab.x() - visible[0].x() for tab in visible] == [0, 15, 30]
    assert len(set(native) & set(tabs._hidden_tabs)) == 4
    tabs._populate_tab_menu()
    assert not {tab.hwnd for tab in visible} & {action.data() for action in tabs._tab_menu.actions()}


def test_all_tabs_have_opaque_bar_background_and_grey_border(tabs: TaskbarWidget):
    tabs.setFixedWidth(4096)
    QTest.qWait(80)
    visible = [tab for tab in tabs.hwnd_to_widget.values() if not tab.isHidden()]
    assert visible
    tabs.ensure_foreground(visible[0].hwnd)
    QTest.qWait(80)
    for tab in visible:
        pixels = tab.grab().toImage()
        background = pixels.pixelColor(30, 7)
        assert background.getRgb() == (36, 36, 36, 255), background.getRgb()
        border = pixels.pixelColor(tab.width() // 2, 3)
        assert min(border.red(), border.green(), border.blue()) >= 150, border.getRgb()
        assert max(border.red(), border.green(), border.blue()) - min(border.red(), border.green(), border.blue()) < 30


def test_chrome_and_devtools_share_one_application_group(tabs: TaskbarWidget):
    chrome = [hwnd for hwnd, data in tabs.window_buttons.items() if data[3].casefold() == "chrome.exe"]
    if not any(GetWindowText(hwnd).startswith("DevTools") for hwnd in chrome):
        pytest.skip("此检查需要实际打开的独立 Chrome DevTools 窗口")
    normal = [hwnd for hwnd in chrome if not GetWindowText(hwnd).startswith("DevTools")]
    assert normal
    assert tabs.task_manager is not None
    identifiers = set()
    for hwnd in chrome:
        window = tabs.task_manager.get_window(hwnd)
        assert window is not None
        identifiers.add(PinManager.get_app_unique_id(hwnd, window.as_dict()))
    assert len(identifiers) >= 2
    assert len({tabs.hwnd_to_widget[hwnd].property("tab_app_id") for hwnd in chrome}) == 1
    tabs.setFixedWidth(4096)
    QTest.qWait(80)
    buttons = sorted((tabs.hwnd_to_widget[hwnd] for hwnd in chrome), key=lambda tab: tab.x())
    assert all(not tab.isHidden() for tab in buttons)
    assert [tab.x() - buttons[0].x() for tab in buttons] == [index * 15 for index in range(len(buttons))]
