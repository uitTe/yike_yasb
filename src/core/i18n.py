from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, TypeAdapter
from yaml import safe_load

from core.locales.zh_cn import MESSAGES
from settings import DEFAULT_CONFIG_DIRECTORY, DEFAULT_CONFIG_FILENAME

if TYPE_CHECKING:
    from PyQt6.QtCore import QTranslator

Language = Literal["en", "zh_CN"]
_language: Language = "en"
_qt_translator: QTranslator | None = None


def get_language() -> Language:
    return _language


def set_language(language: Language) -> None:
    from PyQt6.QtCore import QLibraryInfo, QLocale, QTranslator
    from PyQt6.QtWidgets import QApplication

    global _language, _qt_translator
    _language = TypeAdapter(Language).validate_python(language)
    app = QApplication.instance()
    if app is not None:
        if _qt_translator is not None:
            app.removeTranslator(_qt_translator)
            _qt_translator = None
        if language == "zh_CN":
            translator = QTranslator(app)
            directory = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
            if not translator.load("qtbase_zh_CN", directory):
                raise RuntimeError("无法加载 Qt 简体中文语言文件")
            app.installTranslator(translator)
            _qt_translator = translator
    QLocale.setDefault(QLocale("zh_CN") if language == "zh_CN" else QLocale.system())


def initialize_language() -> None:
    config_path = Path(DEFAULT_CONFIG_DIRECTORY) / DEFAULT_CONFIG_FILENAME
    with config_path.open(encoding="utf-8") as stream:
        config = safe_load(stream)
    if not isinstance(config, dict):
        raise TypeError("YASB configuration must be a mapping")
    set_language(config.get("language", "en"))


def tr(message: str, *, language: Language | None = None, **values: object) -> str:
    text = MESSAGES[message] if (language or _language) == "zh_CN" else message
    return text.format(**values) if values else text


def tr_default(config: BaseModel, field: str) -> str:
    value = getattr(config, field)
    if field in config.model_fields_set:
        return value
    return tr(value)


def tr_configured(message: str) -> str:
    """翻译已知配置模板，保留其他自定义文字。"""
    return tr(message) if message in MESSAGES else message
