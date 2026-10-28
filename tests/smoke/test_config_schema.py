import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import BaseModel
from yaml import safe_load

from core.config import get_config_and_stylesheet, get_config_dir, get_config_path, get_stylesheet_path
from core.validation.config import YasbConfig
from core.widgets.registry import WIDGET_REGISTRY
from tests.support.source import import_core_modules


def _registered_widgets():
    import_core_modules()
    return [pytest.param(widget, id=name) for name, widget in sorted(WIDGET_REGISTRY.items())]


@pytest.mark.parametrize("widget", _registered_widgets())
def test_widget_has_a_config_schema(widget: type):
    schema = getattr(widget, "validation_schema", None)
    assert isinstance(schema, type) and issubclass(schema, BaseModel), (
        f"{widget.__qualname__}.validation_schema is not a pydantic model"
    )
    schema.model_json_schema()


def test_yasb_config_schema_builds():
    YasbConfig.model_json_schema()


SOURCE_DIRECTORY = Path(__file__).resolve().parents[2] / "src"


def test_program_config_directory_is_fixed(tmp_path: Path) -> None:
    alternate = tmp_path / "config"
    result = subprocess.run(
        [sys.executable, str(SOURCE_DIRECTORY / "cli.py"), "--config"],
        env={
            **os.environ,
            "YASB_CONFIG_HOME": str(alternate),
            "PYTHONPATH": str(SOURCE_DIRECTORY),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    assert Path(result.stdout.strip()) == SOURCE_DIRECTORY / "defaults"
    assert not alternate.exists()


def test_program_config_and_stylesheet_load():
    directory = SOURCE_DIRECTORY / "defaults"
    assert Path(get_config_dir()) == directory
    assert Path(get_config_path()) == directory / "config.yaml"
    assert Path(get_stylesheet_path()) == directory / "styles.css"
    raw = safe_load((directory / "config.yaml").read_text(encoding="utf-8"))
    config, stylesheet = get_config_and_stylesheet()
    assert config.model_dump() == YasbConfig.model_validate(raw).model_dump()
    assert stylesheet.strip()
    for entry in raw["widgets"].values():
        if isinstance(entry, dict):
            WIDGET_REGISTRY[entry["type"]].validation_schema.model_validate(entry.get("options", {}))
