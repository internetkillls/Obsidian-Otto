from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from itertools import product
from pathlib import Path
from typing import Any

import requests

from ..config import load_paths, repo_root
from ..events import EVENT_OPENCLAW_RESEARCH, Event, EventBus
from ..logging_utils import append_jsonl
from ..openclaw_support import build_qmd_index_health
from ..retrieval.memory import retrieve_breakdown
from ..state import now_iso, read_json, write_json


DEFAULT_FANOUT_COUNT = 50
DEFAULT_FANOUT_COOLDOWN_HOURS = 6
OPENALEX_BASE_URL = "https://api.openalex.org/works"
ARXIV_API_URL = "https://export.arxiv.org/api/query"


@dataclass
class LocalAnchor:
    title: str
    path: str
    cue: str = ""
    relation_hints: dict[str, list[str]] = field(default_factory=dict)
    source: str = "local_memory"


@dataclass
class JournalLead:
    title: str
    url: str
    journal: str = ""
    year: int | None = None
    doi: str = ""
    oa_status: str = ""
    source: str = "openalex"
    snippet: str = ""


@dataclass
class OutlineCard:
    card_id: str
    collection_name: str
    material_object: str
    formal_object: str
    title: str
    thesis: str
    gap: str
    method: str
    why_now: str
    local_anchors: list[str] = field(default_factory=list)
    journal_leads: list[str] = field(default_factory=list)
    score: float = 0.0
    signature: str = ""
    promote: bool = False


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return cleaned[:80] or "seed"


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        cleaned = str(value).strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def _control_path() -> Path:
    return load_paths().state_root / "handoff" / "qmd_fanout_control.json"


def _latest_path() -> Path:
    return load_paths().state_root / "handoff" / "qmd_seed_fanout_latest.json"


def _markdown_path() -> Path:
    return repo_root() / "Otto-Realm" / "Handoff" / "qmd_seed_fanout.md"


def _parse_iso(ts: str) -> Any:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def _read_control() -> dict[str, Any]:
    return read_json(_control_path(), default={}) or {}


def _can_run(*, force_now: bool) -> tuple[bool, dict[str, Any]]:
    control = _read_control()
    if force_now:
        return True, control
    last_run = _parse_iso(str(control.get("last_run_at", "") or ""))
    if last_run is None:
        return True, control
    next_allowed = last_run + timedelta(hours=DEFAULT_FANOUT_COOLDOWN_HOURS)
    now = datetime.now(timezone.utc).astimezone()
    if now < next_allowed:
        return False, {
            "status": "cooldown_active",
            "last_run_at": str(control.get("last_run_at", "")),
            "next_allowed_at": next_allowed.isoformat(timespec="seconds"),
        }
    return True, control


def _journal_query_variants(seed: str, anchors: list[LocalAnchor]) -> list[str]:
    raw = seed.strip()
    variants = [raw]
    anchor_titles = [anchor.title for anchor in anchors[:3] if anchor.title]
    if anchor_titles:
        variants.append(f"{raw} {anchor_titles[0]}")
    if len(anchor_titles) >= 2:
        variants.append(f"{raw} {anchor_titles[0]} {anchor_titles[1]}")
    return _dedupe(variants)


def _openalex_query(query: str, *, limit: int = 12, oa_only: bool = True) -> list[JournalLead]:
    params = {
        "search": query,
        "per-page": min(max(limit, 1), 50),
    }
    if oa_only:
        params["filter"] = "type:journal-article,is_oa:true"
    else:
        params["filter"] = "type:journal-article"
    headers = {
        "User-Agent": "Obsidian-Otto/0.1 (+qmd fanout)",
        "Accept": "application/json",
    }
    try:
        resp = requests.get(OPENALEX_BASE_URL, params=params, headers=headers, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
    except Exception:
        return []
    results = payload.get("results") if isinstance(payload, dict) else []
    leads: list[JournalLead] = []
    if not isinstance(results, list):
        return []
    seen: set[str] = set()
    for item in results:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        doi = str(item.get("doi") or "").strip()
        url = str(item.get("id") or "").strip()
        if doi:
            url = doi
        if not title or url in seen:
            continue
        seen.add(url)
        primary_location = item.get("primary_location") if isinstance(item.get("primary_location"), dict) else {}
        source = primary_location.get("source") if isinstance(primary_location.get("source"), dict) else {}
        journal = str(
            source.get("display_name")
            or source.get("host_venue_name")
            or item.get("host_venue", {}).get("display_name")
            or ""
        ).strip()
        open_access = item.get("open_access") if isinstance(item.get("open_access"), dict) else {}
        oa_status = str(open_access.get("oa_status") or "").strip()
        year_value = item.get("publication_year")
        year = int(year_value) if isinstance(year_value, int) else None
        snippet = str(item.get("abstract") or "").strip()
        leads.append(
            JournalLead(
                title=title,
                url=url or title,
                journal=journal,
                year=year,
                doi=doi,
                oa_status=oa_status or ("oa" if oa_only else "journal"),
                source="openalex",
                snippet=snippet[:500],
            )
        )
    return leads


def _arxiv_fallback(query: str, *, limit: int = 10) -> list[JournalLead]:
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": min(max(limit, 1), 25),
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    headers = {
        "User-Agent": "Obsidian-Otto/0.1 (+qmd fanout)",
        "Accept": "application/atom+xml,application/xml,text/xml",
    }
    try:
        resp = requests.get(ARXIV_API_URL, params=params, headers=headers, timeout=20)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
    except Exception:
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    leads: list[JournalLead] = []
    for entry in root.findall("atom:entry", ns)[:limit]:
        title = "".join(entry.findtext("atom:title", default="", namespaces=ns).split()).strip()
        if not title:
            continue
        url = entry.findtext("atom:id", default="", namespaces=ns).strip()
        summary = entry.findtext("atom:summary", default="", namespaces=ns).strip()
        published = entry.findtext("atom:published", default="", namespaces=ns).strip()
        year = None
        if len(published) >= 4 and published[:4].isdigit():
            year = int(published[:4])
        leads.append(
            JournalLead(
                title=title,
                url=url or title,
                journal="arXiv",
                year=year,
                doi="",
                oa_status="preprint",
                source="arxiv",
                snippet=summary[:500],
            )
        )
    return leads


def _search_leads(seed: str, anchors: list[LocalAnchor], *, journal_first: bool, count: int) -> dict[str, Any]:
    variants = _journal_query_variants(seed, anchors)
    journal_leads: list[JournalLead] = []
    fallback_leads: list[JournalLead] = []
    for query in variants:
        if journal_first:
            journal_leads.extend(_openalex_query(query, limit=max(6, count // 3), oa_only=True))
            if len(journal_leads) < max(6, count // 3):
                journal_leads.extend(_openalex_query(query, limit=max(6, count // 3), oa_only=False))
        else:
            journal_leads.extend(_openalex_query(query, limit=max(6, count // 3), oa_only=False))
    journal_leads = _dedupe_journal_leads(journal_leads)
    if not journal_leads:
        fallback_leads = _arxiv_fallback(seed, limit=max(6, count // 3))
    return {
        "query_variants": variants,
        "journal_leads": journal_leads[: max(10, count // 2)],
        "fallback_leads": fallback_leads[: max(10, count // 4)],
        "fallback_used": bool(fallback_leads),
        "journal_first": journal_first,
    }


def _dedupe_journal_leads(leads: list[JournalLead]) -> list[JournalLead]:
    seen: set[str] = set()
    unique: list[JournalLead] = []
    for lead in leads:
        key = _normalize(f"{lead.title}|{lead.doi or lead.url}")
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(lead)
    return unique


def _extract_local_anchors(seed: str, package: dict[str, Any] | None = None) -> list[LocalAnchor]:
    package = package or retrieve_breakdown(seed, mode="deep")
    return _extract_local_anchors_from_package(seed, package)


def _extract_local_anchors_from_package(seed: str, package: dict[str, Any]) -> list[LocalAnchor]:
    anchors: list[LocalAnchor] = []
    for hit in (package.get("note_hits") or [])[:12]:
        path = str(hit.get("path") or "").strip()
        title = str(hit.get("title") or Path(path).stem or seed).strip()
        relation_hints = hit.get("relation_hints") if isinstance(hit.get("relation_hints"), dict) else {}
        anchors.append(
            LocalAnchor(
                title=title,
                path=path,
                cue=str(hit.get("body_excerpt") or hit.get("snippet") or ""),
                relation_hints={k: [str(v) for v in values] if isinstance(values, list) else [] for k, values in relation_hints.items()},
                source=str(hit.get("source") or "local_memory"),
            )
        )
    for hint in (package.get("graph_prep_hints") or [])[:8]:
        path = str(hint.get("path") or "").strip()
        title = str(hint.get("title") or Path(path).stem or seed).strip()
        relation_hints = hint.get("relation_hints") if isinstance(hint.get("relation_hints"), dict) else {}
        anchors.append(
            LocalAnchor(
                title=title,
                path=path,
                cue="",
                relation_hints={k: [str(v) for v in values] if isinstance(values, list) else [] for k, values in relation_hints.items()},
                source="graph_prep",
            )
        )
    if not anchors:
        anchors.append(LocalAnchor(title=seed, path="", cue=seed, source="seed"))
    return _dedupe_anchors(anchors)


def _summarize_retrieval(package: dict[str, Any]) -> dict[str, Any]:
    note_hits = list(package.get("note_hits") or [])
    folder_hits = list(package.get("folder_hits") or [])
    state_hits = list(package.get("state_hits") or [])
    graph_prep_hints = list(package.get("graph_prep_hints") or [])
    return {
        "mode": str(package.get("mode", "")),
        "enough_evidence": bool(package.get("enough_evidence", False)),
        "needs_deepening": bool(package.get("needs_deepening", False)),
        "sources_used": list(package.get("sources_used") or []),
        "note_hit_count": len(note_hits),
        "folder_hit_count": len(folder_hits),
        "state_hit_count": len(state_hits),
        "graph_prep_hint_count": len(graph_prep_hints),
        "top_note_hits": [
            {
                "title": str(hit.get("title") or ""),
                "path": str(hit.get("path") or ""),
                "source": str(hit.get("source") or ""),
            }
            for hit in note_hits[:5]
        ],
    }


def _dedupe_anchors(anchors: list[LocalAnchor]) -> list[LocalAnchor]:
    seen: set[str] = set()
    unique: list[LocalAnchor] = []
    for anchor in anchors:
        key = _normalize(f"{anchor.title}|{anchor.path}")
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(anchor)
    return unique


def _theme_pool(seed: str, anchors: list[LocalAnchor], leads: list[JournalLead]) -> list[str]:
    pool: list[str] = []
    pool.extend([seed])
    pool.extend([anchor.title for anchor in anchors])
    pool.extend([lead.title for lead in leads[:8]])
    pool.extend([lead.journal for lead in leads[:8] if lead.journal])
    for anchor in anchors:
        for values in anchor.relation_hints.values():
            pool.extend(values)
    token_candidates = re.findall(r"[A-Za-z0-9]{4,}", " ".join(pool))
    return _dedupe([candidate.replace("_", " ").strip() for candidate in pool + token_candidates])


def _method_pool() -> list[str]:
    return [
        "mechanism scan",
        "boundary test",
        "interface audit",
        "comparative genealogy",
        "formalization pass",
        "measurement pass",
        "critical inversion",
        "translation bridge",
        "operational repair",
        "journal triangulation",
    ]


def _gap_pool() -> list[str]:
    return [
        "hidden assumption",
        "scope drift",
        "evidence asymmetry",
        "retrieval noise",
        "method mismatch",
        "journal record gap",
        "boundary ambiguity",
        "mechanism opacity",
        "classification leak",
        "translation failure",
    ]


def _lead_overlap_score(text: str, lead: JournalLead) -> int:
    text_tokens = set(_normalize(text).split())
    lead_tokens = set(_normalize(" ".join([lead.title, lead.journal, lead.snippet])).split())
    return len(text_tokens & lead_tokens)


def _best_leads_for_card(theme: str, leads: list[JournalLead], limit: int = 2) -> list[JournalLead]:
    ranked = sorted(leads, key=lambda lead: (-_lead_overlap_score(theme, lead), -len(_normalize(lead.title).split()), lead.title))
    return ranked[:limit]


def _score_card(seed: str, theme: str, method: str, gap: str, anchors: list[LocalAnchor], leads: list[JournalLead]) -> float:
    seed_tokens = set(_normalize(seed).split())
    theme_tokens = set(_normalize(theme).split())
    method_tokens = set(_normalize(method).split())
    gap_tokens = set(_normalize(gap).split())
    anchor_blob = " ".join(f"{a.title} {a.cue}" for a in anchors)
    lead_blob = " ".join(f"{l.title} {l.journal} {l.snippet}" for l in leads)
    anchor_tokens = set(_normalize(anchor_blob).split())
    lead_tokens = set(_normalize(lead_blob).split())
    score = 0.0
    score += 3.0 * len(seed_tokens & theme_tokens)
    score += 2.0 * len(seed_tokens & method_tokens)
    score += 1.5 * len(theme_tokens & anchor_tokens)
    score += 1.5 * len(theme_tokens & lead_tokens)
    score += 1.0 * len(method_tokens & lead_tokens)
    score += 0.5 * len(gap_tokens & anchor_tokens)
    return score


def _build_cards(
    seed: str,
    anchors: list[LocalAnchor],
    journal_leads: list[JournalLead],
    fallback_leads: list[JournalLead],
    *,
    paper_date: str,
    count: int,
) -> list[OutlineCard]:
    themes = _theme_pool(seed, anchors, journal_leads + fallback_leads)
    methods = _method_pool()
    gaps = _gap_pool()
    if len(themes) < 6:
        themes.extend([f"{seed} lens", "retrospective", "operational", "governance", "boundary", "repair"])
    if len(themes) < 10:
        themes.extend([lead.title for lead in fallback_leads[:5]])
    themes = _dedupe(themes)
    product_space = product(themes[:12], methods, gaps)
    cards: list[OutlineCard] = []
    seen_signatures: set[str] = set()
    all_leads = journal_leads + fallback_leads
    for theme, method, gap in product_space:
        chosen_leads = _best_leads_for_card(theme, all_leads, limit=2)
        anchor_labels = [anchor.title for anchor in anchors[:4]]
        material_object = theme
        formal_object = method
        collection_name = f"{material_object} + {formal_object}"
        paper_title = f"{paper_date} - {collection_name} - {theme.title()}"
        thesis = (
            f"{seed} can be reconstructed through {theme}, where {method} clarifies the live constraint rather than leaving the problem at the level of description."
        )
        gap_text = f"The current note stack still leaves {gap} under-specified."
        why_now = (
            f"Local memory points to {', '.join(anchor_labels[:2]) if anchor_labels else seed}, while journal-first discovery surfaced {chosen_leads[0].title if chosen_leads else 'no lead'}."
        )
        signature = _normalize(f"{collection_name}|{paper_title}|{thesis}|{gap_text}|{method}")
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        score = _score_card(seed, theme, method, gap, anchors, chosen_leads)
        card = OutlineCard(
            card_id=f"card-{len(cards)+1:02d}",
            collection_name=collection_name,
            material_object=material_object,
            formal_object=formal_object,
            title=paper_title,
            thesis=thesis,
            gap=gap_text,
            method=method,
            why_now=why_now,
            local_anchors=anchor_labels,
            journal_leads=[lead.title for lead in chosen_leads],
            score=round(score, 3),
            signature=signature,
        )
        cards.append(card)
        if len(cards) >= count:
            break
    return cards


def _render_markdown(seed: str, result: dict[str, Any]) -> str:
    lines: list[str] = []
    retrieval = result.get("retrieval_breakdown", {})
    lines.extend(
        [
            f"# QMD Seed Fanout - {seed}",
            "",
            f"- generated_at: {result['generated_at']}",
            f"- generated_day: {result.get('generated_day', 'n/a')}",
            f"- journal_first: {result['journal_first']}",
            f"- force_now: {result['force_now']}",
            f"- qmd_health_ok: {result['qmd_health'].get('ok', False)}",
            "",
            "## Retrieval Evidence",
            f"- enough_evidence: {retrieval.get('enough_evidence', False)}",
            f"- needs_deepening: {retrieval.get('needs_deepening', False)}",
            f"- sources_used: {', '.join(retrieval.get('sources_used', [])) or '(none)'}",
            f"- note_hit_count: {retrieval.get('note_hit_count', 0)}",
            f"- folder_hit_count: {retrieval.get('folder_hit_count', 0)}",
            f"- state_hit_count: {retrieval.get('state_hit_count', 0)}",
            f"- graph_prep_hint_count: {retrieval.get('graph_prep_hint_count', 0)}",
            "",
            "## Local Memory Anchors",
        ]
    )
    for anchor in result.get("local_anchors", [])[:12]:
        lines.append(f"- {anchor['title']} | path={anchor['path']} | source={anchor['source']}")
    if not result.get("local_anchors"):
        lines.append("- (none)")
    lines.extend(["", "## Journal Leads"])
    for lead in result.get("journal_leads", [])[:12]:
        lines.append(
            f"- {lead['title']} | journal={lead['journal']} | year={lead['year'] or 'n/a'} | oa={lead['oa_status'] or 'n/a'} | url={lead['url']}"
        )
    if not result.get("journal_leads"):
        lines.append("- (none)")
    if result.get("fallback_leads"):
        lines.extend(["", "## Fallback Leads"])
        for lead in result.get("fallback_leads", [])[:8]:
            lines.append(f"- {lead['title']} | journal={lead['journal']} | year={lead['year'] or 'n/a'} | url={lead['url']}")
    lines.extend(["", f"## {len(result.get('outline_cards', []))} Outline Cards"])
    for card in result.get("outline_cards", []):
        lines.extend(
            [
                "",
                f"### {card['card_id']}. {card['title']}",
                f"- CollectionName: {card['collection_name']}",
                f"- Material object: {card['material_object']}",
                f"- Formal object: {card['formal_object']}",
                f"- Thesis: {card['thesis']}",
                f"- Gap: {card['gap']}",
                f"- Method: {card['method']}",
                f"- Why now: {card['why_now']}",
                f"- Local anchors: {', '.join(card['local_anchors']) or '(none)'}",
                f"- Journal leads: {', '.join(card['journal_leads']) or '(none)'}",
                f"- Score: {card['score']}",
            ]
        )
    lines.extend(["", "## Promotion Shortlist"])
    for card in result.get("promotion_shortlist", []):
        lines.append(
            f"- {card['card_id']} | {card['title']} | collection={card['collection_name']} | score={card['score']}"
        )
    if not result.get("promotion_shortlist"):
        lines.append("- (none)")
    lines.extend(["", "## Notes"])
    for warning in result.get("warnings", []) or []:
        lines.append(f"- {warning}")
    if not result.get("warnings"):
        lines.append("- (none)")
    return "\n".join(lines) + "\n"


def run_qmd_seed_fanout(
    seed: str,
    *,
    count: int = DEFAULT_FANOUT_COUNT,
    journal_first: bool = True,
    force_now: bool = False,
) -> dict[str, Any]:
    if count <= 0:
        raise ValueError("count must be positive")

    can_run, control = _can_run(force_now=force_now)
    if not can_run:
        result = {
            "status": "cooldown_active",
            "seed": seed,
            "count": count,
            "journal_first": journal_first,
            "force_now": force_now,
            "last_run_at": control.get("last_run_at", ""),
            "next_allowed_at": control.get("next_allowed_at", ""),
        }
        write_json(_latest_path(), result)
        return result

    qmd_health = build_qmd_index_health()
    retrieval_breakdown = retrieve_breakdown(seed, mode="deep")
    anchors = _extract_local_anchors_from_package(seed, retrieval_breakdown)
    search = _search_leads(seed, anchors, journal_first=journal_first, count=count)
    generated_at = now_iso()
    generated_dt = _parse_iso(generated_at) or datetime.now(timezone.utc).astimezone()
    generated_day = generated_dt.date().isoformat()
    cards = _build_cards(
        seed,
        anchors,
        search["journal_leads"],
        search["fallback_leads"],
        paper_date=generated_day,
        count=count,
    )
    promotion_shortlist = sorted(cards, key=lambda card: (-card.score, card.card_id))[:10]
    result = {
        "status": "ok",
        "generated_at": generated_at,
        "generated_day": generated_day,
        "seed": seed,
        "count": count,
        "journal_first": journal_first,
        "force_now": force_now,
        "qmd_health": qmd_health,
        "retrieval_breakdown": _summarize_retrieval(retrieval_breakdown),
        "query_variants": search["query_variants"],
        "local_anchors": [asdict(anchor) for anchor in anchors],
        "journal_leads": [asdict(lead) for lead in search["journal_leads"]],
        "fallback_leads": [asdict(lead) for lead in search["fallback_leads"]],
        "outline_cards": [asdict(card) for card in cards],
        "promotion_shortlist": [asdict(card) for card in promotion_shortlist],
        "warnings": [],
    }
    if not search["journal_leads"]:
        result["warnings"].append("No OA journal lead returned; fallback to repository/preprint leads was used.")
    if not qmd_health.get("ok", False):
        result["warnings"].append("QMD health is not green; retrieval still ran against the local stack.")

    markdown_path = _markdown_path()
    json_path = _latest_path()
    control_path = _control_path()
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(_render_markdown(seed, result), encoding="utf-8")
    write_json(json_path, result)
    write_json(
        control_path,
        {
            "last_run_at": result["generated_at"],
            "next_allowed_at": (generated_dt + timedelta(hours=DEFAULT_FANOUT_COOLDOWN_HOURS)).isoformat(timespec="seconds"),
            "last_seed": seed,
            "last_count": count,
            "last_force_now": force_now,
            "last_markdown_path": str(markdown_path),
            "last_json_path": str(json_path),
        },
    )
    append_jsonl(
        load_paths().state_root / "run_journal" / "qmd_seed_fanout.jsonl",
        {
            "ts": result["generated_at"],
            "seed": seed,
            "count": count,
            "journal_first": journal_first,
            "force_now": force_now,
            "outline_count": len(cards),
            "promotion_shortlist": [card.card_id for card in promotion_shortlist],
            "qmd_health_ok": bool(qmd_health.get("ok", False)),
        },
    )
    EventBus().publish(
        Event(
            type=EVENT_OPENCLAW_RESEARCH,
            source="otto",
            payload={
                "seed": seed,
                "count": count,
                "journal_first": journal_first,
                "force_now": force_now,
                "outline_count": len(cards),
                "markdown_path": str(markdown_path),
                "json_path": str(json_path),
                "qmd_health_ok": bool(qmd_health.get("ok", False)),
            },
        )
    )
    result["markdown_path"] = str(markdown_path)
    result["json_path"] = str(json_path)
    result["control_path"] = str(control_path)
    return result
