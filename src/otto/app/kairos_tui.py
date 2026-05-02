from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..config import load_paths, load_retrieval_config
from ..orchestration.vault_telemetry import run_vault_telemetry
from ..orchestration.kairos_directive import (
    KAIROSDirectiveEngine,
    produce_kairos_directives,
)
from ..retrieval.memory import retrieve_breakdown
from ..state import read_json

try:
    import chromadb
except Exception:  # pragma: no cover
    chromadb = None


def _fmt_score(score: float) -> str:
    return f"{score:.2f}"


def _score_color(score: float, inverted: bool = False) -> str:
    if inverted:
        # Higher = worse (uselessness)
        if score > 2.5: return "red bold"
        if score > 1.8: return "yellow"
        return "green"
    else:
        # Higher = better (training worth)
        if score > 2.0: return "green bold"
        if score > 1.0: return "cyan"
        return "yellow"


def run_kairos_tui() -> None:
    console = Console()
    engine = KAIROSDirectiveEngine()
    paths = load_paths()

    console.print(Panel(
        Text("KAIROS Deep-Dive - Sir Agathon's Vault Intelligence", style="bold cyan"),
        title="KAIROS TUI",
    ))
    console.print("Commands: [scan] [directives] [dig <folder>] [file <path>] [date <YYYY-MM-DD> <YYYY-MM-DD>] [train] [vector] [ask <query>] [compare <query>] [chunks <path>] [quit]")
    console.print()

    while True:
        try:
            raw = input("\nKAIROS> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]KAIROS TUI stopped[/dim]")
            break

        if not raw:
            continue

        parts = raw.split()
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd == "quit":
            break

        elif cmd == "scan":
            console.print("[cyan]Running vault telemetry...[/cyan]")
            try:
                report = run_vault_telemetry()
                _show_telemetry_report(console, report)
            except Exception as e:
                console.print(f"Scan failed: {e}", style="red", markup=False)

        elif cmd == "directives":
            console.print("[cyan]Loading directive manifest...[/cyan]")
            manifest = engine.current_manifest()
            if not manifest or not manifest.get("directives"):
                console.print("[yellow]No directive manifest. Running fresh...[/yellow]")
                manifest_obj = produce_kairos_directives(cycle=1)
                manifest = {
                    "directives": [d.to_dict() for d in manifest_obj.directives],
                    "summary": manifest_obj.summary,
                    "ts": manifest_obj.ts,
                }
            _show_directives(console, manifest)

        elif cmd == "dig":
            if not args:
                console.print("[yellow]Usage: dig <folder_name>[/yellow]")
                continue
            folder_query = " ".join(args)
            # Find matching area
            telemetry = engine._load_telemetry()
            matches = [a for a in telemetry.areas if folder_query.lower() in a.area.lower()]
            if not matches:
                console.print(f"[red]No area found matching: {folder_query}[/red]")
                console.print(f"Available: {', '.join(a.area for a in telemetry.areas[:10])}")
                continue
            area = matches[0].area
            console.print(f"[cyan]Digging into: {area}[/cyan]")
            result = engine.dig_area(area)
            _show_area_dig(console, result)

        elif cmd == "file":
            if not args:
                console.print("[yellow]Usage: file <note_path>[/yellow]")
                continue
            file_path = " ".join(args)
            console.print(f"[cyan]Analyzing: {file_path}[/cyan]")
            result = engine.dig_file(file_path)
            _show_file_dig(console, result)

        elif cmd == "date":
            if len(args) < 2:
                console.print("[yellow]Usage: date <YYYY-MM-DD> <YYYY-MM-DD>[/yellow]")
                continue
            date_from, date_to = args[0], args[1]
            console.print(f"[cyan]Date range: {date_from} -> {date_to}[/cyan]")
            result = engine.dig_date_range(date_from, date_to)
            _show_date_dig(console, result)

        elif cmd == "train":
            console.print("[cyan]Running directive production (train targets)...[/cyan]")
            manifest = produce_kairos_directives(cycle=1)
            train_targets = [d for d in manifest.directives if d.action == "train"]
            if not train_targets:
                console.print("[yellow]No high-value training areas found yet.[/yellow]")
                console.print("Run pipeline first to populate gold data.")
                continue
            console.print(f"\n[bold]Training Targets ({len(train_targets)} areas):[/bold]")
            for t in train_targets:
                console.print(f"  [{t.priority.upper()}] {t.area}")
                console.print(f"    -> {t.rationale[:120]}")
                console.print(f"    commands: {t.commands}")

        elif cmd == "vector":
            console.print("[cyan]Inspecting vector cache + collection...[/cyan]")
            _show_vector_overview(console, _vector_overview())

        elif cmd == "ask":
            if not args:
                console.print("[yellow]Usage: ask <query> or ask <fast|deep> <query>[/yellow]")
                continue
            mode, query = _parse_query_mode(args)
            if not query:
                console.print("[yellow]Usage: ask <query> or ask <fast|deep> <query>[/yellow]")
                continue
            console.print(f"[cyan]Querying KAIROS retrieval ({mode}): {query}[/cyan]")
            _show_query_result(console, retrieve_breakdown(query, mode=mode))

        elif cmd == "compare":
            if not args:
                console.print("[yellow]Usage: compare <query> or compare <fast|deep> <query>[/yellow]")
                continue
            mode, query = _parse_query_mode(args)
            if not query:
                console.print("[yellow]Usage: compare <query> or compare <fast|deep> <query>[/yellow]")
                continue
            console.print(f"[cyan]Comparing SQLite vs Chroma ({mode}): {query}[/cyan]")
            _show_compare_result(console, retrieve_breakdown(query, mode=mode))

        elif cmd == "chunks":
            if not args:
                console.print("[yellow]Usage: chunks <note_path>[/yellow]")
                continue
            note_path = " ".join(args)
            console.print(f"[cyan]Inspecting chunks for: {note_path}[/cyan]")
            _show_chunks(console, note_path, _vector_chunks_for_path(note_path))

        elif cmd == "help":
            console.print("\n[bold]KAIROS TUI Commands:[/bold]")
            console.print("  scan              - Full vault telemetry (uselessness + training worth)")
            console.print("  directives        - Show current directive manifest")
            console.print("  dig <folder>      - Deep-dive into a specific folder/area")
            console.print("  file <path>       - Analyze a single note's quality + recommendations")
            console.print("  date <from> <to>  - List all notes modified in date range")
            console.print("  train             - Show training targets (high signal areas)")
            console.print("  vector            - Show vector cache health + top chunked notes")
            console.print("  ask <query>       - Run hybrid semantic retrieval from KAIROS")
            console.print("  compare <query>   - Compare SQLite hits vs Chroma hits")
            console.print("  chunks <path>     - Show stored Chroma chunks for one note")
            console.print("  help              - This help")
            console.print("  quit              - Exit")

        else:
            console.print(f"[yellow]Unknown command: {cmd}. Type 'help' for commands.[/yellow]")


def _parse_query_mode(args: list[str]) -> tuple[str, str]:
    if args and args[0].lower() in {"fast", "deep"}:
        return args[0].lower(), " ".join(args[1:]).strip()
    return "fast", " ".join(args).strip()


def _vector_overview() -> dict[str, Any]:
    paths = load_paths()
    cfg = load_retrieval_config()
    summary = read_json(paths.artifacts_root / "reports" / "vector_summary.json", default={}) or {}
    collection_name = str(summary.get("collection") or cfg.get("vector", {}).get("collection_name", "otto_gold"))
    result = {
        "enabled": bool(summary.get("enabled", False)),
        "note": summary.get("note", "n/a"),
        "chunk_count": int(summary.get("chunk_count", 0) or 0),
        "collection": collection_name,
        "store_path": str(paths.chroma_path),
        "collection_exists": False,
        "top_paths": [],
        "error": None,
    }

    if chromadb is None:
        result["error"] = "chromadb Python package not available"
        return result

    try:
        client = chromadb.PersistentClient(path=str(paths.chroma_path))
        collection = client.get_or_create_collection(collection_name, metadata={"hnsw:space": "cosine"})
        payload = collection.get(include=["metadatas"])
        metadatas = payload.get("metadatas") or []
        counts = Counter(meta.get("path", "?") for meta in metadatas if meta and meta.get("path"))
        result["collection_exists"] = True
        result["top_paths"] = counts.most_common(10)
    except Exception as exc:
        result["error"] = str(exc)

    return result


def _vector_chunks_for_path(note_path: str) -> dict[str, Any]:
    overview = _vector_overview()
    if not overview.get("collection_exists"):
        return {"path": note_path, "chunks": [], "collection": overview.get("collection"), "error": overview.get("error")}

    paths = load_paths()
    try:
        client = chromadb.PersistentClient(path=str(paths.chroma_path))
        collection = client.get_or_create_collection(str(overview.get("collection")), metadata={"hnsw:space": "cosine"})
        payload = collection.get(include=["documents", "metadatas"])
    except Exception as exc:
        return {"path": note_path, "chunks": [], "collection": overview.get("collection"), "error": str(exc)}

    documents = payload.get("documents") or []
    metadatas = payload.get("metadatas") or []
    chunks = [
        {"index": idx, "text": doc or "", "title": (meta or {}).get("title", note_path)}
        for idx, (doc, meta) in enumerate(zip(documents, metadatas))
        if meta and meta.get("path") == note_path
    ]
    return {"path": note_path, "chunks": chunks, "collection": overview.get("collection"), "error": None}


def _show_telemetry_report(console: Console, report) -> None:
    console.print(f"\n[bold]Vault Telemetry Summary[/bold]")
    console.print(f"  Overall uselessness:    [{_score_color(report.overall_uselessness, inverted=True)}]{_fmt_score(report.overall_uselessness)}[/]")
    console.print(f"  Overall training worth: [{_score_color(report.overall_training_worth)}]{_fmt_score(report.overall_training_worth)}[/]")

    if report.high_value_areas:
        console.print(f"\n[green]High-value areas (high training worth):[/green]")
        for a in report.high_value_areas[:5]:
            console.print(f"  -> {a}")

    if report.dead_zones:
        console.print(f"\n[red]Dead zones (high uselessness):[/red]")
        for a in report.dead_zones[:5]:
            console.print(f"  [!] {a}")

    table = Table(title="Areas by Uselessness Score (worst first)", expand=True)
    table.add_column("Area", style="bold")
    table.add_column("Notes", justify="right")
    table.add_column("Useless", justify="right")
    table.add_column("Worth", justify="right")
    table.add_column("FM%", justify="right")
    table.add_column("Tags", justify="right")
    table.add_column("Priority")

    for area in sorted(report.areas, key=lambda a: -a.uselessness_score)[:12]:
        table.add_row(
            Path(area.area).name or area.area[-30:],
            str(area.note_count),
            f"[{_score_color(area.uselessness_score, inverted=True)}]{_fmt_score(area.uselessness_score)}[/]",
            f"[{_score_color(area.training_worth_score)}]{_fmt_score(area.training_worth_score)}[/]",
            f"{area.frontmatter_pct:.0%}",
            f"{area.tag_density:.1f}",
            area.dig_priority.upper(),
        )
    console.print(table)

    if report.dig_targets:
        console.print(f"\n[bold red]Critical/HIGH dig targets:[/bold red]")
        for t in report.dig_targets[:5]:
            console.print(f"  [{t['priority'].upper()}] {t['area']} - {t['reason'][:80]}")

    if report.train_targets:
        console.print(f"\n[bold green]Top training targets:[/bold green]")
        for t in report.train_targets[:3]:
            console.print(f"  [worth={t['training_worth']:.2f}] {t['area']} ({t['note_count']} notes)")


def _show_directives(console: Console, manifest: dict[str, Any]) -> None:
    directives = manifest.get("directives", [])
    summary = manifest.get("summary", {})
    ts = manifest.get("ts", "?")

    console.print(f"\n[bold]KAIROS Directives - {ts}[/bold]")
    console.print(f"  Total: {summary.get('total_directives', len(directives))} | "
                  f"dig={summary.get('dig',0)} train={summary.get('train',0)} refine={summary.get('refine',0)}")
    console.print(f"  [red]critical[/red]={summary.get('critical',0)} "
                  f"[yellow]high[/yellow]={summary.get('high',0)} "
                  f"[cyan]medium[/cyan]={summary.get('medium',0)}")

    for d in directives:
        action_color = {"dig": "red", "train": "green", "refine": "cyan"}.get(d.get("action", ""), "white")
        console.print(f"\n  [{d.get('priority','').upper()}] [{action_color}]{d.get('action','')}[/] {d.get('area','')}")
        console.print(f"    rationale: {d.get('rationale','')[:150]}")
        cmds = d.get("commands", [])
        if cmds:
            console.print(f"    commands: {cmds[0][:100]}")


def _show_area_dig(console: Console, result: dict[str, Any]) -> None:
    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        return

    tm = result["telemetry"]
    console.print(f"\n[bold]Area: {result['area']}[/bold]")
    console.print(f"  Notes: {result['note_count']}")
    console.print(f"  Uselessness: [{_score_color(tm['uselessness_score'], inverted=True)}]{tm['uselessness_score']:.2f}[/]")
    console.print(f"  Training worth: [{_score_color(tm['training_worth_score'])}]{tm['training_worth_score']:.2f}[/]")
    console.print(f"  Frontmatter: {tm['frontmatter_pct']:.0%} | Tags: {tm['tag_density']:.1f} | Signals: {tm['signal_density']:.2f}")
    console.print(f"  Orphan ratio: {tm['orphan_ratio']:.0%} | Priority: [bold]{tm['dig_priority'].upper()}[/bold]")
    console.print(f"\n  [cyan]Recommendation:[/cyan] {tm['recommendation']}")

    table = Table(title="Notes in area", expand=True)
    table.add_column("Title")
    table.add_column("FM", justify="center")
    table.add_column("Tags", justify="right")
    table.add_column("WL", justify="right")
    table.add_column("Scarcity", justify="right")
    table.add_column("mtime")

    for note in result.get("notes", [])[:20]:
        table.add_row(
            note["title"][:40],
            "Y" if note["has_frontmatter"] else "N",
            str(len(note["tags"])),
            str(len(note["wikilinks"])),
            str(len(note.get("scarcity") or [])),
            note["mtime"],
        )
    console.print(table)


def _show_file_dig(console: Console, result: dict[str, Any]) -> None:
    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        if result.get("hint"):
            console.print(f"[dim]{result['hint']}[/dim]")
        return

    console.print(f"\n[bold]{result['title']}[/bold]")
    console.print(f"  Path: {result['file']}")
    console.print(f"  mtime: {result['mtime']} | quality_score: [{_score_color(result['quality_score'])}]{result['quality_score']:.2f}[/]")

    if result.get("missing_fields"):
        console.print(f"  [yellow]Missing: {', '.join(result['missing_fields'])}[/yellow]")
    else:
        console.print("  [green]Y All signal fields present[/green]")

    if result.get("recommendations"):
        console.print("\n  [bold cyan]Recommendations:[/bold cyan]")
        for rec in result["recommendations"]:
            console.print(f"    -> {rec}")

    if result.get("frontmatter_text"):
        console.print(f"\n  [dim]Frontmatter: {result['frontmatter_text'][:200]}[/dim]")

    if result.get("body_preview"):
        console.print(f"\n  [dim]Body preview: {result['body_preview'][:200]}[/dim]")


def _show_date_dig(console: Console, result: dict[str, Any]) -> None:
    console.print(f"\n[bold]Date range: {result['date_from']} -> {result['date_to']}[/bold]")
    console.print(f"  Notes found: {result['note_count']}")

    table = Table(title="Notes in date range", expand=True)
    table.add_column("Title")
    table.add_column("FM", justify="center")
    table.add_column("Tags", justify="right")
    table.add_column("mtime")
    for note in result.get("notes", [])[:30]:
        table.add_row(
            note["title"][:40],
            "Y" if note["has_frontmatter"] else "N",
            str(len(note["tags"])),
            note["mtime"],
        )
    console.print(table)


def _show_vector_overview(console: Console, result: dict[str, Any]) -> None:
    console.print("\n[bold]Vector Cache Overview[/bold]")
    console.print(f"  Enabled: {result.get('enabled')}")
    console.print(f"  Note: {result.get('note')}")
    console.print(f"  Collection: {result.get('collection')}")
    console.print(f"  Store: {result.get('store_path')}")
    console.print(f"  Chunk count: {result.get('chunk_count')}")
    if result.get("error"):
        console.print(f"  [yellow]Inspector note:[/yellow] {result['error']}")
    if result.get("top_paths"):
        table = Table(title="Top chunked notes", expand=True)
        table.add_column("Path")
        table.add_column("Chunks", justify="right")
        for path, count in result["top_paths"]:
            table.add_row(path, str(count))
        console.print(table)


def _show_query_result(console: Console, result: dict[str, Any]) -> None:
    console.print("\n[bold]Hybrid Retrieval Result[/bold]")
    console.print(f"  Query: {result.get('query')}")
    console.print(f"  Sources used: {', '.join(result.get('sources_used', [])) or '(none)'}")
    console.print(f"  Enough evidence: {result.get('enough_evidence')}")
    console.print(f"  Needs deepening: {result.get('needs_deepening')}")
    _show_hit_table(console, "Fused note hits", result.get("note_hits", []), limit=8)

    folder_hits = result.get("folder_hits", [])
    if folder_hits:
        folder_table = Table(title="Folder hits", expand=True)
        folder_table.add_column("Folder")
        folder_table.add_column("Risk", justify="right")
        folder_table.add_column("Missing FM", justify="right")
        for hit in folder_hits:
            folder_table.add_row(hit.get("folder", ""), str(hit.get("risk_score", "")), str(hit.get("missing_frontmatter", "")))
        console.print(folder_table)

    state_hits = result.get("state_hits", [])
    if state_hits:
        console.print("\n[bold]State hits[/bold]")
        for hit in state_hits:
            console.print(f"  [{hit.get('source')}] {hit.get('snippet', '')[:180]}")


def _show_compare_result(console: Console, result: dict[str, Any]) -> None:
    console.print("\n[bold]Source Comparison[/bold]")
    _show_hit_table(console, "SQLite hits", result.get("sqlite_hits", []), limit=8)
    _show_hit_table(console, "Chroma hits", result.get("chroma_hits", []), limit=8)
    _show_hit_table(console, "Fused ranking", result.get("note_hits", []), limit=8)


def _show_hit_table(console: Console, title: str, hits: list[dict[str, Any]], limit: int = 8) -> None:
    if not hits:
        console.print(f"\n[dim]{title}: no hits[/dim]")
        return
    table = Table(title=title, expand=True)
    table.add_column("Title")
    table.add_column("Path")
    table.add_column("Source")
    table.add_column("Snippet")
    for hit in hits[:limit]:
        source = ",".join(hit.get("sources", [])) if hit.get("sources") else hit.get("source", "")
        snippet = (hit.get("body_excerpt") or hit.get("frontmatter_text") or hit.get("snippet") or "")[:120]
        table.add_row(hit.get("title", "(untitled)")[:40], hit.get("path", "")[:60], source[:24], snippet)
    console.print(table)


def _show_chunks(console: Console, note_path: str, result: dict[str, Any]) -> None:
    if result.get("error"):
        console.print(f"[red]{result['error']}[/red]")
        return
    chunks = result.get("chunks", [])
    console.print(f"\n[bold]Chunks for {note_path}[/bold]")
    console.print(f"  Collection: {result.get('collection')}")
    console.print(f"  Chunk count: {len(chunks)}")
    if not chunks:
        console.print("[yellow]No chunks found for that path.[/yellow]")
        return
    for chunk in chunks[:8]:
        console.print(Panel(chunk["text"][:700], title=f"chunk {chunk['index']}", expand=True))
