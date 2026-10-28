"""校验并保存天气弹窗中的位置设置。"""

from core.ui.config_document import ConfigDocument
from core.validation.widgets.yasb.open_meteo import OpenMeteoLocationConfig


def save_weather_location(document: ConfigDocument, widget_name: str, location: OpenMeteoLocationConfig) -> None:
    if document.value(("widgets", widget_name, "type")) != "yasb.open_meteo.OpenMeteoWidget":
        raise ValueError("当前组件的天气配置不存在。")
    document.assign(("widgets", widget_name, "options", "location"), location.model_dump())
    document.save()
