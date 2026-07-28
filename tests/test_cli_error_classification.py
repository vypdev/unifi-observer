import pytest

from unifi_observer.cli import CliError, _configure
from unifi_observer.domain.errors import UniFiError
from unifi_observer.infrastructure.config import Settings


def _local_settings() -> Settings:
    return Settings(
        api_mode="local",
        api_base_url="https://unifi.local",
        api_key=None,
        site_id=None,
        allowed_site_ids=(),
        verify_tls=True,
        timeout_seconds=15,
        enable_write=False,
    )


def test_discover_sites_reports_header_presence_without_secret(monkeypatch, capsys):
    from unifi_observer.cli import _discover_sites

    class FakeClient:
        def __init__(self, settings):
            assert settings.api_key == "secret-value"

        async def list_sites(self):
            return {"data": []}

        async def aclose(self):
            pass

    monkeypatch.setattr("unifi_observer.cli.UniFiClient", FakeClient)
    _discover_sites(_local_settings_with_key())
    output = capsys.readouterr().out
    assert "official_api_request: X-API-Key present" in output
    assert "secret-value" not in output


def _local_settings_with_key() -> Settings:
    return Settings(
        api_mode="local",
        api_base_url="https://unifi.local",
        api_key="secret-value",
        site_id=None,
        allowed_site_ids=(),
        verify_tls=True,
        timeout_seconds=15,
        enable_write=False,
    )


def test_configure_reports_api_key_failure_separately_from_tls(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("unifi_observer.cli._prompt_settings", _local_settings)
    monkeypatch.setattr("unifi_observer.cli._prepare_local_tls", lambda settings, _: settings)
    monkeypatch.setattr(
        "unifi_observer.cli._discover_sites",
        lambda _: (_ for _ in ()).throw(UniFiError("UniFi upstream returned HTTP 401", 401)),
    )

    with pytest.raises(CliError, match="API key.*HTTP 401"):
        _configure(tmp_path / "config.env")
    assert "official_api_response: HTTP 401" in capsys.readouterr().out
