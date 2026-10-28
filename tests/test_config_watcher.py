from pathlib import Path
from shutil import copyfile
from time import monotonic

import pytest
from PyQt6.QtCore import QIODevice, QSaveFile
from PyQt6.QtTest import QSignalSpy
from watchdog.observers import Observer

from core.bar_manager import BarManager
from core.ui.config_document import ConfigDocument
from core.validation.config import YasbConfig
from core.watcher import FileModifiedEventHandler


@pytest.fixture
def watched_config(qapp, tmp_path):
    path = tmp_path / "config.yaml"
    copyfile(Path(__file__).parents[1] / "src/defaults/config.yaml", path)
    manager = BarManager(YasbConfig(), "")
    # 本组检查文件事件和 Qt 通知，真实状态栏的重启由运行实例单独验证。
    manager.config_modified.disconnect(manager.on_config_modified)
    manager.styles_modified.disconnect(manager.on_styles_modified)
    handler = FileModifiedEventHandler(manager)
    observer = Observer()
    observer.schedule(handler, str(tmp_path), recursive=False)
    observer.start()
    try:
        yield path, manager, handler
    finally:
        observer.stop()
        observer.join(timeout=5)
        manager._disconnect_reload_signals()
        manager.deleteLater()
        qapp.processEvents()


def wait_for_signal(qapp, spy, count):
    deadline = monotonic() + 4
    while len(spy) < count and monotonic() < deadline:
        spy.wait(100)
        qapp.processEvents()
    assert len(spy) == count


def test_settings_atomic_save_reloads_on_each_replacement(qapp, watched_config):
    path, manager, _handler = watched_config
    spy = QSignalSpy(manager.config_modified)
    document = ConfigDocument(path)
    document.assign(("debug",), not document.data.get("debug", False))
    document.save()
    wait_for_signal(qapp, spy, 1)
    document.assign(("debug",), not document.data["debug"])
    document.save()
    wait_for_signal(qapp, spy, 2)


def test_plain_file_write_still_notifies(qapp, watched_config):
    path, manager, _handler = watched_config
    spy = QSignalSpy(manager.config_modified)
    path.write_bytes(path.read_bytes() + b"\n# changed configuration\n")
    wait_for_signal(qapp, spy, 1)


def test_atomic_save_respects_disabled_watching(qapp, watched_config):
    path, manager, _handler = watched_config
    manager.config.watch_config = False
    spy = QSignalSpy(manager.config_modified)
    document = ConfigDocument(path)
    document.assign(("debug",), not document.data.get("debug", False))
    document.save()
    assert not spy.wait(500)
    assert len(spy) == 0


def test_same_contents_atomic_replacement_does_not_notify(qapp, watched_config):
    path, manager, _handler = watched_config
    spy = QSignalSpy(manager.config_modified)
    target = QSaveFile(str(path))
    contents = path.read_bytes()
    assert target.open(QIODevice.OpenModeFlag.WriteOnly)
    assert target.write(contents) == len(contents)
    assert target.commit()
    assert not spy.wait(500)
    assert len(spy) == 0


def test_created_config_file_notifies(qapp, watched_config):
    path, manager, _handler = watched_config
    spy = QSignalSpy(manager.config_modified)
    contents = path.read_bytes() + b"\n# recreated configuration\n"
    path.unlink()
    path.write_bytes(contents)
    wait_for_signal(qapp, spy, 1)


def test_atomic_stylesheet_save_notifies(qapp, watched_config):
    path, manager, _handler = watched_config
    spy = QSignalSpy(manager.styles_modified)
    stylesheet = path.parent / "styles.css"
    target = QSaveFile(str(stylesheet))
    contents = b".yasb-bar { color: white; }\n"
    assert target.open(QIODevice.OpenModeFlag.WriteOnly)
    assert target.write(contents) == len(contents)
    assert target.commit()
    wait_for_signal(qapp, spy, 1)
