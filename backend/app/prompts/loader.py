"""Versioned prompt templates. The content hash is the version recorded on every provider call."""

import hashlib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent / "templates"


@dataclass(frozen=True)
class Template:
    name: str
    version: str
    text: str
    sha256: str


@cache
def template(name: str) -> Template:
    text = (TEMPLATE_DIR / f"{name}.md").read_text(encoding="utf-8")
    digest = hashlib.sha256(text.encode()).hexdigest()
    return Template(name=name, version=digest[:12], text=text, sha256=digest)
