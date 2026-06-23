from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExtractResult:
    markdown: str
    title: str | None = None
    warnings: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
