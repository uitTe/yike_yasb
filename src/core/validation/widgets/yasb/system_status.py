from pydantic import Field

from core.validation.widgets.yasb.control_center import ControlCenterConfig


class SystemStatusConfig(ControlCenterConfig):
    label: str = ""
    label_alt: str = ""
    update_interval: int = Field(default=3000, ge=1000, le=60000)
