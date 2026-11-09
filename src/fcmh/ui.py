"""Tiny I/O seam so the wizard and restore can be driven by tests or the GUI."""

from __future__ import annotations

import webbrowser
from typing import Callable


class UI:
    def __init__(
        self,
        out: Callable[[str], None] = print,
        ask: Callable[[str], str] = input,
        open_url: Callable[[str], object] = webbrowser.open,
        assume_yes: bool = False,
    ) -> None:
        self.out = out
        self._ask = ask
        self.open_url = open_url
        self.assume_yes = assume_yes

    def ask(self, prompt: str) -> str:
        try:
            return self._ask(prompt)
        except EOFError:
            return ""

    def confirm(self, prompt: str) -> bool:
        if self.assume_yes:
            self.out(f"{prompt} [y/N] y (--yes)")
            return True
        answer = self.ask(f"{prompt} [y/N] ").strip().lower()
        return answer in ("y", "yes")
