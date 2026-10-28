from pydantic import Field

from core.validation.widgets.base_model import CallbacksConfig, CustomBaseModel, KeybindingConfig
from core.validation.widgets.yasb.cpu import CpuMenuConfig


class SystemMonitorCallbacksConfig(CallbacksConfig):
    on_left: str = "toggle_menu"


class SystemMonitorMenuConfig(CpuMenuConfig):
    enabled: bool = True


class SystemMonitorConfig(CustomBaseModel):
    class_name: str = ""
    update_interval: int = Field(default=2000, ge=1000, le=60000)
    menu: SystemMonitorMenuConfig = SystemMonitorMenuConfig()
    callbacks: SystemMonitorCallbacksConfig = SystemMonitorCallbacksConfig()
    keybindings: list[KeybindingConfig] = []
