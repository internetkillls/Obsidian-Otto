from __future__ import annotations

import json
import time
from pathlib import Path

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .status import build_status
from ..config import load_paths


def _shorten(text: str, limit: int = 140) -> str:
    text = str(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _table_from_top_folders(top_folders: list[dict]) -> Table:
    table = Table(expand=True)
    table.add_column("Folder")
    table.add_column("Risk", justify="right")
    table.add_column("MissingFM", justify="right")
    table.add_column("Dup", justify="right")
    for item in top_folders[:8]:
        table.add_row(
            str(item.get("folder", ".")),
            str(item.get("risk_score", "")),
            str(item.get("missing_frontmatter", "")),
            str(item.get("duplicate_titles", "")),
        )
    if table.row_count == 0:
        table.add_row("No Gold data yet", "-", "-", "-")
    return table


def _table_from_models(rows: list[dict]) -> Table:
    table = Table(expand=True)
    table.add_column("Task")
    table.add_column("Model")
    table.add_column("Effort")
    for row in rows[:10]:
        table.add_row(str(row["task"]), str(row["model"]), str(row["effort"]))
    return table


def render_dashboard() -> Layout:
    status = build_status()
    paths = load_paths()
    layout = Layout()

    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=8),
    )
    layout["body"].split_row(
        Layout(name="left", ratio=2),
        Layout(name="center", ratio=3),
        Layout(name="right", ratio=2),
    )
    layout["left"].split_column(Layout(name="tasks"), Layout(name="docker"))
    layout["center"].split_column(Layout(name="health"), Layout(name="logs"))
    layout["right"].split_column(Layout(name="models"), Layout(name="events"))

    training_ready = status.get("training_ready", False)
    vault = status.get("vault_path") or "(not configured)"
    header_text = Text(f"Obsidian-Otto  |  vault={vault}  |  training_ready={training_ready}", style="bold cyan")
    layout["header"].update(Panel(header_text, title="Live Control Room"))

    task_panel = Panel(
        Group(
            Text("Active tasks", style="bold"),
            *[Text(f"- {name}") for name in status.get("active_tasks", [])] or [Text("- none")],
            Text(""),
            Text("Handoff next actions", style="bold"),
            *[Text(f"- {_shorten(item)}") for item in (status.get("handoff", {}).get("next_actions") or [])[:6]] or [Text("- none")],
        ),
        title="Tasks / Handoff",
    )
    layout["tasks"].update(task_panel)

    docker = status.get("docker", {})
    docker_lines = [f"status: {docker.get('status')}"]
    for svc in docker.get("services", [])[:6]:
        name = svc.get("Service") or svc.get("Name") or svc.get("raw", "service")
        state = svc.get("State") or svc.get("Status") or "n/a"
        docker_lines.append(f"- {name}: {state}")
    layout["docker"].update(Panel(Group(*[Text(line) for line in docker_lines]), title="Docker"))

    health = Group(
        Text("Top risky folders", style="bold"),
        _table_from_top_folders(status.get("top_folders", [])),
        Text(""),
        Text(f"Checkpoint scope: {status.get('checkpoint', {}).get('scope', 'n/a')}"),
        Text(f"SQLite: {status.get('sqlite_path')}"),
    )
    layout["health"].update(Panel(health, title="Health / Gold"))

    logs = status.get("recent_logs", [])
    log_group = Group(*[Text(_shorten(line, 180)) for line in logs] or [Text("No logs yet")])
    layout["logs"].update(Panel(log_group, title="Recent Logs"))

    layout["models"].update(Panel(_table_from_models(status.get("model_matrix", [])), title="Model Routing"))

    events = status.get("recent_events", [])
    event_group = Group(*[Text(_shorten(line, 180)) for line in events] or [Text("No events yet")])
    layout["events"].update(Panel(event_group, title="Recent Events"))

    footer_lines = [
        "Commands: status.bat | tui.bat | reindex.bat | kairos.bat | dream.bat | start.bat | stop.bat | docker-clean.bat",
        "Rule: prefer Gold -> Silver -> Chroma -> Bronze/raw",
    ]
    layout["footer"].update(Panel(Group(*[Text(line) for line in footer_lines]), title="Operator Notes"))
    return layout


def run_tui(refresh_seconds: float = 2.0) -> None:
    console = Console()
    try:
        with Live(render_dashboard(), refresh_per_second=max(1, int(1 / max(refresh_seconds, 0.2))), screen=True, console=console) as live:
            try:
                while True:
                    time.sleep(refresh_seconds)
                    live.update(render_dashboard())
            except KeyboardInterrupt:
                pass
            except Exception as exc:
                console.print(f"[red]TUI error: {exc}[/red]")
                raise
