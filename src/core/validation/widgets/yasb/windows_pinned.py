from pydantic import Field

from core.validation.widgets.base_model import CustomBaseModel


class WindowsPinnedConfig(CustomBaseModel):
    icon_size: int = Field(default=32, ge=8, le=64)
    tooltip: bool = True
