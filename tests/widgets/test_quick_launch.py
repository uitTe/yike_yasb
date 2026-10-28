import pytest
from pydantic import ValidationError

from core.validation.config import YasbConfig
from core.validation.widgets.yasb.quick_launch import QuickLaunchConfig
from core.widgets.services.quick_launch.providers.ip_info import IpInfoProvider
from core.widgets.services.quick_launch.service import PROVIDER_REGISTRY


def test_local_provider_configuration():
    providers = QuickLaunchConfig().providers.model_dump()
    assert providers.keys() == PROVIDER_REGISTRY.keys()
    assert providers["apps"]["enabled"]
    assert "show_online" not in providers["wsl"]
    assert not {"binance", "currency", "github_notifications", "hacker_news", "web_search"}.intersection(providers)


def test_old_root_options_are_rejected():
    with pytest.raises(ValidationError, match="extra_forbidden"):
        YasbConfig.model_validate({"update_check": True})


@pytest.mark.parametrize("name", ["binance", "currency", "github_notifications", "hacker_news", "web_search"])
def test_old_online_providers_are_rejected(name):
    with pytest.raises(ValidationError, match="extra_forbidden"):
        QuickLaunchConfig.model_validate({"providers": {name: {"enabled": True}}})


def test_old_wsl_options_are_rejected():
    with pytest.raises(ValidationError, match="extra_forbidden"):
        QuickLaunchConfig.model_validate({"providers": {"wsl": {"show_online": True}}})


def test_ip_tools_calculate_local_subnet(qapp):
    provider = IpInfoProvider({"prefix": "ip"})
    results = provider.get_results("ip calc 192.168.1.0/24")
    values = [str(result.action_data.get("copy", "")) for result in results]
    assert "192.168.1.0" in values
    assert "192.168.1.255" in values
    assert "255.255.255.0" in values
    assert "254" in values


def test_ip_tools_analyze_address(qapp):
    provider = IpInfoProvider({"prefix": "ip"})
    results = provider.get_results("ip check 192.168.1.1")
    values = [str(result.action_data.get("copy", "")) for result in results]
    assert "192.168.1.1" in values
    assert "Private" in values
    assert "11000000.10101000.00000001.00000001" in values
