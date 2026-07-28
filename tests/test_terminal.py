from __future__ import annotations

import io

from unifi_observer.presentation.terminal import TerminalUI


def test_terminal_ui_is_plain_and_testable_when_color_is_disabled():
    output = io.StringIO()
    errors = io.StringIO()
    terminal = TerminalUI(output, errors, color=False, unicode=False)

    terminal.banner("UniFi Observer", "Preparing")
    terminal.step("Connecting")
    terminal.success("Ready")
    terminal.warning("Retrying")
    terminal.error("Failed")

    assert "\\033[" not in output.getvalue()
    assert "> Connecting" in output.getvalue()
    assert "OK Ready" in output.getvalue()
    assert "! Retrying" in output.getvalue()
    assert "ERR Failed" in errors.getvalue()


def test_terminal_ui_supports_unicode_and_color_when_explicitly_enabled():
    output = io.StringIO()
    terminal = TerminalUI(output, output, color=True, unicode=True)

    terminal.success("Connected")

    rendered = output.getvalue()
    assert "✔" in rendered
    assert "\x1b[32m" in rendered


def test_terminal_ui_honors_no_color(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    output = io.StringIO()

    terminal = TerminalUI(output, output, color=None, unicode=False)
    terminal.info("Plain")

    assert "\\033[" not in output.getvalue()
