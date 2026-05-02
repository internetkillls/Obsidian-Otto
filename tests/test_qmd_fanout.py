from __future__ import annotations

from types import SimpleNamespace

import pytest

import otto.cli as otto_cli
from otto.orchestration.qmd_fanout import JournalLead, run_qmd_seed_fanout


def _fanout_paths(tmp_path):
    return SimpleNamespace(
        state_root=tmp_path / "state",
        logs_root=tmp_path / "logs",
    )


def _fake_retrieval(seed: str, mode: str = "deep") -> dict:
    return {
        "mode": mode,
        "enough_evidence": True,
        "needs_deepening": False,
        "note_hits": [
            {
                "title": f"{seed} anchor 1",
                "path": ".Otto-Realm/Memory-Tiers/01-Facts/seed-1.md",
                "body_excerpt": "local anchor one",
                "source": "sqlite_fts",
                "relation_hints": {"topic": ["crack research", "open access"]},
            },
            {
                "title": f"{seed} anchor 2",
                "path": ".Otto-Realm/Brain/seed-2.md",
                "body_excerpt": "local anchor two",
                "source": "sqlite_fts",
                "relation_hints": {"topic": ["interface", "constraint"]},
            },
        ],
        "folder_hits": [{"folder": "20-Programs/Crack-Research"}],
        "state_hits": [],
        "graph_prep_hints": [
            {
                "title": f"{seed} anchor 1",
                "path": ".Otto-Realm/Memory-Tiers/01-Facts/seed-1.md",
                "relation_hints": {"topic": ["crack research", "open access"]},
            }
        ],
        "sources_used": ["sqlite", "chroma"],
    }


def _fake_openalex_calls():
    calls: list[tuple[str, bool, int]] = []

    def _fake_openalex(query: str, *, limit: int = 12, oa_only: bool = True) -> list[JournalLead]:
        calls.append((query, oa_only, limit))
        suffix = "oa" if oa_only else "journal"
        return [
            JournalLead(
                title=f"{query} {suffix} lead 1",
                url=f"https://example.org/{suffix}/{len(calls)}-1",
                journal="Journal of Seed Studies",
                year=2026,
                doi=f"10.1234/{suffix}.{len(calls)}.1",
                oa_status="oa" if oa_only else "journal",
                source="openalex",
                snippet="seed lead one",
            ),
            JournalLead(
                title=f"{query} {suffix} lead 2",
                url=f"https://example.org/{suffix}/{len(calls)}-2",
                journal="Journal of Seed Studies",
                year=2026,
                doi=f"10.1234/{suffix}.{len(calls)}.2",
                oa_status="oa" if oa_only else "journal",
                source="openalex",
                snippet="seed lead two",
            ),
        ]

    return calls, _fake_openalex


def test_qmd_seed_fanout_builds_fifty_deduped_outline_cards(tmp_path, monkeypatch):
    paths = _fanout_paths(tmp_path)
    calls, fake_openalex = _fake_openalex_calls()
    markdown_path = tmp_path / "qmd_seed_fanout.md"

    monkeypatch.setattr("otto.orchestration.qmd_fanout.load_paths", lambda: paths)
    monkeypatch.setattr("otto.orchestration.qmd_fanout.retrieve_breakdown", _fake_retrieval)
    monkeypatch.setattr("otto.orchestration.qmd_fanout.build_qmd_index_health", lambda: {"ok": True, "backend_is_qmd": True})
    monkeypatch.setattr("otto.orchestration.qmd_fanout._markdown_path", lambda: markdown_path)
    monkeypatch.setattr(
        "otto.orchestration.qmd_fanout._theme_pool",
        lambda seed, anchors, leads: [
            "interface drift",
            "scarcity boundary",
            "open access journal",
            "retrieval evidence",
            "collection shaping",
            "mechanism opacity",
            "conceptual inversion",
            "critical displacement",
            "method genealogy",
            "interface audit",
            "constraint mapping",
            "seed fanout",
        ],
    )
    monkeypatch.setattr("otto.orchestration.qmd_fanout._arxiv_fallback", lambda *args, **kwargs: pytest.fail("fallback should not run"))
    monkeypatch.setattr("otto.orchestration.qmd_fanout._openalex_query", fake_openalex)

    result = run_qmd_seed_fanout("crack research seed", count=50, journal_first=True)

    assert result["status"] == "ok"
    assert result["generated_day"] == result["generated_at"][:10]
    assert result["retrieval_breakdown"]["note_hit_count"] == 2
    assert result["retrieval_breakdown"]["sources_used"] == ["sqlite", "chroma"]
    assert len(result["outline_cards"]) == 50
    assert len({card["signature"] for card in result["outline_cards"]}) == 50
    assert all(card["title"].startswith(result["generated_day"]) for card in result["outline_cards"])
    assert all(card["collection_name"].count(" + ") == 1 for card in result["outline_cards"])
    assert result["journal_leads"]
    assert not result["fallback_leads"]
    assert calls[0][1] is True
    assert markdown_path.exists()
    assert "Retrieval Evidence" in markdown_path.read_text(encoding="utf-8")


def test_qmd_seed_fanout_respects_cooldown_and_force_now(tmp_path, monkeypatch):
    paths = _fanout_paths(tmp_path)
    _, fake_openalex = _fake_openalex_calls()
    markdown_path = tmp_path / "qmd_seed_fanout.md"

    monkeypatch.setattr("otto.orchestration.qmd_fanout.load_paths", lambda: paths)
    monkeypatch.setattr("otto.orchestration.qmd_fanout.retrieve_breakdown", _fake_retrieval)
    monkeypatch.setattr("otto.orchestration.qmd_fanout.build_qmd_index_health", lambda: {"ok": True, "backend_is_qmd": True})
    monkeypatch.setattr("otto.orchestration.qmd_fanout._markdown_path", lambda: markdown_path)
    monkeypatch.setattr(
        "otto.orchestration.qmd_fanout._theme_pool",
        lambda seed, anchors, leads: [
            "interface drift",
            "scarcity boundary",
            "open access journal",
            "retrieval evidence",
            "collection shaping",
            "mechanism opacity",
            "conceptual inversion",
            "critical displacement",
            "method genealogy",
            "interface audit",
            "constraint mapping",
            "seed fanout",
        ],
    )
    monkeypatch.setattr("otto.orchestration.qmd_fanout._arxiv_fallback", lambda *args, **kwargs: [])
    monkeypatch.setattr("otto.orchestration.qmd_fanout._openalex_query", fake_openalex)

    first = run_qmd_seed_fanout("crack research seed", count=12, journal_first=True)
    second = run_qmd_seed_fanout("crack research seed", count=12, journal_first=True)
    forced = run_qmd_seed_fanout("crack research seed", count=12, journal_first=True, force_now=True)

    assert first["status"] == "ok"
    assert second["status"] == "cooldown_active"
    assert forced["status"] == "ok"
    assert forced["force_now"] is True


def test_qmd_fanout_cli_dispatches(monkeypatch, capsys):
    monkeypatch.setattr(
        otto_cli,
        "run_qmd_seed_fanout",
        lambda seed, count=50, journal_first=True, force_now=False: {
            "status": "ok",
            "seed": seed,
            "count": count,
            "journal_first": journal_first,
            "force_now": force_now,
        },
    )

    exit_code = otto_cli.main(
        [
            "qmd-fanout",
            "--seed",
            "crack research seed",
            "--count",
            "7",
            "--no-journal-first",
            "--force-now",
        ]
    )

    captured = capsys.readouterr().out
    assert exit_code == 0
    assert '"seed": "crack research seed"' in captured
    assert '"count": 7' in captured
    assert '"journal_first": false' in captured
    assert '"force_now": true' in captured
