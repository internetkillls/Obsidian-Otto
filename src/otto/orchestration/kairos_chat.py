from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from ..config import load_paths, load_retrieval_config
from ..retrieval.memory import retrieve_breakdown
from ..state import now_iso, write_json

try:
    import chromadb
except Exception:  # pragma: no cover
    chromadb = None


class KAIROSChatHandler:
    """Handles Sir Agathon's natural language commands to KAIROS.

    Can be called from:
    - OpenClaw (via MCP tool, natural language)
    - Telegram bot (via chat message)
    - TUI (already built in kairos_tui.py)

    Command patterns:
      "dig Projects"          → dig_area("Projects")
      "dig this folder"        → use current context from OpenClaw
      "train on Areas"        → show training targets filtered to that area
      "scan vault"             → run full telemetry
      "file Notes/test.md"     → analyze single file
      "date 2026-03-01 to 2026-04-01" → notes in range
      "what's useless"         → show dead_zones
      "what's worth training"  → show train_targets
      "find notes about X"     → hybrid sqlite + chroma retrieval
      "deepen X"              → rerun retrieval in deep mode if fast mode finds no trustworthy evidence
      "compare X"              → compare sparse vs dense retrieval
      "show vector status"     → vector cache / chroma summary
      "show chunks for X.md"   → inspect stored vector chunks for one note
      "give me directives"     → show full directive manifest
      "how's my vault"         → vault summary
    """

    def __init__(self):
        self.paths = load_paths()

    def handle(self, message: str) -> dict[str, Any]:
        """Parse and route a natural language command to KAIROS."""
        msg = message.strip().lower()

        # ── dig commands ─────────────────────────────────────────────────
        if msg.startswith("dig ") or "dig into" in msg:
            target = self._extract_target(msg, ["dig ", "dig into ", "dig into the ", "dig the "])
            return self._dig(target or "")

        # ── train commands ───────────────────────────────────────────────
        if "train" in msg or "training" in msg:
            area = self._extract_target(msg, ["train on ", "training on ", "train in "])
            return self._train_targets(area)

        # ── scan commands ────────────────────────────────────────────────
        if any(k in msg for k in ["scan", "how's", "how is", "vault summary", "vault status", "quality check"]):
            return self._vault_summary()

        # ── file analysis ────────────────────────────────────────────────
        if msg.startswith("file ") or "analyze" in msg and ".md" in msg:
            note_path = self._extract_note_path(message)
            if note_path:
                return self._file_analysis(note_path)
            return {"error": "Could not find a file path in your message", "hint": "Try: file Projects/Note.md"}

        # ── date range ──────────────────────────────────────────────────
        if "date" in msg or "between" in msg or "from" in msg and "to" in msg:
            dates = self._extract_dates(message)
            if dates:
                return self._date_range(dates[0], dates[1])
            return {"error": "Could not parse date range. Use: date 2026-03-01 to 2026-04-01"}

        # ── useless / dead zones ─────────────────────────────────────────
        if any(k in msg for k in ["useless", "dead zone", "bad quality", "messy"]):
            return self._dead_zones()

        # ── worth training ───────────────────────────────────────────────
        if any(k in msg for k in ["worth training", "high value", "good data", "signal", "training data"]):
            return self._train_targets(None)

        # ── directives ───────────────────────────────────────────────────
        if "directive" in msg or "strategy" in msg or "what to do" in msg or "next actions" in msg:
            return self._directives()

        # ── compare retrieval modes ─────────────────────────────────────
        if any(
            msg.startswith(prefix)
            for prefix in [
                "deepen ",
                "deepen query ",
                "deepen retrieval for ",
                "deepen search for ",
                "perdalam ",
                "perdalam query ",
                "dalami ",
                "dalami query ",
            ]
        ):
            target = self._extract_target(
                msg,
                [
                    "deepen query ",
                    "deepen retrieval for ",
                    "deepen search for ",
                    "deepen ",
                    "perdalam query ",
                    "perdalam retrieval untuk ",
                    "perdalam pencarian untuk ",
                    "perdalam ",
                    "dalami query ",
                    "dalami ",
                ],
            )
            return self._deepen(target or "")

        if (
            msg.startswith("compare ")
            or msg.startswith("bandingkan ")
            or "compare sqlite" in msg
            or "compare chroma" in msg
            or "sparse vs dense" in msg
            or "sparse vs vector" in msg
        ):
            target = self._extract_target(
                msg,
                [
                    "bandingkan sparse vs vector untuk ",
                    "bandingkan sqlite vs vector untuk ",
                    "bandingkan sparse vs dense untuk ",
                    "sparse vs dense for ",
                    "compare sqlite ",
                    "compare chroma ",
                    "bandingkan ",
                    "compare ",
                ],
            )
            return self._compare(target or "")

        # ── vector / chunk inspection ───────────────────────────────────
        if any(k in msg for k in ["vector status", "vector cache", "embedding status", "chroma status", "status vector", "status chroma"]):
            return self._vector_status()
        if any(k in msg for k in ["chunk", "potongan", "cuplikan"]) and ".md" in message:
            note_path = self._extract_note_path(message)
            if note_path:
                return self._chunks_for_path(note_path)
            return {"error": "Could not find a note path for chunk inspection", "hint": "Try: show chunks for Projects/Note.md"}

        # ── folder quality ───────────────────────────────────────────────
        if any(k in msg for k in ["folder quality", "folder risk", "folder analysis", "folder score"]):
            return self._folder_quality()

        # ── semantic / hybrid retrieval ─────────────────────────────────
        if any(
            k in msg
            for k in [
                "find ",
                "search ",
                "fetch ",
                "retrieve ",
                "look up ",
                "lookup ",
                "semantic ",
                "what do you know about ",
                "cari ",
                "carikan ",
                "ambil catatan ",
                "ambil note ",
                "cari catatan ",
            ]
        ):
            query = self._extract_target(
                msg,
                [
                    "find notes about ",
                    "find ",
                    "search for ",
                    "search ",
                    "fetch ",
                    "retrieve ",
                    "look up ",
                    "lookup ",
                    "semantic search for ",
                    "what do you know about ",
                    "cari catatan tentang ",
                    "cari catatan soal ",
                    "cari catatan ",
                    "cari note tentang ",
                    "cari note ",
                    "carikan catatan tentang ",
                    "carikan ",
                    "ambil catatan tentang ",
                    "ambil note tentang ",
                ],
            )
            return self._ask(query or message.strip(), mode="auto")

        # ── help ─────────────────────────────────────────────────────────
        if any(k in msg for k in ["help", "commands", "what can", "kairos can"]):
            return self._help()

        return {
            "error": f"I don't understand: '{message[:50]}...'",
            "hint": "Try: 'dig Projects', 'scan vault', 'train on Areas', 'what's useless', 'file Notes/test.md'",
            "available_commands": [
                "dig <folder>       — deep-dive into folder quality + recommendations",
                "scan               — full vault telemetry (uselessness + training worth)",
                "train [on <area>]  — show training targets",
                "file <path.md>     — analyze a single note",
                "date <from> <to>    — notes modified in range",
                "what's useless     — show dead zones (low quality areas)",
                "what's worth training — show high signal areas",
                "find <query>       — hybrid retrieval with one-shot auto-deepen when fast mode is too weak",
                "deepen <query>     — automatically widen retrieval only when fast mode is too weak",
                "compare <query>    — compare SQLite vs Chroma hits",
                "vector status      — show vector cache / Chroma state",
                "show chunks for <path.md> — inspect stored vector chunks",
                "directives         — show current KAIROS strategy directives",
                "help               — this help",
            ],
        }

    def _ask(self, query: str, mode: str = "auto") -> dict[str, Any]:
        cleaned = query.strip()
        if not cleaned:
            return {"error": "Query is required", "hint": "Try: find notes about operator rhythm"}
        if mode == "auto":
            fast_package = retrieve_breakdown(cleaned, mode="fast")
            if fast_package.get("enough_evidence") or not self._auto_deepen_enabled():
                result = self._result_from_package(
                    cleaned,
                    fast_package,
                    resolved_mode="fast",
                    requested_mode="auto",
                )
                result["search_policy"] = {
                    "requested": "auto",
                    "resolved": "fast",
                    "auto_deepen_attempted": False,
                    "auto_deepen_enabled": self._auto_deepen_enabled(),
                }
                return result
            return self._deepen_from_fast_package(cleaned, fast_package, trigger="auto")
        package = retrieve_breakdown(cleaned, mode=mode)
        return self._result_from_package(cleaned, package, resolved_mode=mode)

    def _deepen(self, query: str) -> dict[str, Any]:
        cleaned = query.strip()
        if not cleaned:
            return {"error": "Query is required", "hint": "Try: deepen operator rhythm"}

        fast_package = retrieve_breakdown(cleaned, mode="fast")
        if fast_package.get("enough_evidence"):
            result = self._result_from_package(cleaned, fast_package, resolved_mode="fast")
            result["summary"] = "Fast retrieval already found enough evidence, so KAIROS skipped the wider deep pass."
            result["escalation"] = {
                "requested": "deepen",
                "performed": False,
                "trigger": "fast-sufficient",
            }
            return result

        return self._deepen_from_fast_package(cleaned, fast_package, trigger="manual")

    def _deepen_from_fast_package(self, query: str, fast_package: dict[str, Any], *, trigger: str) -> dict[str, Any]:
        deep_package = retrieve_breakdown(query, mode="deep")
        result = self._result_from_package(
            query,
            deep_package,
            resolved_mode="deep",
            requested_mode="auto" if trigger == "auto" else None,
        )
        result["escalation"] = {
            "requested": "deepen" if trigger == "manual" else "auto",
            "performed": True,
            "trigger": "fast-no-evidence",
            "fast_sources_used": fast_package.get("sources_used", []),
            "fast_note_hits": len(fast_package.get("note_hits", [])),
            "fast_folder_hits": len(fast_package.get("folder_hits", [])),
        }
        if trigger == "auto":
            result["search_policy"] = {
                "requested": "auto",
                "resolved": "deep",
                "auto_deepen_attempted": True,
                "auto_deepen_enabled": True,
            }
        if result["enough_evidence"]:
            result["summary"] = "KAIROS widened the retrieval window after fast mode found nothing trustworthy."
        else:
            fallback = self._build_no_evidence_fallback(
                query,
                deep_package,
                attempted_mode="deep",
                escalated=True,
            )
            result["summary"] = fallback["message"]
            result["fallback"] = fallback
            result["suggested_commands"] = fallback["suggested_commands"]
            result["auto_escalate"] = fallback["auto_escalate"]
            result["rewrite_suggestions"] = fallback["rewrite_suggestions"]
            result["suggested_queries"] = fallback["suggested_queries"]
        return result

    def _result_from_package(
        self,
        query: str,
        package: dict[str, Any],
        *,
        resolved_mode: str,
        requested_mode: str | None = None,
    ) -> dict[str, Any]:
        result = {
            "query": query,
            "mode": resolved_mode,
            "sources_used": package.get("sources_used", []),
            "enough_evidence": package.get("enough_evidence", False),
            "needs_deepening": package.get("needs_deepening", False),
            "note_hits": package.get("note_hits", []),
            "sqlite_hits": package.get("sqlite_hits", []),
            "chroma_hits": package.get("chroma_hits", []),
            "best_suppressed_chroma_hit": package.get("best_suppressed_chroma_hit"),
            "dense_diagnostics": package.get("dense_diagnostics", {}),
            "graph_prep_hints": package.get("graph_prep_hints", []),
            "folder_hits": package.get("folder_hits", []),
            "state_hits": package.get("state_hits", []),
        }
        if requested_mode and requested_mode != resolved_mode:
            result["requested_mode"] = requested_mode
        if not result["enough_evidence"]:
            fallback = self._build_no_evidence_fallback(query, package, attempted_mode=resolved_mode)
            result["summary"] = fallback["message"]
            result["fallback"] = fallback
            result["suggested_commands"] = fallback["suggested_commands"]
            result["auto_escalate"] = fallback["auto_escalate"]
            result["rewrite_suggestions"] = fallback["rewrite_suggestions"]
            result["suggested_queries"] = fallback["suggested_queries"]
        return result

    def _rewrite_cfg(self) -> dict[str, Any]:
        return load_retrieval_config().get("rewrite", {})

    def _auto_deepen_enabled(self) -> bool:
        return bool(self._rewrite_cfg().get("auto_deepen_on_no_evidence", True))

    def _aliases_from_frontmatter(self, frontmatter_text: str | None) -> list[str]:
        text = str(frontmatter_text or "").strip()
        if not text:
            return []
        aliases: list[str] = []
        try:
            data = yaml.safe_load(text)
        except Exception:
            data = None
        if isinstance(data, dict):
            raw_aliases = data.get("aliases")
            if isinstance(raw_aliases, list):
                aliases.extend(str(item).strip() for item in raw_aliases if str(item).strip())
            elif isinstance(raw_aliases, str) and raw_aliases.strip():
                aliases.append(raw_aliases.strip())

        if not aliases:
            inline = re.search(r"(?mi)^aliases:\s*\[(.*?)\]\s*$", text)
            if inline:
                aliases.extend(part.strip().strip("'\"") for part in inline.group(1).split(",") if part.strip())
            else:
                block = re.search(r"(?mis)^aliases:\s*\n((?:[ \t]*-\s*.*\n?)*)", text)
                if block:
                    aliases.extend(
                        line.strip()[2:].strip().strip("'\"")
                        for line in block.group(1).splitlines()
                        if line.strip().startswith("- ")
                    )

        seen: set[str] = set()
        deduped: list[str] = []
        for alias in aliases:
            lowered = alias.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(alias)
        return deduped

    def _aliases_from_json_blob(self, aliases_json: str | None) -> list[str]:
        raw = str(aliases_json or "").strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = raw
        if isinstance(parsed, list):
            values = [str(item).strip() for item in parsed if str(item).strip()]
        elif isinstance(parsed, str):
            values = [parsed.strip()] if parsed.strip() else []
        else:
            values = []
        seen: set[str] = set()
        deduped: list[str] = []
        for value in values:
            lowered = value.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(value)
        return deduped

    def _compare(self, query: str, mode: str = "fast") -> dict[str, Any]:
        cleaned = query.strip()
        if not cleaned:
            return {"error": "Query is required", "hint": "Try: compare operator rhythm"}
        package = retrieve_breakdown(cleaned, mode=mode)
        return {
            "query": cleaned,
            "mode": mode,
            "sqlite_hits": package.get("sqlite_hits", []),
            "chroma_hits": package.get("chroma_hits", []),
            "fused_hits": package.get("note_hits", []),
            "best_suppressed_chroma_hit": package.get("best_suppressed_chroma_hit"),
            "dense_diagnostics": package.get("dense_diagnostics", {}),
            "graph_prep_hints": package.get("graph_prep_hints", []),
            "sources_used": package.get("sources_used", []),
        }

    def _build_no_evidence_fallback(
        self,
        query: str,
        package: dict[str, Any],
        *,
        attempted_mode: str,
        escalated: bool = False,
    ) -> dict[str, Any]:
        vector = self._vector_status()
        chunk_count = int(vector.get("chunk_count", 0) or 0)
        sources_used = package.get("sources_used", [])
        rewrite = self._query_rewrite_helper(query)
        if not vector.get("vector_enabled"):
            diagnosis = "Vector cache is disabled, so KAIROS only had sparse/state retrieval to work with."
        elif chunk_count < 250:
            diagnosis = f"Vector cache is enabled but still thin ({chunk_count} chunks), so semantic recall may be weak."
        elif sources_used:
            diagnosis = "KAIROS touched live sources, but none of the matches were strong enough to keep as trustworthy evidence."
        else:
            diagnosis = "Fast retrieval found no trustworthy matches. Weak archive/noise hits were intentionally suppressed instead of being shown as fake evidence."

        if attempted_mode == "fast":
            message = f"No trustworthy evidence yet for '{query}'. {diagnosis}"
            suggested_commands = [
                f"deepen {query}",
                f"compare {query}",
                "show vector status",
            ]
        elif escalated:
            message = f"Deep retrieval still found no trustworthy evidence for '{query}'. {diagnosis}"
            suggested_commands = [
                f"compare {query}",
                "show vector status",
                rewrite["next_hint"],
            ]
        else:
            message = f"No trustworthy evidence found for '{query}'. {diagnosis}"
            suggested_commands = [
                f"compare {query}",
                "show vector status",
                rewrite["next_hint"],
            ]

        return {
            "status": "no_evidence",
            "attempted_mode": attempted_mode,
            "message": message,
            "diagnosis": diagnosis,
            "vector_enabled": bool(vector.get("vector_enabled")),
            "chunk_count": chunk_count,
            "suggested_commands": suggested_commands,
            "auto_escalate": {
                "recommended": attempted_mode == "fast",
                "command": f"deepen {query}" if attempted_mode == "fast" else None,
                "reason": "fast-no-evidence" if attempted_mode == "fast" else "already-deep",
                "max_retries": 1 if attempted_mode == "fast" else 0,
            },
            "rewrite_suggestions": rewrite["suggestions"],
            "suggested_queries": rewrite["queries"],
        }

    def _query_rewrite_helper(self, query: str, limit: int = 5) -> dict[str, Any]:
        query_lower = query.lower()
        tokens = [token for token in re.findall(r"[A-Za-z0-9]+", query_lower) if len(token) >= 3]
        scored: dict[tuple[str, str], dict[str, Any]] = {}
        rewrite_cfg = self._rewrite_cfg()
        configured_title_alias_base = float(rewrite_cfg.get("configured_title_alias_base_score", 7.0) or 7.0)
        configured_folder_alias_base = float(rewrite_cfg.get("configured_folder_alias_base_score", 6.5) or 6.5)
        metadata_alias_base = float(rewrite_cfg.get("metadata_alias_base_score", 6.0) or 6.0)
        title_match_base = float(rewrite_cfg.get("title_match_base_score", 4.0) or 4.0)
        path_match_base = float(rewrite_cfg.get("path_match_base_score", 3.0) or 3.0)
        folder_match_base = float(rewrite_cfg.get("folder_match_base_score", 2.5) or 2.5)
        nearby_alias_folder_base = float(rewrite_cfg.get("nearby_alias_folder_base_score", 1.5) or 1.5)

        def register(kind: str, text: str, score: float, reason: str) -> None:
            cleaned = str(text or "").strip()
            if not cleaned:
                return
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            key = (kind, cleaned.lower())
            current = scored.get(key)
            candidate = {
                "kind": kind,
                "text": cleaned,
                "score": round(score, 3),
                "reason": reason,
            }
            if current is None or candidate["score"] > current["score"]:
                scored[key] = candidate

        def alias_match_score(alias: str) -> float:
            alias_lower = str(alias or "").strip().lower()
            if not alias_lower:
                return 0.0
            alias_tokens = [token for token in re.findall(r"[A-Za-z0-9]+", alias_lower) if len(token) >= 3]
            if alias_lower in query_lower:
                return 3.0 + len(alias_tokens)
            overlap = sum(1 for token in alias_tokens if token in tokens)
            if overlap == 0:
                return 0.0
            if overlap == len(alias_tokens):
                return 2.0 + overlap
            if overlap >= 2 or (overlap == 1 and len(alias_tokens) == 1):
                return 1.0 + overlap
            return 0.0

        for item in rewrite_cfg.get("title_aliases", []) or []:
            title = str(item.get("title") or "").strip()
            aliases = [title, *list(item.get("aliases", []) or [])]
            best = max((alias_match_score(alias) for alias in aliases), default=0.0)
            if best > 0:
                register("note_alias", title, configured_title_alias_base + best, "configured title alias")

        for item in rewrite_cfg.get("folder_aliases", []) or []:
            folder = str(item.get("folder") or "").strip()
            aliases = [folder, *list(item.get("aliases", []) or [])]
            best = max((alias_match_score(alias) for alias in aliases), default=0.0)
            if best > 0:
                register("folder", folder.replace("\\", "/"), configured_folder_alias_base + best, "configured folder alias")

        if self.paths.sqlite_path.exists():
            conn = sqlite3.connect(self.paths.sqlite_path)
            try:
                note_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(notes)").fetchall()}
                select_aliases = ", aliases_json" if "aliases_json" in note_columns else ", '' AS aliases_json"
                rows = conn.execute(
                    f"""
                    SELECT path, title, frontmatter_text, body_excerpt, mtime{select_aliases}
                    FROM notes
                    ORDER BY mtime DESC
                    LIMIT 2500
                    """
                ).fetchall()
            finally:
                conn.close()

            for path, title, frontmatter_text, body_excerpt, mtime, aliases_json in rows:
                path_text = str(path or "")
                title_text = str(title or "")
                title_path_haystack = " ".join([path_text.lower(), title_text.lower()])
                token_matches = sum(1 for token in tokens if token in title_path_haystack)
                metadata_aliases = self._aliases_from_json_blob(aliases_json) or self._aliases_from_frontmatter(frontmatter_text)
                best_metadata_alias = 0.0
                for alias in metadata_aliases:
                    alias_score = alias_match_score(alias)
                    if alias_score > best_metadata_alias:
                        best_metadata_alias = alias_score
                    if alias_score > 0:
                        register(
                            "note_alias",
                            title_text or alias,
                            metadata_alias_base + alias_score,
                            f"note metadata alias: {alias}",
                        )
                if token_matches > 0:
                    register(
                        "note_title",
                        title_text or Path(path_text).stem,
                        title_match_base + token_matches,
                        "nearby note title from SQLite",
                    )
                    register(
                        "note_path",
                        path_text,
                        path_match_base + token_matches,
                        "matching note path from SQLite",
                    )
                    folder = str(Path(path_text).parent).replace("\\", "/").strip(".")
                    if folder:
                        register(
                            "folder",
                            folder,
                            folder_match_base + token_matches,
                            "folder with overlapping terms",
                        )
                elif best_metadata_alias > 0:
                    folder = str(Path(path_text).parent).replace("\\", "/").strip(".")
                    if folder:
                        register(
                            "folder",
                            folder,
                            nearby_alias_folder_base + best_metadata_alias,
                            "folder near note metadata alias",
                        )
                elif not tokens:
                    register("note_title", title_text or Path(path_text).stem, 1.0, "recent note title from SQLite")

        gold_summary_path = self.paths.artifacts_root / "summaries" / "gold_summary.json"
        if gold_summary_path.exists():
            try:
                gold = json.loads(gold_summary_path.read_text(encoding="utf-8"))
            except Exception:
                gold = {}
            for item in gold.get("top_folders", [])[:10]:
                folder = str(item.get("folder") or "").replace("\\", "/")
                if folder in {"", "."}:
                    continue
                score = float(item.get("risk_score", 0.0) or 0.0)
                token_matches = sum(1 for token in tokens if token in folder.lower())
                if token_matches > 0:
                    register("folder", folder, 2.0 + token_matches + (score / 100.0), "folder anchor from Gold summary")
                elif len([item for item in scored.values() if item["kind"] == "folder"]) < 3:
                    register("folder", folder, 1.0 + (score / 100.0), "known folder anchor from Gold summary")

        suggestions = sorted(scored.values(), key=lambda item: (-item["score"], item["text"]))[:limit]
        note_like_kinds = {"note_alias", "note_title", "note_path"}
        best_note_score = max((item["score"] for item in suggestions if item["kind"] in note_like_kinds), default=0.0)
        high_title_score = float(rewrite_cfg.get("high_confidence_title_score", 8.0) or 8.0)
        title_gap = float(rewrite_cfg.get("prefer_titles_over_folders_gap", 3.0) or 3.0)
        max_folder_fallbacks = int(rewrite_cfg.get("max_folder_fallbacks_when_title_confident", 1) or 0)
        if best_note_score >= high_title_score:
            filtered: list[dict[str, Any]] = []
            folder_kept = 0
            for item in suggestions:
                if item["kind"] == "folder":
                    if item["score"] < (best_note_score - title_gap):
                        continue
                    if folder_kept >= max_folder_fallbacks:
                        continue
                    folder_kept += 1
                filtered.append(item)
            suggestions = filtered[:limit]
        queries: list[str] = []
        seen_queries: set[str] = set()
        for item in suggestions:
            if item["kind"] == "folder":
                candidate = f"dig {item['text']}"
            else:
                candidate = f"find {item['text']}"
            lowered = candidate.lower()
            if lowered not in seen_queries:
                queries.append(candidate)
                seen_queries.add(lowered)

        next_hint = "Try a narrower query with a concrete note title, folder, or proper noun."
        if queries:
            next_hint = f"Try one of these corpus-near rewrites: {', '.join(queries[:3])}"

        return {
            "suggestions": suggestions,
            "queries": queries[:limit],
            "next_hint": next_hint,
        }

    def _dig(self, area_hint: str) -> dict[str, Any]:
        from ..orchestration.kairos_directive import KAIROSDirectiveEngine
        engine = KAIROSDirectiveEngine()
        telemetry = engine._load_telemetry()

        # Fuzzy match area
        if area_hint:
            matches = [a for a in telemetry.areas if area_hint.lower() in a.area.lower()]
            if not matches:
                return {"error": f"No area matching '{area_hint}'", "available": [a.area for a in telemetry.areas[:10]]}
            area = matches[0].area
        else:
            # Pick worst area
            worst = sorted(telemetry.areas, key=lambda a: -a.uselessness_score)[0]
            area = worst.area

        return engine.dig_area(area)

    def _train_targets(self, area_hint: str | None) -> dict[str, Any]:
        from ..orchestration.kairos_directive import produce_kairos_directives
        manifest = produce_kairos_directives(cycle=0)
        train_targets = [d for d in manifest.directives if d.action == "train"]

        if area_hint:
            train_targets = [t for t in train_targets if area_hint.lower() in t.area.lower()]

        return {
            "query": area_hint or "all",
            "count": len(train_targets),
            "targets": [
                {
                    "area": t.area,
                    "priority": t.priority,
                    "rationale": t.rationale,
                    "top_candidates": t.commands[:2],
                }
                for t in train_targets
            ],
        }

    def _vault_summary(self) -> dict[str, Any]:
        from ..orchestration.vault_telemetry import run_vault_telemetry
        report = run_vault_telemetry()
        return {
            "ts": now_iso(),
            "overall_uselessness": report.overall_uselessness,
            "overall_training_worth": report.overall_training_worth,
            "high_value_areas": report.high_value_areas,
            "dead_zones": report.dead_zones,
            "dig_targets_count": len(report.dig_targets),
            "train_targets_count": len(report.train_targets),
            "total_areas": len(report.areas),
            "verdict": self._verdict(report),
        }

    def _verdict(self, report) -> str:
        uw = report.overall_uselessness
        tw = report.overall_training_worth
        if uw < 1.0 and tw > 1.5:
            return "Excellent — vault is well-structured with high training potential"
        elif uw < 1.5 and tw > 1.0:
            return "Good — some repair needed but training data is viable"
        elif uw < 2.0:
            return "Fair — targeted repair (frontmatter, scarcity) recommended"
        elif uw < 2.5:
            return "Needs work — significant metadata repair needed before training"
        else:
            return "Critical — systematic repair required across multiple areas"

    def _dead_zones(self) -> dict[str, Any]:
        from ..orchestration.vault_telemetry import run_vault_telemetry
        report = run_vault_telemetry()
        return {
            "dead_zones": report.dead_zones,
            "count": len(report.dead_zones),
            "verdict": "These areas have high uselessness scores — frontmatter + metadata repair will boost overall vault quality significantly",
            "recommendation": "Start with the highest uselessness areas first. Add frontmatter, tags, and wikilinks to reduce orphan ratio.",
        }

    def _directives(self) -> dict[str, Any]:
        from ..orchestration.kairos_directive import KAIROSDirectiveEngine
        engine = KAIROSDirectiveEngine()
        return engine.current_manifest()

    def _folder_quality(self) -> dict[str, Any]:
        from ..orchestration.vault_telemetry import run_vault_telemetry
        report = run_vault_telemetry()
        conn = sqlite3.connect(self.paths.sqlite_path)
        conn.set_trace_callback(None)
        rows = conn.execute(
            "SELECT folder, risk_score, note_count, missing_frontmatter FROM folder_risk ORDER BY risk_score DESC LIMIT 10"
        ).fetchall()
        conn.close()
        return {
            "top_risky_folders": [
                {"folder": r[0], "risk_score": r[1], "note_count": r[2], "missing_frontmatter": r[3]}
                for r in rows
            ],
            "verdict": "Folders sorted by risk score — focus repair on highest scores first",
        }

    def _vector_status(self) -> dict[str, Any]:
        summary_path = self.paths.artifacts_root / "reports" / "vector_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
        return {
            "vector_enabled": bool(summary.get("enabled", False)),
            "chunk_count": int(summary.get("chunk_count", 0) or 0),
            "collection": summary.get("collection", "otto_gold"),
            "note": summary.get("note", "vector summary not found"),
            "store_path": str(self.paths.chroma_path),
            "chroma_python_ready": chromadb is not None,
        }

    def _chunks_for_path(self, note_path: str) -> dict[str, Any]:
        vector_state = self._vector_status()
        if chromadb is None:
            return {"error": "chromadb Python package is not available", "path": note_path}

        collection_name = str(vector_state.get("collection") or "otto_gold")
        try:
            client = chromadb.PersistentClient(path=str(self.paths.chroma_path))
            collection = client.get_or_create_collection(collection_name, metadata={"hnsw:space": "cosine"})
            payload = collection.get(include=["documents", "metadatas"])
        except Exception as exc:
            return {"error": f"Failed to inspect Chroma: {exc}", "path": note_path, "collection": collection_name}

        documents = payload.get("documents") or []
        metadatas = payload.get("metadatas") or []
        target_path = note_path.replace("\\", "/").lower()
        chunks = [
            {"index": idx, "title": (meta or {}).get("title", note_path), "text": (doc or "")[:700]}
            for idx, (doc, meta) in enumerate(zip(documents, metadatas))
            if meta and str(meta.get("path", "")).replace("\\", "/").lower() == target_path
        ]
        return {
            "path": note_path,
            "collection": collection_name,
            "chunk_count": len(chunks),
            "chunks": chunks,
        }

    def _file_analysis(self, path: str) -> dict[str, Any]:
        from ..orchestration.kairos_directive import KAIROSDirectiveEngine
        engine = KAIROSDirectiveEngine()
        return engine.dig_file(path)

    def _date_range(self, date_from: str, date_to: str) -> dict[str, Any]:
        from ..orchestration.kairos_directive import KAIROSDirectiveEngine
        engine = KAIROSDirectiveEngine()
        return engine.dig_date_range(date_from, date_to)

    def _help(self) -> dict[str, Any]:
        return {
            "available_commands": [
                {"command": "dig <folder>", "description": "Deep-dive into folder quality + per-note breakdown + repair recommendations"},
                {"command": "scan", "description": "Full vault telemetry: uselessness score, training worth, dead zones, high-value areas"},
                {"command": "train [on <area>]", "description": "Show training targets — areas with high signal density and good metadata"},
                {"command": "file <path.md>", "description": "Analyze a single note: quality score, missing fields, specific recommendations"},
                {"command": "date YYYY-MM-DD to YYYY-MM-DD", "description": "List all notes modified in a date range"},
                {"command": "what's useless", "description": "Show dead zones — areas with highest uselessness scores"},
                {"command": "what's worth training", "description": "Show areas with highest training worth (signal density + metadata coverage)"},
                {"command": "find <query>", "description": "Hybrid retrieval that auto-deepens once when fast mode finds no trustworthy evidence"},
                {"command": "deepen <query>", "description": "Retry the same query in a wider retrieval mode only when fast retrieval is too weak"},
                {"command": "rewrite guidance", "description": "When KAIROS finds no evidence, it now returns corpus-near rewrite suggestions from SQLite + Gold"},
                {"command": "compare <query>", "description": "Compare sparse SQLite hits vs dense Chroma hits for the same query"},
                {"command": "vector status", "description": "Show vector cache health, chunk count, and Chroma state"},
                {"command": "show chunks for <path.md>", "description": "Inspect vectorized chunks stored for a specific note"},
                {"command": "directives", "description": "Show current KAIROS strategy directives (dig/train/refine actions)"},
                {"command": "folder quality", "description": "Show folder_risk scores from SQLite — sorted by risk score"},
            ],
            "persona": "KAIROS is a top-tier academic data engineer. It thinks critically, identifies systemic patterns, and refines strategies based on evidence.",
            "data_source": "All analysis grounded in SQLite (notes, folder_risk, FTS5), Postgres (vault_signals), and bronze_manifest.json",
        }

    def _extract_target(self, msg: str, prefixes: list[str]) -> str | None:
        for prefix in prefixes:
            if prefix in msg:
                target = msg.split(prefix, 1)[1].strip().rstrip("?.")
                return target
        return None

    def _extract_dates(self, message: str) -> list[str] | None:
        import re
        # Match YYYY-MM-DD patterns
        dates = re.findall(r"\d{4}-\d{2}-\d{2}", message)
        if len(dates) >= 2:
            return [dates[0], dates[1]]
        return None

    def _extract_note_path(self, message: str) -> str | None:
        import re
        cleaned = message.strip()
        lower = cleaned.lower()
        for prefix in [
            "show chunks for ",
            "chunks for ",
            "ambil chunk note ",
            "ambil chunk untuk ",
            "ambil potongan note ",
            "file ",
            "analyze file ",
            "analyze ",
        ]:
            if lower.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                break
        match = re.search(r"([A-Za-z0-9_.\\/:-]+(?: [A-Za-z0-9_.\\/:-]+)*\.md)\b", cleaned)
        if not match:
            return None
        return match.group(1).strip()

    def _hit_reason_summary(self, hit: dict[str, Any]) -> str:
        breakdown = hit.get("score_breakdown", {}) or {}
        reasons: list[str] = []
        if float(breakdown.get("semantic_similarity", 0.0) or 0.0) > 0.0:
            reasons.append("semantic")
        if float(breakdown.get("evidence_support", 0.0) or 0.0) > 0.0:
            reasons.append("evidence")
        if float(breakdown.get("relation_hint_support", 0.0) or 0.0) > 0.0:
            reasons.append("relation hints")
        if not reasons:
            return ""
        relation_matches = hit.get("relation_hint_matches", {}) or {}
        matched_fields = relation_matches.get("matched_fields", []) or []
        if matched_fields:
            return f"{', '.join(reasons)} ({', '.join(matched_fields[:2])})"
        return ", ".join(reasons)

    def _hit_score_line(self, hit: dict[str, Any]) -> str:
        breakdown = hit.get("score_breakdown", {}) or {}
        if not breakdown:
            return ""
        return (
            "s="
            f"{float(breakdown.get('semantic_similarity', 0.0) or 0.0):.3f} "
            "e="
            f"{float(breakdown.get('evidence_support', 0.0) or 0.0):.3f} "
            "r="
            f"{float(breakdown.get('relation_hint_support', 0.0) or 0.0):.3f} "
            "n="
            f"{float(breakdown.get('noise_penalty', 0.0) or 0.0):.3f}"
        )

    def format_telegram(self, result: dict[str, Any]) -> str:
        """Format a KAIROS result as a Telegram-friendly message."""
        if "error" in result:
            out = f"⚠ {result['error']}"
            if result.get("hint"):
                out += f"\n→ {result['hint']}"
            return out

        # vault summary
        if "overall_uselessness" in result:
            uw = result["overall_uselessness"]
            tw = result["overall_training_worth"]
            verdict = result.get("verdict", "")
            dz = result.get("dead_zones", [])
            hv = result.get("high_value_areas", [])
            lines = [
                f"📊 *Vault Telemetry*",
                f"  Uselessness: `{uw:.2f}` (lower=better)",
                f"  Training worth: `{tw:.2f}` (higher=better)",
                f"  Verdict: {verdict}",
            ]
            if dz:
                lines.append(f"  ⚠ Dead zones ({len(dz)}): {', '.join(Path(d).name for d in dz[:3])}")
            if hv:
                lines.append(f"  ✅ High value: {', '.join(Path(h).name for h in hv[:3])}")
            return "\n".join(lines)

        # dig result
        if "telemetry" in result:
            tm = result["telemetry"]
            notes = result.get("note_count", 0)
            lines = [
                f"🔍 *Area: {Path(result['area']).name}*",
                f"  Notes: {notes}",
                f"  Uselessness: `{tm['uselessness_score']:.2f}` | Worth: `{tm['training_worth_score']:.2f}`",
                f"  Frontmatter: {tm['frontmatter_pct']:.0%} | Orphan: {tm['orphan_ratio']:.0%}",
                f"  Priority: *{tm['dig_priority'].upper()}*",
                f"  → {tm['recommendation'][:120]}",
            ]
            return "\n".join(lines)

        # directives
        if "directives" in result:
            directives = result.get("directives", [])
            summary = result.get("summary", {})
            lines = [f"📋 *KAIROS Directives* ({len(directives)} total)"]
            for d in directives[:5]:
                lines.append(f"  [{d['priority'].upper()}] *{d['action']}* {d['area'][:30]}")
                lines.append(f"    → {d['rationale'][:80]}")
            return "\n".join(lines)

        # dead zones
        if "dead_zones" in result and "high_value_areas" not in result:
            dz = result["dead_zones"]
            verdict = result.get("verdict", "")
            lines = [f"☠ *Dead Zones* ({len(dz)} areas)"]
            for z in dz[:5]:
                lines.append(f"  ⚠ {Path(z).name}")
            lines.append(f"\n{verdict}")
            return "\n".join(lines)

        # train targets
        if "targets" in result:
            targets = result["targets"]
            lines = [f"🎯 *Training Targets* ({len(targets)} areas)"]
            for t in targets[:5]:
                lines.append(f"  [{t['priority'].upper()}] *{Path(t['area']).name}*")
                lines.append(f"    → {t['rationale'][:80]}")
            return "\n".join(lines)

        # file analysis
        if "quality_score" in result:
            missing = result.get("missing_fields", [])
            lines = [
                f"📄 *{result['title']}*",
                f"  Quality: `{result['quality_score']:.2f}` | mtime: {result['mtime']}",
            ]
            if missing:
                lines.append(f"  ⚠ Missing: {', '.join(missing)}")
            else:
                lines.append("  ✅ All signal fields present")
            for rec in result.get("recommendations", [])[:3]:
                lines.append(f"  → {rec}")
            return "\n".join(lines)

        if "note_hits" in result and "query" in result:
            lines = [
                f"🔎 *KAIROS Retrieval*",
                f"  Query: `{result['query']}`",
                f"  Sources: {', '.join(result.get('sources_used', [])) or '(none)'}",
            ]
            dense_diagnostics = result.get("dense_diagnostics", {}) or {}
            if dense_diagnostics.get("layer"):
                lines.append("  Dense diagnostics: debug layer")
            gate_counts = dense_diagnostics.get("gate_counts", {}) or {}
            suppressed_reason_counts = dense_diagnostics.get("suppressed_reason_counts", {}) or {}
            technical_rewrite_relaxed_hits = dense_diagnostics.get("technical_rewrite_relaxed_hits", []) or []
            if gate_counts:
                gate_summary = ", ".join(f"{gate}={count}" for gate, count in sorted(gate_counts.items()))
                lines.append(f"  Dense gates: {gate_summary}")
            if suppressed_reason_counts:
                suppressed_summary = ", ".join(f"{reason}={count}" for reason, count in sorted(suppressed_reason_counts.items()))
                lines.append(f"  Dense suppressed: {suppressed_summary}")
            if technical_rewrite_relaxed_hits:
                lines.append("  Technical rewrite kept:")
                for kept in technical_rewrite_relaxed_hits[:2]:
                    lines.append(
                        "    "
                        f"`{kept.get('best_variant', '')}` → "
                        f"`{float(kept.get('distance', 0.0)):.3f}`"
                    )
            if result.get("summary"):
                lines.append(f"  Verdict: {result['summary']}")
            near_miss = result.get("best_suppressed_chroma_hit")
            if near_miss:
                variant = near_miss.get("best_variant") or next(iter(near_miss.get("matched_queries", []) or []), "")
                reason = near_miss.get("reason", "")
                lines.append(
                    "  Chroma near-miss: "
                    f"`{float(near_miss.get('distance', 0.0)):.3f}` "
                    f"{near_miss.get('title', '(untitled)')[:40]}"
                )
                if variant:
                    lines.append(f"    via `{variant}`")
                if reason:
                    lines.append(f"    reason: `{reason}`")
            for hit in result.get("note_hits", [])[:5]:
                title = hit.get("title", "(untitled)")
                path = hit.get("path", "")
                lines.append(f"  → *{title[:40]}*")
                if path:
                    lines.append(f"    `{path}`")
                reason_summary = self._hit_reason_summary(hit)
                if reason_summary:
                    lines.append(f"    why: {reason_summary}")
                score_line = self._hit_score_line(hit)
                if score_line:
                    lines.append(f"    score: {score_line}")
            if not result.get("note_hits"):
                for suggestion in result.get("suggested_commands", [])[:3]:
                    lines.append(f"  → {suggestion}")
                for rewrite in result.get("suggested_queries", [])[:2]:
                    lines.append(f"  ↳ corpus-near: {rewrite}")
            return "\n".join(lines)

        if "fused_hits" in result and "query" in result:
            lines = [
                f"⚖ *Retrieval Compare*",
                f"  Query: `{result['query']}`",
                f"  SQLite hits: {len(result.get('sqlite_hits', []))}",
                f"  Chroma hits: {len(result.get('chroma_hits', []))}",
                f"  Fused hits: {len(result.get('fused_hits', []))}",
            ]
            dense_diagnostics = result.get("dense_diagnostics", {}) or {}
            if dense_diagnostics.get("layer"):
                lines.append("  Dense diagnostics: debug layer")
            gate_counts = dense_diagnostics.get("gate_counts", {}) or {}
            suppressed_reason_counts = dense_diagnostics.get("suppressed_reason_counts", {}) or {}
            technical_rewrite_relaxed_hits = dense_diagnostics.get("technical_rewrite_relaxed_hits", []) or []
            if gate_counts:
                gate_summary = ", ".join(f"{gate}={count}" for gate, count in sorted(gate_counts.items()))
                lines.append(f"  Dense gates: {gate_summary}")
            if suppressed_reason_counts:
                suppressed_summary = ", ".join(f"{reason}={count}" for reason, count in sorted(suppressed_reason_counts.items()))
                lines.append(f"  Dense suppressed: {suppressed_summary}")
            if technical_rewrite_relaxed_hits:
                lines.append("  Technical rewrite kept:")
                for kept in technical_rewrite_relaxed_hits[:2]:
                    lines.append(
                        "    "
                        f"`{kept.get('best_variant', '')}` → "
                        f"`{float(kept.get('distance', 0.0)):.3f}`"
                    )
            near_miss = result.get("best_suppressed_chroma_hit")
            if near_miss:
                variant = near_miss.get("best_variant") or next(iter(near_miss.get("matched_queries", []) or []), "")
                reason = near_miss.get("reason", "")
                lines.append(
                    "  Best suppressed Chroma near-miss: "
                    f"`{float(near_miss.get('distance', 0.0)):.3f}` "
                    f"{near_miss.get('title', '(untitled)')[:40]}"
                )
                if variant:
                    lines.append(f"    via `{variant}`")
                if reason:
                    lines.append(f"    reason: `{reason}`")
            for hit in result.get("fused_hits", [])[:3]:
                title = hit.get("title", hit.get("path", "(untitled)"))
                path = hit.get("path", "")
                lines.append(f"  → *{title[:40]}*")
                if path:
                    lines.append(f"    `{path}`")
                reason_summary = self._hit_reason_summary(hit)
                if reason_summary:
                    lines.append(f"    why: {reason_summary}")
                score_line = self._hit_score_line(hit)
                if score_line:
                    lines.append(f"    score: {score_line}")
            return "\n".join(lines)

        if "vector_enabled" in result and "chunk_count" in result:
            return "\n".join(
                [
                    "🧠 *Vector Status*",
                    f"  Enabled: {result.get('vector_enabled')}",
                    f"  Chunk count: {result.get('chunk_count')}",
                    f"  Collection: {result.get('collection')}",
                    f"  Note: {result.get('note')}",
                ]
            )

        if "chunks" in result and "path" in result:
            lines = [
                f"🧩 *Vector Chunks*",
                f"  Path: `{result.get('path')}`",
                f"  Chunk count: {result.get('chunk_count', 0)}",
            ]
            for chunk in result.get("chunks", [])[:3]:
                lines.append(f"  → chunk {chunk.get('index')}: {chunk.get('text', '')[:90]}")
            return "\n".join(lines)

        # date range
        if "date_from" in result:
            notes = result.get("notes", [])
            lines = [f"📅 *{result['date_from']} → {result['date_to']}* ({len(notes)} notes)"]
            for n in notes[:10]:
                fm = "✓" if n.get("has_frontmatter") else "✗"
                lines.append(f"  [{fm}] {n['title'][:40]} | {n['mtime']}")
            return "\n".join(lines)

        return json.dumps(result, indent=2, ensure_ascii=False)
