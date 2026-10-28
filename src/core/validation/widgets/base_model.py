from typing import Literal

from pydantic import BaseModel, ConfigDict


class CustomBaseModel(BaseModel):
    # 未声明的配置字段直接触发校验错误。
    model_config = ConfigDict(extra="forbid", validate_default=True)


class CallbacksConfig(CustomBaseModel):
    on_left: str = "do_nothing"
    on_middle: str = "do_nothing"
    on_right: str = "do_nothing"


class KeybindingConfig(CustomBaseModel):
    keys: str
    action: str
    screen: Literal["active", "cursor", "primary"] = "active"
