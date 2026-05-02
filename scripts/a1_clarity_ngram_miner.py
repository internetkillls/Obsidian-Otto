from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any

from _active_scope import is_active_scope
from _scarcity_common import now_iso, read_note_metadata, split_frontmatter, write_json

TOKEN_RE = re.compile(r"[a-z0-9]+")
FOLDER_10_90_RE = re.compile(r"^(?:[1-8][0-9]|90)(?:$|[^0-9].*)")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _tokenize_line(text: str, block_words: set[str], go_words: set[str]) -> list[str]:
    out: list[str] = []
    for token in TOKEN_RE.findall(text.lower()):
        if token in go_words:
            out.append(token)
            continue
        if len(token) < 3:
            continue
        if token in block_words:
            continue
        out.append(token)
    return out


def _line_ngrams(tokens: list[str]) -> set[str]:
    grams: set[str] = set()
    for i in range(len(tokens) - 1):
        grams.add(f"{tokens[i]} {tokens[i + 1]}")
    for i in range(len(tokens) - 2):
        grams.add(f"{tokens[i]} {tokens[i + 1]} {tokens[i + 2]}")
    return grams


def _score_note(text: str, meta: dict[str, Any], cfg: dict[str, Any]) -> tuple[float, int, int]:
    score = 0.0
    lowered = text.lower()
    marker_hits = 0
    anti_hits = 0
    for marker in cfg.get("clarity_markers", []):
        marker_l = str(marker).strip().lower()
        if marker_l and marker_l in lowered:
            marker_hits += 1
            score += 1.0
    for marker in cfg.get("anti_markers", []):
        marker_l = str(marker).strip().lower()
        if marker_l and marker_l in lowered:
            anti_hits += 1
            score -= 1.0
    necessity = meta.get("necessity")
    if isinstance(necessity, (int, float)):
        score += 0.25 * float(necessity)
    artificial = meta.get("artificial")
    if isinstance(artificial, (int, float)):
        score += 0.1 * (1.0 - float(artificial))
    if meta.get("scarcity"):
        score += 0.1
    return score, marker_hits, anti_hits


def _normalize_words(values: list[Any]) -> set[str]:
    out: set[str] = set()
    for value in values:
        w = str(value).strip().lower()
        if w:
            out.add(w)
    return out


def _enumerate_notes(vault: Path, scope: str) -> list[Path]:
    candidates: list[Path] = []
    for note in vault.rglob("*.md"):
        try:
            rel = note.relative_to(vault)
        except ValueError:
            continue
        if not rel.parts:
            continue
        top = rel.parts[0]
        if not FOLDER_10_90_RE.match(top):
            continue
        if scope == "active" and not is_active_scope(note, vault):
            continue
        if scope == "full" and any(part in {"state", "tests", ".obsidian", ".git", ".trash", ".venv"} for part in note.parts):
            continue
        candidates.append(note)
    candidates.sort(key=lambda p: str(p.relative_to(vault)).lower())
    return candidates


def _pick_batch(notes: list[Path], start_idx: int, batch_size: int) -> tuple[list[Path], int]:
    if not notes:
        return [], 0
    start = start_idx % len(notes)
    take = min(batch_size, len(notes))
    selected = [notes[(start + i) % len(notes)] for i in range(take)]
    next_index = (start + take) % len(notes)
    return selected, next_index


def _append_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _build_file_index(vault: Path, notes: list[Path]) -> dict[str, dict[str, int]]:
    index: dict[str, dict[str, int]] = {}
    for note in notes:
        rel = str(note.relative_to(vault)).replace("\\", "/")
        stat = note.stat()
        index[rel] = {"mtime_ns": int(stat.st_mtime_ns), "size": int(stat.st_size)}
    return index


def _delta_files(
    prev_index: dict[str, dict[str, int]],
    curr_index: dict[str, dict[str, int]],
) -> tuple[list[str], list[str], list[str]]:
    prev_keys = set(prev_index.keys())
    curr_keys = set(curr_index.keys())
    added = sorted(curr_keys - prev_keys)
    removed = sorted(prev_keys - curr_keys)
    changed = sorted(
        k
        for k in (curr_keys & prev_keys)
        if curr_index.get(k, {}).get("mtime_ns") != prev_index.get(k, {}).get("mtime_ns")
        or curr_index.get(k, {}).get("size") != prev_index.get(k, {}).get("size")
    )
    return added, removed, changed


def main() -> int:
    parser = argparse.ArgumentParser(description="A-lane bi/trigram miner for clarity and insight anchors")
    parser.add_argument("--vault", default="")
    parser.add_argument("--scope", choices=["active", "full"], default="active")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--config", default="config/clarity_ngram_miner.json")
    parser.add_argument("--noise-config", default="config/graph_shaper_noise_words.json")
    parser.add_argument("--counts-output", default="state/openclaw/clarity_ngram_counts.json")
    parser.add_argument("--profile-output", default="state/openclaw/clarity_ngram_profile.json")
    parser.add_argument("--cursor-output", default="state/openclaw/clarity_ngram_cursor.json")
    parser.add_argument("--file-index-output", default="state/openclaw/clarity_ngram_file_index.json")
    parser.add_argument("--handoff-dir", default="state/handoff/from_cowork")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--apply-go-words", action="store_true")
    args = parser.parse_args()

    repo = _repo_root()
    vault = Path(args.vault).expanduser().resolve() if args.vault else Path(
        os.environ.get("OTTO_VAULT_PATH", str(repo))
    ).expanduser().resolve()
    if not vault.exists() or not vault.is_dir():
        raise SystemExit(f"Vault path is not a directory: {vault}")

    cfg_path = (repo / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    noise_path = (repo / args.noise_config).resolve() if not Path(args.noise_config).is_absolute() else Path(args.noise_config)
    counts_path = (repo / args.counts_output).resolve() if not Path(args.counts_output).is_absolute() else Path(args.counts_output)
    profile_path = (repo / args.profile_output).resolve() if not Path(args.profile_output).is_absolute() else Path(args.profile_output)
    cursor_path = (repo / args.cursor_output).resolve() if not Path(args.cursor_output).is_absolute() else Path(args.cursor_output)
    file_index_path = (repo / args.file_index_output).resolve() if not Path(args.file_index_output).is_absolute() else Path(args.file_index_output)
    handoff_dir = (repo / args.handoff_dir).resolve() if not Path(args.handoff_dir).is_absolute() else Path(args.handoff_dir)

    default_cfg = {
        "version": "1.0",
        "clarity_markers": ["clarity", "insight", "aha", "jernih", "nyambung", "paham", "breakthrough"],
        "anti_markers": ["bingung", "acak", "ngawur", "stuck", "confused"],
        "positive_threshold": 1.2,
        "negative_threshold": -0.2,
        "require_marker_for_positive": True,
        "min_pos_df": 2,
        "min_score": 0.7,
        "top_k_phrases": 80,
        "top_k_go_words": 40,
        "max_age_runs": 60,
    }
    cfg = _load_json(cfg_path, default_cfg)
    if not cfg_path.exists():
        write_json(cfg_path, cfg)

    noise_cfg = _load_json(noise_path, {"version": "1.0", "custom_stopwords": [], "noise_words": [], "go_words": []})
    block_words = _normalize_words((noise_cfg.get("common_stopwords") or [])) | _normalize_words((noise_cfg.get("custom_stopwords") or [])) | _normalize_words((noise_cfg.get("noise_words") or []))
    go_words = _normalize_words((noise_cfg.get("go_words") or []))
    block_words = {w for w in block_words if w and w not in go_words}

    cursor = _load_json(cursor_path, {"run_count": 0, "note_count": 0})
    run_count = int(cursor.get("run_count", 0)) + 1
    notes = _enumerate_notes(vault, args.scope)
    curr_index = _build_file_index(vault, notes)
    prev_index_payload = _load_json(file_index_path, {"files": {}})
    prev_index = prev_index_payload.get("files", {}) if isinstance(prev_index_payload, dict) else {}
    added, removed, changed = _delta_files(prev_index, curr_index)
    has_delta = bool(added or removed or changed)

    if (not has_delta) and (not args.force):
        prev_profile = _load_json(profile_path, {})
        if not isinstance(prev_profile, dict):
            prev_profile = {}
        profile = {
            **prev_profile,
            "ts": now_iso(),
            "run_count": run_count,
            "scope": args.scope,
            "status": "no_delta_skip",
            "note_count_total": len(notes),
            "delta": {"added": 0, "removed": 0, "changed": 0},
            "noise_config_path": str(noise_path),
        }
        write_json(profile_path, profile)
        write_json(cursor_path, {"ts": now_iso(), "run_count": run_count, "note_count": len(notes)})
        write_json(file_index_path, {"ts": now_iso(), "files": curr_index})
        summary = {
            "ts": profile["ts"],
            "run_count": run_count,
            "status": "no_delta_skip",
            "note_count_total": len(notes),
            "profile": str(profile_path),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    batch = notes
    next_index = 0

    ngram_counts: dict[str, dict[str, Any]] = {}

    pos_threshold = float(cfg.get("positive_threshold", 1.2))
    neg_threshold = float(cfg.get("negative_threshold", -0.2))
    require_marker = bool(cfg.get("require_marker_for_positive", True))
    pos_notes = 0
    neg_notes = 0
    neutral_notes = 0
    sampled: list[dict[str, Any]] = []

    for note_path in batch:
        rel = str(note_path.relative_to(vault))
        text = note_path.read_text(encoding="utf-8", errors="replace")
        _, body = split_frontmatter(text)
        meta = read_note_metadata(note_path, vault)
        title = note_path.stem
        signal_score, marker_hits, anti_hits = _score_note(f"{title}\n{body}", meta, cfg)
        label = "neutral"
        if signal_score >= pos_threshold and (not require_marker or marker_hits > 0):
            label = "positive"
            pos_notes += 1
        elif signal_score <= neg_threshold:
            label = "negative"
            neg_notes += 1
        else:
            neutral_notes += 1

        sampled.append(
            {
                "note": rel,
                "score": round(signal_score, 3),
                "label": label,
                "marker_hits": marker_hits,
                "anti_hits": anti_hits,
            }
        )
        if label == "neutral":
            continue

        note_ngrams: set[str] = set()
        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            tokens = _tokenize_line(line, block_words, go_words)
            note_ngrams |= _line_ngrams(tokens)
        for gram in note_ngrams:
            row = ngram_counts.get(gram) or {"pos_df": 0, "neg_df": 0, "total_df": 0, "last_seen_run": 0}
            if label == "positive":
                row["pos_df"] = int(row.get("pos_df", 0)) + 1
            else:
                row["neg_df"] = int(row.get("neg_df", 0)) + 1
            row["total_df"] = int(row.get("total_df", 0)) + 1
            row["last_seen_run"] = run_count
            ngram_counts[gram] = row

    min_pos_df = int(cfg.get("min_pos_df", 2))
    min_score = float(cfg.get("min_score", 0.7))
    ranked: list[dict[str, Any]] = []
    for gram, row in ngram_counts.items():
        pos_df = int(row.get("pos_df", 0))
        neg_df = int(row.get("neg_df", 0))
        if pos_df < min_pos_df:
            continue
        purity = pos_df / max(1, pos_df + neg_df)
        strength = math.log1p(pos_df)
        score = purity * strength
        if score < min_score:
            continue
        ranked.append({
            "phrase": gram,
            "pos_df": pos_df,
            "neg_df": neg_df,
            "score": round(score, 4),
            "purity": round(purity, 4),
            "n": 2 if gram.count(" ") == 1 else 3,
        })
    ranked.sort(key=lambda x: (x["score"], x["pos_df"]), reverse=True)

    top_k_phrases = int(cfg.get("top_k_phrases", 80))
    top_k_go_words = int(cfg.get("top_k_go_words", 40))
    top_phrases = ranked[:top_k_phrases]
    token_score: dict[str, float] = {}
    for item in top_phrases:
        for token in item["phrase"].split():
            if token in block_words:
                continue
            token_score[token] = token_score.get(token, 0.0) + float(item["score"])
    go_word_candidates = sorted(
        [{"word": token, "score": round(score, 4)} for token, score in token_score.items()],
        key=lambda x: x["score"],
        reverse=True,
    )[:top_k_go_words]

    if args.apply_go_words:
        merged_go = set(go_words)
        for item in go_word_candidates:
            merged_go.add(item["word"])
        noise_cfg["go_words"] = sorted(merged_go)
        write_json(noise_path, noise_cfg)

    counts_payload = {"ts": now_iso(), "run_count": run_count, "ngrams": ngram_counts}
    write_json(counts_path, counts_payload)
    write_json(cursor_path, {"ts": now_iso(), "next_index": next_index, "run_count": run_count, "note_count": len(notes)})
    write_json(file_index_path, {"ts": now_iso(), "files": curr_index})

    profile = {
        "ts": now_iso(),
        "run_count": run_count,
        "scope": args.scope,
        "note_count_total": len(notes),
        "note_count_batch": len(batch),
        "delta": {"added": len(added), "removed": len(removed), "changed": len(changed)},
        "labels": {"positive": pos_notes, "negative": neg_notes, "neutral": neutral_notes},
        "top_phrase_anchors": top_phrases,
        "go_word_candidates": go_word_candidates,
        "noise_config_path": str(noise_path),
        "sampled_notes": sampled[:30],
    }
    write_json(profile_path, profile)

    stamp = now_iso().replace("-", "").replace(":", "").replace("+", "").split(".")[0][:13]
    bridge = {
        "source": "cowork-otto-a",
        "role": "a",
        "status": "handoff",
        "updated_at": now_iso(),
        "summary": (
            f"A clarity miner run={run_count}; batch={len(batch)}/{len(notes)}; "
            f"positive={pos_notes}; anchors={len(top_phrases)}; go_candidates={len(go_word_candidates)}"
        ),
        "artifacts": [str(profile_path), str(counts_path)],
        "next_actions": [
            "B: review top phrase anchors before auto-apply",
            "C: use go_words for graph-shaper semantic anchor",
        ],
        "next_action": "B: review top phrase anchors before auto-apply",
        "language": "id",
    }
    handoff_file = handoff_dir / f"{stamp}_a_handoff.json"
    write_json(handoff_file, bridge)
    _append_json(handoff_dir / "a_clarity_miner.jsonl", bridge)

    summary = {
        "ts": profile["ts"],
        "run_count": run_count,
        "batch": len(batch),
        "total": len(notes),
        "delta": {"added": len(added), "removed": len(removed), "changed": len(changed)},
        "positive": pos_notes,
        "negative": neg_notes,
        "neutral": neutral_notes,
        "anchors": len(top_phrases),
        "go_word_candidates": len(go_word_candidates),
        "profile": str(profile_path),
        "handoff": str(handoff_file),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
