"""保存 Codex 弹窗中的程序路径。"""

from core.ui.config_document import ConfigDocument
from core.widgets.services.codex_usage.codex_api import find_codex_command


def save_codex_path(document: ConfigDocument, widget_name: str, executable: str) -> str:
    executable = executable.strip()
    if not executable or not find_codex_command(executable):
        raise ValueError("找不到 Codex 程序，请选择有效的程序路径。")
    if document.value(("widgets", widget_name, "type")) != "yasb.codex_usage.CodexUsageWidget":
        raise ValueError("当前组件的 Codex 配置不存在。")
    document.assign(("widgets", widget_name, "options", "codex_path"), executable)
    document.save()
    return executable
