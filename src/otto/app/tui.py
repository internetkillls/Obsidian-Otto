from __future__ import annotations
import time

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .launcher import action_specs_for_screen
from .status import build_status


def _shorten(text: str, limit: int = 140) -> str:
    text = str(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _state_label(value: bool | None, *, positive: str, negative: str, unknown: str = "unknown") -> str:
    if value is None:
        return unknown
    return positive if value else negative


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
    layout["left"].split_column(Layout(name="tasks"), Layout(name="runtime"))
    layout["center"].split_column(Layout(name="health"), Layout(name="logs"))
    layout["right"].split_column(Layout(name="models"), Layout(name="events"))

    training_ready = status.get("training_ready", False)
    vault = status.get("vault_path") or "(not configured)"
    handoff = status.get("handoff", {}) or {}
    effective_next_actions = status.get("next_actions") or []
    header_text = Text(f"Obsidian-Otto  |  vault={vault}  |  training_ready={training_ready}", style="bold cyan")
    layout["header"].update(Panel(header_text, title="Live Control Room"))

    graph_lines = []
    if handoff.get("graph_demotion_review_path"):
        graph_lines = [
            Text(""),
            Text("Graph demotion", style="bold"),
            Text(f"- mode: {handoff.get('graph_demotion_next_apply_mode')}"),
            Text(f"- hotspot: {handoff.get('graph_demotion_hotspot_family')}"),
            Text(f"- quality: {handoff.get('graph_demotion_quality_verdict')}"),
            Text(f"- next: {_shorten(handoff.get('graph_demotion_next_action') or 'none', 120)}"),
        ]

    task_panel = Panel(
        Group(
            Text("Active tasks", style="bold"),
            *[Text(f"- {name}") for name in status.get("active_tasks", [])] or [Text("- none")],
            Text(""),
            Text("Handoff next actions", style="bold"),
            *[Text(f"- {_shorten(item)}") for item in effective_next_actions[:6]] or [Text("- none")],
            *graph_lines,
        ),
        title="Tasks / Handoff",
    )
    layout["tasks"].update(task_panel)

    runtime = status.get("runtime", {})
    infra = status.get("infra", {})
    vector = status.get("vector", {})
    gateway = status.get("openclaw_gateway", {})
    morpheus_bridge = status.get("morpheus_openclaw_bridge", {})
    docker_probe_status = str(infra.get("docker_probe_status") or "n/a")
    docker_probe_transport = str(infra.get("docker_probe_transport") or "").strip()
    docker_probe_line = docker_probe_status
    if docker_probe_transport and docker_probe_transport != "direct":
        docker_probe_line = f"{docker_probe_line} via {docker_probe_transport}"
    runtime_lines = [
        f"runtime: {runtime.get('status', 'unknown')}" + (f" (PID {runtime.get('pid')})" if runtime.get("pid") else ""),
        f"docker daemon: {_state_label(infra.get('daemon_running'), positive='up', negative='down')}",
        f"docker probe: {docker_probe_line}",
        f"postgres: {'reachable' if infra.get('postgres_reachable') else 'unreachable'}",
        f"mcp: {_state_label(infra.get('mcp_reachable') if infra.get('running_services_known') else None, positive='reachable', negative='down')}",
        f"chroma svc: {_state_label(vector.get('service_running'), positive='up', negative='down')}",
        f"chroma py: {'installed' if vector.get('python_package_installed') else 'missing'}",
        f"openclaw gateway: {gateway.get('status', 'unknown')}" + (f" (PID {','.join(str(pid) for pid in (gateway.get('pids') or []))})" if gateway.get("pids") else ""),
        "morpheus bridge: "
        f"{morpheus_bridge.get('bridge_mode', 'unavailable')} "
        f"(candidates={morpheus_bridge.get('candidate_count', 'n/a')}, ready={morpheus_bridge.get('ready_for_openclaw_dreaming', 'n/a')})",
    ]
    if gateway.get("checked_at"):
        runtime_lines.append(f"gateway checked: {_shorten(gateway.get('checked_at'), 40)}")
    if gateway.get("last_failure_at"):
        runtime_lines.append(f"gateway last failure: {_shorten(gateway.get('last_failure_at'), 40)}")
    layout["runtime"].update(Panel(Group(*[Text(line) for line in runtime_lines]), title="Runtime / Infra"))

    health = Group(
        Text("Top risky folders", style="bold"),
        _table_from_top_folders(status.get("top_folders", [])),
        Text(""),
        Text(f"Checkpoint scope: {status.get('checkpoint', {}).get('scope', 'n/a')}"),
        Text(f"SQLite: {status.get('sqlite', {}).get('path')}"),
        Text(f"SQLite notes: {status.get('sqlite', {}).get('note_count', 'n/a')}"),
        Text(f"Vector: {_shorten(status.get('vector', {}).get('note', 'n/a'), 100)}"),
        Text(f"OpenClaw probe: {_shorten(status.get('openclaw_gateway', {}).get('reason', 'n/a'), 100)}"),
        Text(
            "Morpheus bridge: "
            + _shorten(
                f"{morpheus_bridge.get('bridge_mode', 'unavailable')} / candidates={morpheus_bridge.get('candidate_count', 'n/a')} / ready={morpheus_bridge.get('ready_for_openclaw_dreaming', 'n/a')}",
                100,
            )
        ),
    )
    layout["health"].update(Panel(health, title="Health / Gold"))

    logs = status.get("recent_logs", [])
    log_group = Group(*[Text(_shorten(line, 180)) for line in logs] or [Text("No logs yet")])
    layout["logs"].update(Panel(log_group, title="Recent Logs"))

    layout["models"].update(Panel(_table_from_models(status.get("model_matrix", [])), title="Model Routing"))

    events = status.get("recent_events", [])
    event_group = Group(*[Text(_shorten(line, 180)) for line in events] or [Text("No events yet")])
    layout["events"].update(Panel(event_group, title="Recent Events"))

    controller_issue_lines = [f"controller: {_shorten(item, 140)}" for item in status.get("controller_issues", [])[:2]]
    infra_issue_lines = [f"infra: {_shorten(item, 140)}" for item in status.get("infra_issues", [])[:2]]
    home_actions = ", ".join(f"otto.bat {spec.name}" for spec in action_specs_for_screen("home")[:4])
    advanced_actions = ", ".join(
        f"otto.bat {spec.name}" for spec in [spec for spec in action_specs_for_screen("advanced") if spec.name in {"kairos", "dream", "openclaw-gateway-probe", "openclaw-plugin-reload"}]
    )
    footer_lines = [
        f"Commands: {home_actions}",
        f"Advanced: {advanced_actions}",
        "Use `otto.bat list` or `otto.bat describe <action>` for the full command surface.",
        "Rule: prefer Gold -> Silver -> Chroma -> Bronze/raw",
    ]
    footer_lines.extend(controller_issue_lines or ["controller: none"])
    footer_lines.extend(infra_issue_lines or ["infra: none"])
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
    finally:
        console.print("[dim]TUI stopped[/dim]")
