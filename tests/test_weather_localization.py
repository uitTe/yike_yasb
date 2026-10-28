from pathlib import Path
from shutil import copyfile

import pytest
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QLabel, QPushButton

from core.i18n import set_language, tr
from core.utils.system import app_data_path
from core.validation.widgets.yasb.open_meteo import OpenMeteoCardConfig, OpenMeteoWidgetConfig
from core.widgets.services.open_meteo.widgets import ClickableWidget, HourlyDataLineWidget
from core.widgets.yasb.open_meteo import OpenMeteoWidget


@pytest.mark.parametrize("language", ["zh_CN", "en"])
def test_weather_popup_uses_selected_language_with_real_cache(qapp, language):
    source = Path("D:/tools/YASB_yike/data/weather.json")
    if not source.is_file():
        pytest.skip("需要本机真实天气缓存")
    copyfile(source, app_data_path("weather.json"))
    set_language(language)
    widget = OpenMeteoWidget(OpenMeteoWidgetConfig(
        update_interval=86400,
        weather_card=OpenMeteoCardConfig(show_hourly_forecast=True),
    ))
    widget.widget_name = "open_meteo"
    try:
        QTest.qWait(20)
        assert widget._has_valid_weather_data
        widget._popup_card()
        QTest.qWait(20)
        labels = [label.text() for label in widget.dialog.findChildren(QLabel)]
        details = next(text for text in labels if "hPa" in text)
        chinese = ("体感温度", "湿度", "气压", "云量", "紫外线指数")
        english = ("Feels like", "Humidity", "Pressure", "Cloud", "UV Index")
        expected, absent = (chinese, english) if language == "zh_CN" else (english, chinese)
        assert all(word in details for word in expected), details
        assert not any(word in details for word in absent), details
        assert widget._weather_data["{feelslike}"] in details
        assert widget._weather_data["{humidity}"] in details
        assert widget._weather_data["{pressure}"] in details
        assert tr("Today") in labels
        assert tr("Tomorrow") in labels
        assert tr("Location settings") in [button.text() for button in widget.dialog.findChildren(QPushButton)]
        assert tr("Now") == ("现在" if language == "zh_CN" else "Now")
        chart = widget.dialog.findChild(HourlyDataLineWidget)
        assert chart.current_idx == 1
        assert not chart.fg_pixmap.isNull()
        days = widget.dialog.findChildren(ClickableWidget)
        days[1].clicked.emit()
        QTest.qWait(10)
        assert chart.current_idx is None
        days[0].clicked.emit()
        QTest.qWait(10)
        assert chart.current_idx == 1
    finally:
        for fetcher in OpenMeteoWidget._shared_fetchers.values():
            fetcher.stop()
            fetcher.deleteLater()
        OpenMeteoWidget._shared_fetchers.clear()
        OpenMeteoWidget._shared_instances.clear()
        if hasattr(widget, "dialog"):
            widget.dialog.close()
        widget.close()
        widget.deleteLater()
        QTest.qWait(1)
        set_language("en")
