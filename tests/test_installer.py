import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_installer_scripts_are_valid_bash():
    result = subprocess.run(
        ["bash", "-n", str(ROOT / "install.sh"), str(ROOT / "scripts/setup.sh")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_installer_defaults_to_https_and_starts_configuration():
    installer = (ROOT / "install.sh").read_text(encoding="utf-8")
    setup = (ROOT / "scripts/setup.sh").read_text(encoding="utf-8")

    assert "https://github.com/vypdev/unifi-observer.git" in installer
    assert '[[ "$REPOSITORY_URL" == https://* ]]' in installer
    assert 'exec "$cli_target" configure' in setup
    assert "UNIFI_API_KEY" not in installer
    assert "UNIFI_API_KEY" not in setup


def test_installer_help_does_not_clone_or_modify_the_host():
    result = subprocess.run(
        ["bash", str(ROOT / "install.sh"), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "UNIFI_OBSERVER_SKIP_CONFIGURE" in result.stdout
