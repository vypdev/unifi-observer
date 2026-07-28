import stat

import pytest

from unifi_mcp.cli import build_parser, load_env_file, write_env_file


def test_parser_exposes_observer_commands():
    parser = build_parser()
    for command in (
        "get-site",
        "generate-certificate",
        "configure",
        "start",
        "stop",
        "restart",
        "status",
        "uninstall",
    ):
        args = parser.parse_args([command])
        assert args.command == command


def test_write_and_load_env_file_protects_api_key(tmp_path):
    path = tmp_path / "config.env"
    values = {
        "UNIFI_API_MODE": "local",
        "UNIFI_API_BASE_URL": "https://unifi.local",
        "UNIFI_API_KEY": "secret-'key\\\\with\"punctuation",
        "UNIFI_SITE_ID": "site-123",
    }

    write_env_file(path, values)

    assert load_env_file(path) == values
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert "UNIFI_API_KEY=" in path.read_text()


def test_write_env_file_refuses_parent_that_is_not_private(tmp_path):
    path = tmp_path / "config.env"
    path.parent.chmod(0o755)

    with pytest.raises(PermissionError, match="private"):
        write_env_file(path, {"UNIFI_API_KEY": "secret"})
