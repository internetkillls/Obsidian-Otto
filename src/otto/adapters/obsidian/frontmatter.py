from __future__ import annotations

from typing import Any


def _render_value(value: Any, indent: int = 0) -> list[str]:
    prefix = " " * indent
    if isinstance(value, list):
        if not value:
            return [f"{prefix}[]"]
        lines: list[str] = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}-")
                lines.extend(_render_value(item, indent + 2))
            else:
                lines.append(f"{prefix}- {item}")
        return lines
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.extend(_render_value(item, indent + 2))
            else:
                lines.append(f"{prefix}{key}: {item}")
        return lines
    return [f"{prefix}{value}"]


def render_frontmatter(fields: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in fields.items():
        if isinstance(value, (list, dict)):
            lines.append(f"{key}:")
            lines.extend(_render_value(value, 2))
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines) + "\n"
