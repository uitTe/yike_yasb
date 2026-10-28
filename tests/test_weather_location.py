from copy import deepcopy
from pathlib import Path
from shutil import copyfile

import pytest
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QFrame

from core.ui.config_document import ConfigChangedError, ConfigDocument
from core.validation.widgets.yasb.open_meteo import OpenMeteoLocationConfig
from core.widgets.services.open_meteo.config import save_weather_location
from core.widgets.services.open_meteo.location import load_weather_cache, save_location, save_weather_cache
from core.widgets.services.open_meteo.location_editor import LocationEditor


@pytest.fixture
def weather_document(tmp_path, qapp):
    path = tmp_path / "config.yaml"
    copyfile(Path(__file__).parents[1] / "src/defaults/config.yaml", path)
    return ConfigDocument(path)


@pytest.mark.parametrize("latitude,longitude", [(-90, -180), (90, 180), (0, 0), (30.59849, 114.376844)])
def test_coordinates_accept_boundaries(latitude, longitude):
    assert OpenMeteoLocationConfig(latitude=latitude, longitude=longitude).latitude == latitude


@pytest.mark.parametrize("latitude,longitude", [(90.1, 0), (-90.1, 0), (0, 180.1), (0, -180.1),
                                              (float("nan"), 0), (0, float("inf"))])
def test_invalid_coordinates_are_rejected(latitude, longitude):
    with pytest.raises(ValueError):
        OpenMeteoLocationConfig(latitude=latitude, longitude=longitude)


def test_save_preserves_other_configuration(weather_document):
    before = deepcopy(weather_document.data)
    location = OpenMeteoLocationConfig(name="武汉", latitude=30.59849, longitude=114.376844)
    save_weather_location(weather_document, "open_meteo", location)
    before["widgets"]["open_meteo"]["options"]["location"] = location.model_dump()
    assert ConfigDocument(weather_document.path).data == before


def test_save_rejects_external_changes(weather_document):
    other = ConfigDocument(weather_document.path)
    other.assign(("debug",), True)
    other.save()
    external = weather_document.path.read_bytes()
    with pytest.raises(ConfigChangedError):
        save_weather_location(weather_document, "open_meteo", OpenMeteoLocationConfig(latitude=0, longitude=0))
    assert weather_document.path.read_bytes() == external


def test_editor_validates_and_saves_coordinates(weather_document, qapp):
    parent = QFrame()
    editor = LocationEditor(weather_document, "open_meteo", None, parent)
    editor.tabs.setCurrentIndex(1)
    for latitude, longitude in (("", ""), ("91", "114"), ("30", "181"), ("NaN", "114"), ("30", "Infinity")):
        editor.latitude.setText(latitude)
        editor.longitude.setText(longitude)
        assert not editor.save.isEnabled()
    editor.latitude.setText("30.598490")
    editor.longitude.setText("114.376844")
    assert editor.save.isEnabled()
    editor.save.click()
    saved = ConfigDocument(weather_document.path).value(("widgets", "open_meteo", "options", "location"))
    assert saved == {"name": "30.598490, 114.376844", "latitude": 30.59849, "longitude": 114.376844}
    parent.deleteLater()
    QTest.qWait(1)


def test_editor_cancel_preserves_configuration(weather_document, qapp):
    parent = QFrame()
    before = weather_document.path.read_bytes()
    editor = LocationEditor(weather_document, "open_meteo", None, parent)
    editor.tabs.setCurrentIndex(1)
    editor.latitude.setText("30.59849")
    editor.longitude.setText("114.376844")
    editor.cancelled.emit()
    assert weather_document.path.read_bytes() == before
    parent.deleteLater()
    QTest.qWait(1)


def test_same_latitude_different_longitude_invalidates_real_cache():
    source = Path("D:/tools/YASB_yike/data/weather.json")
    if not source.exists():
        pytest.skip("需要本机真实天气缓存")
    import json

    cached = json.loads(source.read_text(encoding="utf-8"))["open_meteo"]
    if not cached.get("cached_data"):
        pytest.skip("需要成功获取的真实天气预报")
    widget_id = "test_weather_longitude"
    save_location(widget_id, cached)
    save_weather_cache(widget_id, cached["cached_data"])
    assert load_weather_cache(widget_id)[0] == cached["cached_data"]
    save_location(widget_id, {**cached, "longitude": cached["longitude"] + 0.01})
    assert load_weather_cache(widget_id) == (None, 0)
