from __future__ import annotations

try:
    from .tui import run_tui
except ModuleNotFoundError as exc:  # pragma: no cover - dependency guard
    def run_tui(*args, **kwargs):  # type: ignore[no-redef]
        raise RuntimeError("TUI dependencies are missing (install 'rich' to use run_tui).") from exc
