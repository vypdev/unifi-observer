"""Small, dependency-free terminal presentation helpers for the native CLI."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import TextIO

_RESET = "\033[0m"
_BOLD = "\033[1m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_DIM = "\033[2m"


@dataclass(frozen=True)
class TerminalUI:
    """Render consistent terminal messages with safe TTY degradation.

    Color is enabled only for an interactive stream unless ``FORCE_COLOR`` is set.
    ``NO_COLOR`` always wins. Messages remain plain text when redirected, which keeps
    logs suitable for CI and systemd without ANSI escape sequences.
    """

    stream: TextIO = field(default_factory=lambda: sys.stdout)
    error_stream: TextIO = field(default_factory=lambda: sys.stderr)
    color: bool | None = None
    unicode: bool | None = None

    def __post_init__(self) -> None:
        if self.color is None:
            object.__setattr__(self, "color", self._color_enabled())
        if self.unicode is None:
            object.__setattr__(self, "unicode", self._unicode_enabled())

    def _color_enabled(self) -> bool:
        if os.environ.get("NO_COLOR") is not None:
            return False
        if os.environ.get("FORCE_COLOR") is not None:
            return True
        return bool(self.stream.isatty())

    def _unicode_enabled(self) -> bool:
        if os.environ.get("UNIFI_OBSERVER_ASCII") == "1":
            return False
        encoding = getattr(self.stream, "encoding", None) or "utf-8"
        return encoding.lower().replace("-", "") == "utf8"

    def _paint(self, text: str, code: str) -> str:
        return f"{code}{text}{_RESET}" if self.color else text

    def _symbol(self, unicode_symbol: str, ascii_symbol: str) -> str:
        return unicode_symbol if self.unicode else ascii_symbol

    def banner(self, title: str, subtitle: str | None = None) -> None:
        line = "═" * max(48, min(76, len(title) + 12)) if self.unicode else "=" * max(48, min(76, len(title) + 12))
        self.stream.write(f"\n{self._paint(line, _CYAN)}\n")
        symbol = self._paint(self._symbol("◈", "*"), _CYAN)
        title_text = self._paint(title, _BOLD + _CYAN)
        self.stream.write(f"  {symbol} {title_text}\n")
        if subtitle:
            self.stream.write(f"  {self._paint(subtitle, _DIM)}\n")
        self.stream.write(f"{self._paint(line, _CYAN)}\n")
        self.stream.flush()

    def step(self, message: str) -> None:
        self._write(self._symbol("◆", ">"), message, _CYAN)

    def info(self, message: str) -> None:
        self._write(self._symbol("ℹ", "i"), message, _CYAN)

    def success(self, message: str) -> None:
        self._write(self._symbol("✔", "OK"), message, _GREEN)

    def warning(self, message: str) -> None:
        self._write(self._symbol("⚠", "!"), message, _YELLOW)

    def error(self, message: str) -> None:
        self._write(self._symbol("✖", "ERR"), message, _RED, self.error_stream)

    def _write(self, symbol: str, message: str, color: str, stream: TextIO | None = None) -> None:
        output = stream or self.stream
        output.write(f"  {self._paint(symbol, color)} {message}\n")
        output.flush()


