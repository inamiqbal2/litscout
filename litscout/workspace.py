"""A workspace is one folder per research question."""
from __future__ import annotations

import json
from pathlib import Path


class Workspace:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()

    # folders
    @property
    def pdfs(self): return self._dir("pdfs")
    @property
    def text(self): return self._dir("text")
    @property
    def cards(self): return self._dir("cards")

    def _dir(self, name):
        p = self.root / name
        p.mkdir(parents=True, exist_ok=True)
        return p

    # json helpers
    def path(self, name): return self.root / name

    def load(self, name, default=None):
        p = self.root / name
        if not p.exists():
            return default
        return json.loads(p.read_text())

    def save(self, name, data):
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / name).write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def write(self, name, text):
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / name).write_text(text)

    @property
    def project(self) -> dict:
        p = self.load("project.json")
        if p is None:
            raise SystemExit(f"No project.json in {self.root}. Run `litscout init` first.")
        return p
