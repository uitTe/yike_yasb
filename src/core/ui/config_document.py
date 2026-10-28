"""配置页面的数据、严格校验与 YAML 保存。"""

from copy import deepcopy
from functools import cache
from importlib import import_module
from importlib.resources import files
from io import StringIO
from pathlib import Path
from pkgutil import iter_modules
from typing import Any

from pydantic import BaseModel
from PyQt6.QtCore import QIODevice, QSaveFile
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from core.config import get_config_path, parse_env
from core.validation.bar import BarConfig
from core.validation.config import YasbConfig
from core.widgets.registry import WIDGET_REGISTRY
from settings import IS_FROZEN

type ConfigPath = tuple[str | int, ...]


@cache
def widget_models() -> dict[str, type[BaseModel]]:
    for group in ("yasb", "komorebi", "glazewm"):
        package = import_module(f"core.widgets.{group}")
        for module in iter_modules(package.__path__, f"{package.__name__}."):
            if not module.ispkg:
                import_module(module.name)
    return {name: widget.validation_schema for name, widget in sorted(WIDGET_REGISTRY.items())}


class ConfigChangedError(ValueError):
    pass


def validate_config(data: dict[str, Any]) -> None:
    expanded = parse_env(deepcopy(data))
    config = YasbConfig.model_validate(expanded)
    if not config.bars:
        raise ValueError("至少需要一个状态栏。")
    models = widget_models()
    for name, entry in expanded.get("widgets", {}).items():
        if not isinstance(entry, dict) or set(entry) - {"type", "options"}:
            raise ValueError(f"组件 {name} 需要 type 和 options 配置。")
        widget_type = entry.get("type")
        if widget_type not in models:
            raise ValueError(f"组件 {name} 的类型无效：{widget_type}")
        try:
            models[widget_type].model_validate(entry.get("options", {}))
        except ValueError as error:
            raise ValueError(f"组件 {name}：\n{error}") from error
    references = []
    for name, bar in config.bars.items():
        for side in ("left", "center", "right"):
            references.append((f"{name}.{side}", getattr(bar.widgets, side)))
    groups = {}
    for name, entry in expanded.get("widgets", {}).items():
        if entry["type"] == "yasb.grouper.GrouperWidget":
            groups[name] = entry.get("options", {}).get("widgets", [])
            references.append((name, groups[name]))
    for name, names in references:
        missing = set(names) - set(config.widgets)
        if missing:
            raise ValueError(f"{name} 引用了不存在的组件：{', '.join(sorted(missing))}")

    def visit(name: str, parents: set[str]) -> None:
        if name in parents:
            raise ValueError(f"组件分组存在循环引用：{name}")
        for child in groups.get(name, []):
            visit(child, parents | {name})

    for name in groups:
        visit(name, set())


class ConfigDocument:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else Path(get_config_path())
        self.yaml = YAML(typ="rt", pure=True)
        self.yaml.preserve_quotes = True
        self.yaml.width = 4096
        self.yaml.indent(mapping=2, sequence=4, offset=2)
        self.reload()

    def reload(self) -> None:
        original_bytes = self.path.read_bytes()
        data = self.yaml.load(original_bytes.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("配置文件必须包含 YAML 对象。")
        validate_config(data)
        self.original_bytes = original_bytes
        self.yaml.line_break = "\r\n" if b"\r\n" in original_bytes else "\n"
        self.data = data
        self.original = deepcopy(data)

    @property
    def dirty(self) -> bool:
        return self.data != self.original

    def value(self, path: ConfigPath, default: Any = None) -> Any:
        current = self.data
        for key in path:
            if isinstance(current, dict) and key not in current:
                return deepcopy(default)
            current = current[key]
        return current

    def assign(self, path: ConfigPath, value: Any) -> None:
        if not path:
            raise ValueError("不能替换配置根对象。")
        target = self.data
        for key in path[:-1]:
            if isinstance(target, dict) and key not in target:
                target[key] = CommentedMap()
            target = target[key]
        target[path[-1]] = deepcopy(value)

    def restore_defaults(self) -> None:
        """将独立默认模板载入编辑内容，保存前保持配置文件不变。"""
        template = (files("core").joinpath("default_config.yaml") if IS_FROZEN
                    else Path(__file__).resolve().parents[2] / "defaults" / "config.yaml")
        data = self.yaml.load(template.read_text(encoding="utf-8"))
        validate_config(data)
        self.data = data

    def exists(self, path: ConfigPath) -> bool:
        current = self.data
        for key in path:
            if isinstance(current, dict) and key not in current:
                return False
            if isinstance(current, list) and (not isinstance(key, int) or key >= len(current)):
                return False
            current = current[key]
        return True

    def schema(self, path: ConfigPath) -> dict[str, Any]:
        if not path:
            schema = YasbConfig.model_json_schema()
            schema["properties"] = {k: v for k, v in schema["properties"].items() if k not in ("bars", "widgets")}
            return schema
        if path[0] == "bars":
            return BarConfig.model_json_schema()
        return widget_models()[self.value(path)["type"]].model_json_schema()

    def add(self, category: str, name: str, widget_type: str | None = None) -> ConfigPath:
        name = name.strip()
        if not name or name in self.data.get(category, {}):
            raise ValueError("名称不能为空，也不能与已有名称重复。")
        if category == "bars":
            value = BarConfig().model_dump(mode="json")
        else:
            if widget_type not in widget_models():
                raise ValueError("请选择组件类型。")
            value = {"type": widget_type, "options": {}}
        self.assign((category, name), value)
        return (category, name)

    def _references(self):
        for bar in self.data.get("bars", {}).values():
            for side in ("left", "center", "right"):
                if side in bar.get("widgets", {}):
                    yield bar["widgets"][side]
        for widget in self.data.get("widgets", {}).values():
            if widget["type"] == "yasb.grouper.GrouperWidget":
                options = widget.get("options", {})
                if "widgets" in options:
                    yield options["widgets"]
                if "exclude_widgets" in options.get("collapse_options", {}):
                    yield options["collapse_options"]["exclude_widgets"]

    def rename(self, path: ConfigPath, name: str) -> ConfigPath:
        name = name.strip()
        mapping = self.data[path[0]]
        old = path[1]
        if not name or (name != old and name in mapping):
            raise ValueError("名称不能为空，也不能与已有名称重复。")
        if name == old:
            return path
        index = list(mapping).index(old)
        value = mapping.pop(old)
        if isinstance(mapping, CommentedMap):
            mapping.insert(index, name, value)
            if old in mapping.ca.items:
                mapping.ca.items[name] = mapping.ca.items.pop(old)
        else:
            mapping[name] = value
        if path[0] == "widgets":
            for items in self._references():
                for index, item in enumerate(items):
                    if item == old:
                        items[index] = name
        return (path[0], name)

    def remove(self, path: ConfigPath) -> None:
        if path[0] == "bars" and len(self.data["bars"]) == 1:
            raise ValueError("至少需要保留一个状态栏。")
        if path[0] == "widgets":
            for items in self._references():
                items[:] = [item for item in items if item != path[1]]
        del self.data[path[0]][path[1]]

    def save(self) -> None:
        validate_config(self.data)
        if self.path.read_bytes() != self.original_bytes:
            raise ConfigChangedError("配置文件已被其他程序修改，请重新读取后再编辑。")
        if not self.dirty:
            return
        stream = StringIO()
        self.yaml.dump(self.data, stream)
        encoded = stream.getvalue().encode("utf-8")
        target = QSaveFile(str(self.path))
        if not target.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError(target.errorString())
        if target.write(encoded) != len(encoded) or not target.commit():
            raise OSError(target.errorString())
        self.original_bytes = encoded
        self.original = deepcopy(self.data)
