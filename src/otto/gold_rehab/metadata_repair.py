from __future__ import annotations

from pathlib import Path

from ..corridor import merge_frontmatter


def append_only_otto_fields(frontmatter: dict[str, object], additions: dict[str, object]) -> dict[str, object]:
    return merge_frontmatter(frontmatter, additions)
