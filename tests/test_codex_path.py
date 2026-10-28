from copy import deepcopy
from pathlib import Path
from shutil import copyfile, which

import pytest

from core.ui.config_document import ConfigChangedError, ConfigDocument
from core.widgets.services.codex_usage.codex_api import find_codex_command
from core.widgets.services.codex_usage.config import save_codex_path


@pytest.fixture
def codex_command():
    command = which("codex")
    if command is None:
        pytest.skip("需要安装真实 Codex CLI")
    return command


@pytest.fixture
def codex_document(tmp_path, qapp):
    path = tmp_path / "config.yaml"
    copyfile(Path(__file__).parents[1] / "src/defaults/config.yaml", path)
    document = ConfigDocument(path)
    document.add("widgets", "work_codex", "yasb.codex_usage.CodexUsageWidget")
    document.assign(("widgets", "work_codex", "options"), {"codex_path": "codex", "cache_ttl": 240})
    document.save()
    return document


def test_path_save_preserves_other_settings_and_yaml(codex_document, codex_command):
    before = deepcopy(codex_document.data)
    comments = [line for line in codex_document.path.read_text(encoding="utf-8").splitlines()
                if line.lstrip().startswith("#")]
    result = save_codex_path(codex_document, "work_codex", f"  {codex_command}  ")
    assert result == codex_command
    expected = deepcopy(before)
    expected["widgets"]["work_codex"]["options"]["codex_path"] = codex_command
    assert ConfigDocument(codex_document.path).data == expected
    assert all(comment in codex_document.path.read_text(encoding="utf-8") for comment in comments)
    saved = codex_document.path.read_bytes()
    save_codex_path(codex_document, "work_codex", codex_command)
    assert codex_document.path.read_bytes() == saved


def test_invalid_path_does_not_write_configuration(codex_document, tmp_path):
    before = codex_document.path.read_bytes()
    for path in ("", str(tmp_path), str(tmp_path / "missing-codex.exe")):
        with pytest.raises(ValueError, match="找不到 Codex"):
            save_codex_path(codex_document, "work_codex", path)
        assert codex_document.path.read_bytes() == before


def test_changed_configuration_is_preserved(codex_document, codex_command):
    other_editor = ConfigDocument(codex_document.path)
    other_editor.assign(("debug",), not other_editor.value(("debug",), False))
    other_editor.save()
    external = codex_document.path.read_bytes()
    with pytest.raises(ConfigChangedError):
        save_codex_path(codex_document, "work_codex", codex_command)
    assert codex_document.path.read_bytes() == external


def test_path_save_requires_codex_widget(codex_document, codex_command):
    before = codex_document.path.read_bytes()
    with pytest.raises(ValueError, match="Codex 配置不存在"):
        save_codex_path(codex_document, "missing_widget", codex_command)
    assert codex_document.path.read_bytes() == before


def test_resolver_supports_real_codex_command_and_path(codex_command):
    assert Path(find_codex_command("codex")).samefile(codex_command)
    assert Path(find_codex_command(codex_command)).samefile(codex_command)
