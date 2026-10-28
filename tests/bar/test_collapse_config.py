from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from core.validation.bar import BarConfig


def test_collapse_default_and_heights():
    assert not BarConfig().collapse.enabled
    bar = BarConfig(dimensions={"height": 48}, collapse={"enabled": True})
    assert bar.collapse.start_collapsed
    assert bar.collapse.collapsed_height == 34
    with pytest.raises(ValidationError, match="收起高度"):
        BarConfig(dimensions={"height": 30}, collapse={"enabled": True})


def test_default_top_bar_starts_collapsed_and_dock_is_unchanged():
    path = Path(__file__).resolve().parents[2] / "src/defaults/config.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    top = BarConfig.model_validate(config["bars"]["primary-bar"])
    dock = BarConfig.model_validate(config["bars"]["macos-dock"])
    assert top.collapse.enabled and top.collapse.start_collapsed
    assert top.collapse.collapsed_height == 34 and top.dimensions.height == 48
    assert not dock.collapse.enabled and dock.dimensions.height == 64
