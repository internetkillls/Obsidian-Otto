from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from urllib.parse import unquote, urlparse
from html import unescape
from html.parser import HTMLParser
from dataclasses import asdict, dataclass, field
from typing import Any

import requests

from ..config import load_env_file, load_paths, repo_root
from ..logging_utils import append_jsonl
from ..state import now_iso, write_json


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return cleaned[:80] or "topic"


def _json_fragment(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _extract_hits(container: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if isinstance(container, dict):
        for key, value in container.items():
            if key in {"results", "items", "organic", "documents", "hits"} and isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        candidates.append(item)
            else:
                candidates.extend(_extract_hits(value))
    elif isinstance(container, list):
        for item in container:
            candidates.extend(_extract_hits(item))
    return candidates


def _extract_text(container: Any) -> str:
    if isinstance(container, str):
        return container.strip()
    if isinstance(container, dict):
        for key in ("markdown", "content", "text", "body", "html"):
            value = container.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for value in container.values():
            text = _extract_text(value)
            if text:
                return text
    if isinstance(container, list):
        for item in container:
            text = _extract_text(item)
            if text:
                return text
    return ""


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        elif tag in {"p", "div", "section", "article", "main", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        elif tag in {"p", "div", "section", "article", "main", "li", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self.parts.append(text)

    def text(self) -> str:
        joined = " ".join(self.parts)
        joined = re.sub(r"\s*\n\s*", "\n", joined)
        joined = re.sub(r"\n{3,}", "\n\n", joined)
        joined = re.sub(r"[ \t]{2,}", " ", joined)
        return unescape(joined).strip()


@dataclass
class ResearchTopic:
    topic: str
    topic_class: str
    priority: str
    source_tiers: list[str]
    needs_freshness_check: bool = False
    effect_size_required: bool = False


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str
    source: str | None = None


@dataclass
class FetchedDocument:
    url: str
    ok: bool
    title: str | None = None
    preview: str | None = None
    provider: str | None = None
    error: str | None = None


def _ddg_scrape_search(query: str, limit: int = 6) -> tuple[list[SearchHit], list[str]]:
    """Fallback: scrape DuckDuckGo HTML directly when OpenClaw search fails."""
    warnings: list[str] = []
    hits: list[SearchHit] = []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Otto/0.1; +https://github.com/internetkillls/obsidian-otto)",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.5",
        }
        params = {"q": query, "kl": "wt-wt"}
        resp = requests.get(
            "https://html.duckduckgo.com/html/",
            params=params,
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        body = resp.text or ""

        # Parse DuckDuckGo HTML result blocks: <a class="result__a" href="URL">Title</a>
        # and <a class="result__snippet" href="...">snippet text</a>
        link_pattern = re.compile(
            r'<a class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )
        snippet_pattern = re.compile(
            r'<a class="result__snippet"[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )

        seen_urls: set[str] = set()
        # Collect links first
        link_data: dict[str, str] = {}
        for match in link_pattern.finditer(body):
            url = match.group(1).strip()
            if not url or url in seen_urls or url.startswith("/"):
                continue
            seen_urls.add(url)
            title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            title = unescape(title).strip()
            if title:
                link_data[url] = title

        # Collect snippets (may come after link, try to match by proximity)
        snippet_map: dict[str, str] = {}
        for match in snippet_pattern.finditer(body):
            snippet = re.sub(r"<[^>]+>", "", match.group(1)).strip()
            snippet = unescape(snippet).strip()
            if snippet:
                # Associate with last seen URL (approximate but functional)
                if link_data:
                    last_url = next(iter(reversed(list(link_data.keys()))))
                    snippet_map[last_url] = snippet

        for url, title in list(link_data.items())[:limit]:
            snippet = snippet_map.get(url, "")
            if snippet:
                snippet = snippet[:300]
            hits.append(SearchHit(
                title=title or url,
                url=url,
                snippet=snippet,
                source="duckduckgo",
            ))
        if not hits:
            warnings.append("DuckDuckGo HTML returned no parseable results")
    except requests.RequestException as exc:
        warnings.append(f"DuckDuckGo HTML fallback failed: {exc}")
    return hits, warnings


@dataclass
class ResearchRun:
    ts: str
    approved: bool
    budget_reason: str
    fetch_cycles: int
    topic: ResearchTopic
    hypothesis: str
    search_query: str
    search_provider: str | None = None
    fetch_provider: str | None = None
    search_ok: bool = False
    fetch_ok: bool = False
    search_hits: list[SearchHit] = field(default_factory=list)
    fetched_documents: list[FetchedDocument] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cache_path: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "approved": self.approved,
            "budget_reason": self.budget_reason,
            "fetch_cycles": self.fetch_cycles,
            "topic": asdict(self.topic),
            "hypothesis": self.hypothesis,
            "search_query": self.search_query,
            "search_provider": self.search_provider,
            "fetch_provider": self.fetch_provider,
            "search_ok": self.search_ok,
            "fetch_ok": self.fetch_ok,
            "search_hits": [asdict(hit) for hit in self.search_hits],
            "fetched_documents": [asdict(doc) for doc in self.fetched_documents],
            "warnings": self.warnings,
            "cache_path": self.cache_path,
        }


class OpenClawResearchEngine:
    SOURCE_TABLE = {
        "real_pain": (["Reddit", "GitHub Issues"], False, False),
        "academic_theory": (["arXiv", "PLOS ONE", "ACM OA"], False, False),
        "systems": (["expert blogs", "documentation", "conference proceedings"], False, False),
        "economics": (["SSRN", "NBER", "FT", "Bloomberg"], True, False),
        "career": (["LinkedIn Pulse", "expert blogs", "case studies"], True, False),
        "wellbeing": (["PubMed OA", "APA OA", "Cochrane"], False, True),
        "orientation": (["Wikipedia", "Tier 1 corroboration required"], False, False),
    }

    def __init__(self) -> None:
        self.paths = load_paths()
        self.repo_env = load_env_file(repo_root() / ".env")
        self.openclaw_path = shutil.which("openclaw")

    def classify_topic(self, text: str) -> str:
        lowered = text.lower()
        if any(word in lowered for word in ["bug", "issue", "pain", "lived", "experience"]):
            return "real_pain"
        if any(word in lowered for word in ["economic", "market", "pricing", "income"]):
            return "economics"
        if "career" in lowered:
            return "career"
        if any(word in lowered for word in ["metadata", "governance", "execution", "workflow", "frontmatter", "retrieval", "system"]):
            return "systems"
        if any(word in lowered for word in ["wellbeing", "psychology", "sleep", "stress"]):
            return "wellbeing"
        if any(word in lowered for word in ["model", "epistemic", "theory", "research"]):
            return "academic_theory"
        return "orientation"

    def _validate_hypothesis(self, topic_text: str, hypothesis: str) -> tuple[bool, str]:
        text = topic_text.strip()
        hypo = hypothesis.strip()
        if len(text.split()) < 4:
            return False, "topic too vague for a bounded fetch sequence"
        if len(hypo.split()) < 8:
            return False, "hypothesis too thin to justify research cycles"
        if not any(term in hypo.lower() for term in ["clarify", "test", "compare", "disconfirm", "determine", "bound"]):
            return False, "hypothesis lacks an explicit decision or test shape"
        return True, "hypothesis validated"

    def budget_guard(self, topic_text: str, priority: str) -> tuple[bool, str, int]:
        if priority == "high":
            return True, "High-priority gap justifies immediate Tier 1/Tier 2 research", 2
        if len(topic_text.split()) >= 8:
            return True, "Topic is specific enough for a bounded review-first fetch", 1
        return False, "Marginal utility is unclear; refine the hypothesis before spending fetch cycles", 0

    def wikipedia_auto_tag(self, citation: str) -> str:
        if "wikipedia" in citation.lower() and "cross-reference with Tier 1 sources" not in citation.lower():
            return f"⚠️ [{citation} — cross-reference with Tier 1 sources]"
        return citation

    def _extract_wikipedia_title(self, url: str) -> str | None:
        parsed = urlparse(url)
        path = parsed.path or ""
        if "/wiki/" in path:
            title = path.split("/wiki/", 1)[1]
        elif "/page/summary/" in path:
            title = path.rsplit("/page/summary/", 1)[-1]
        else:
            title = path.rsplit("/", 1)[-1]
        title = unquote(title).strip()
        return title or None

    def _fetch_wikipedia_summary(self, url: str) -> FetchedDocument:
        title = self._extract_wikipedia_title(url)
        if not title:
            return FetchedDocument(url=url, ok=False, provider="wikipedia-api", error="could not extract wikipedia title")
        api_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(title, safe='')}"
        try:
            resp = requests.get(
                api_url,
                timeout=20,
                headers={"Accept": "application/json", "User-Agent": "Obsidian-Otto/0.1 (+wikipedia api)"},
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            return FetchedDocument(url=url, ok=False, provider="wikipedia-api", error=str(exc)[:500])
        extract = str(payload.get("extract") or payload.get("description") or "").strip()
        thumbnail = payload.get("thumbnail") if isinstance(payload, dict) else None
        preview = extract[:1200] if extract else None
        if thumbnail and isinstance(thumbnail, dict) and thumbnail.get("source"):
            preview = f"{preview or ''}\nThumbnail: {thumbnail.get('source')}".strip()
        return FetchedDocument(
            url=url,
            ok=bool(extract),
            title=str(payload.get("title") or title).strip() if isinstance(payload, dict) else title,
            preview=preview,
            provider="wikipedia-api",
            error=None if extract else "wikipedia summary missing extract",
        )

    def _env_value(self, key: str) -> str | None:
        return os.environ.get(key) or self.repo_env.get(key)

    def _search_provider_candidates(self) -> list[str]:
        providers: list[str] = []
        if self._env_value("BRAVE_API_KEY"):
            providers.append("brave")
        providers.append("duckduckgo")
        if self._env_value("PERPLEXITY_API_KEY") or self._env_value("OPENROUTER_API_KEY"):
            providers.append("perplexity")
        if self._env_value("TAVILY_API_KEY"):
            providers.append("tavily")
        if self._env_value("EXA_API_KEY"):
            providers.append("exa")
        return providers

    def _fetch_provider(self) -> str | None:
        if self._env_value("FIRECRAWL_API_KEY"):
            return "firecrawl"
        return None

    def _local_fetch_one(self, url: str) -> FetchedDocument:
        try:
            response = requests.get(
                url,
                timeout=20,
                headers={
                    "User-Agent": "Obsidian-Otto/0.1 (+local fetch fallback; requests)",
                    "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
                },
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            return FetchedDocument(url=url, ok=False, provider="python-requests", error=str(exc)[:500])

        content_type = (response.headers.get("content-type") or "").lower()
        body = response.text or ""
        title_match = re.search(r"<title[^>]*>(.*?)</title>", body, flags=re.IGNORECASE | re.DOTALL)
        title = unescape(title_match.group(1)).strip() if title_match else None

        if "html" in content_type or "<html" in body.lower():
            extractor = _HTMLTextExtractor()
            try:
                extractor.feed(body)
                preview = extractor.text()[:1200] or None
            except Exception as exc:
                return FetchedDocument(
                    url=url,
                    ok=False,
                    provider="python-requests",
                    title=title,
                    error=f"html_parse_failed: {exc}"[:500],
                )
        else:
            preview = body.strip()[:1200] or None

        return FetchedDocument(
            url=url,
            ok=True,
            title=title,
            preview=preview,
            provider="python-requests",
        )

    def _run_openclaw(self, args: list[str], *, timeout_seconds: int = 90) -> tuple[bool, dict[str, Any] | None, str]:
        if not self.openclaw_path:
            return False, None, "openclaw executable not found on PATH"
        try:
            proc = subprocess.run(
                [self.openclaw_path, *args],
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            timeout_output = "\n".join(part for part in [exc.stdout, exc.stderr] if part).strip()
            return False, _json_fragment(timeout_output), f"openclaw timed out after {timeout_seconds}s"
        output_text = "\n".join(part for part in [proc.stdout, proc.stderr] if part).strip()
        payload = _json_fragment(proc.stdout or "") or _json_fragment(output_text)
        if proc.returncode == 0 and payload is not None:
            return True, payload, output_text
        error_text = output_text or f"openclaw exited with code {proc.returncode}"
        return False, payload, error_text

    def _search_query(self, topic: ResearchTopic, hypothesis: str) -> str:
        hints = {
            "real_pain": "site:reddit.com OR site:github.com/issues",
            "academic_theory": "site:arxiv.org OR site:plos.org OR site:acm.org",
            "systems": "site:acm.org OR site:arxiv.org OR site:plos.org",
            "economics": "site:ssrn.com OR site:nber.org OR site:ft.com OR site:bloomberg.com",
            "career": "site:linkedin.com OR expert blog case study",
            "wellbeing": "site:pubmed.ncbi.nlm.nih.gov OR site:plos.org",
            "orientation": "overview deep dive",
        }
        return f"{topic.topic} {hints.get(topic.topic_class, '')} {hypothesis}".strip()

    def _priority_source_tiers(self, topic: ResearchTopic) -> list[str]:
        tiers = list(topic.source_tiers)
        if topic.topic_class in {"academic_theory", "systems", "wellbeing"}:
            enforced = [tier for tier in ["arXiv", "PLOS ONE", "ACM OA"] if tier not in tiers]
            tiers = enforced + tiers
        if topic.topic_class == "orientation":
            tiers = [tier for tier in tiers if tier != "Wikipedia"] + ["Wikipedia"]
        return tiers

    def _parse_search_hits(self, payload: dict[str, Any]) -> tuple[list[SearchHit], list[str]]:
        warnings: list[str] = []
        outputs = payload.get("outputs")
        if isinstance(outputs, list):
            for output in outputs:
                result = output.get("result") if isinstance(output, dict) else None
                if isinstance(result, dict) and result.get("error"):
                    warnings.append(str(result.get("message") or result["error"]))
        hits: list[SearchHit] = []
        seen_urls: set[str] = set()
        for item in _extract_hits(payload):
            url = str(item.get("url") or item.get("link") or item.get("href") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            title = str(item.get("title") or item.get("name") or url).strip()
            snippet = str(
                item.get("snippet") or item.get("description") or item.get("body") or item.get("text") or ""
            ).strip()
            source = item.get("source") or item.get("domain")
            hits.append(SearchHit(title=title, url=self.wikipedia_auto_tag(url), snippet=snippet[:400], source=source))
        return hits, warnings

    def _fetch_one(self, url: str, provider: str) -> FetchedDocument:
        ok, payload, error_text = self._run_openclaw(
            ["infer", "web", "fetch", "--json", "--provider", provider, "--url", url],
            timeout_seconds=120,
        )
        if not ok or payload is None:
            return FetchedDocument(url=url, ok=False, provider=provider, error=error_text[:500])
        title = None
        outputs = payload.get("outputs")
        if isinstance(outputs, list):
            for output in outputs:
                result = output.get("result") if isinstance(output, dict) else None
                if isinstance(result, dict):
                    title = result.get("title") or title
                    if result.get("error"):
                        return FetchedDocument(
                            url=url,
                            ok=False,
                            provider=provider,
                            error=str(result.get("message") or result["error"])[:500],
                        )
        preview = _extract_text(payload)[:1200] or None
        return FetchedDocument(
            url=url,
            ok=True,
            title=str(title).strip() if title else None,
            preview=preview,
            provider=provider,
        )

    def execute(self, *, topic_text: str, priority: str = "medium") -> ResearchRun:
        topic_class = self.classify_topic(topic_text)
        source_tiers, freshness, effect_size = self.SOURCE_TABLE[topic_class]
        approved, reason, cycles = self.budget_guard(topic_text, priority)
        topic = ResearchTopic(
            topic=topic_text,
            topic_class=topic_class,
            priority=priority,
            source_tiers=source_tiers,
            needs_freshness_check=freshness,
            effect_size_required=effect_size,
        )
        hypothesis = f"Research should clarify the highest-leverage decision behind: {topic_text}"
        hypothesis_ok, hypothesis_reason = self._validate_hypothesis(topic_text, hypothesis)
        if not hypothesis_ok:
            approved = False
            reason = hypothesis_reason
        search_query = self._search_query(topic, hypothesis)
        run = ResearchRun(
            ts=now_iso(),
            approved=approved,
            budget_reason=reason,
            fetch_cycles=min(max(cycles, 1), 3) if approved else 0,
            topic=topic,
            hypothesis=hypothesis,
            search_query=search_query,
        )
        if not hypothesis_ok:
            run.warnings.append(hypothesis_reason)
            append_jsonl(self.paths.state_root / "run_journal" / "openclaw_fetches.jsonl", run.as_dict())
            return run
        if not approved:
            run.warnings.append("Budget guard rejected this query before OpenClaw execution.")
            append_jsonl(self.paths.state_root / "run_journal" / "openclaw_fetches.jsonl", run.as_dict())
            return run

        if not self.openclaw_path:
            run.warnings.append("OpenClaw CLI is not available on PATH.")
            append_jsonl(self.paths.state_root / "run_journal" / "openclaw_fetches.jsonl", run.as_dict())
            return run

        search_errors: list[str] = []
        search_payload: dict[str, Any] | None = None

        # Try OpenClaw search providers first
        for provider in self._search_provider_candidates():
            ok, payload, output_text = self._run_openclaw(
                ["infer", "web", "search", "--json", "--provider", provider, "--limit", str(max(run.fetch_cycles, 1) * 3), "--query", search_query]
            )
            if ok and payload is not None:
                run.search_provider = provider
                search_payload = payload
                break
            search_errors.append(f"openclaw/{provider}: {output_text[:300]}")

        # Fallback: if all OpenClaw providers fail, scrape DuckDuckGo HTML directly
        if search_payload is None:
            ddg_hits, ddg_warnings = _ddg_scrape_search(search_query, limit=max(run.fetch_cycles, 1) * 3)
            if ddg_hits:
                run.search_provider = "duckduckgo-html"
                run.search_ok = True
                run.search_hits = ddg_hits
                run.warnings.append(f"OpenClaw search failed — used DuckDuckGo HTML fallback: {ddg_warnings[0] if ddg_warnings else 'ok'}")
                run.warnings.extend(ddg_warnings)
            else:
                run.warnings.extend(ddg_warnings)
                run.warnings.extend(search_errors or ["OpenClaw search returned no payload and DDG fallback returned no results."])
            cache_data = {"run": run.as_dict(), "search_payload": None, "fetch_payloads": {}}
            cache_path = self.paths.state_root / "openclaw" / "research" / f"{run.ts[:10]}-{_slugify(topic_text)}.json"
            write_json(cache_path, cache_data)
            run.cache_path = str(cache_path)
            append_jsonl(self.paths.state_root / "run_journal" / "openclaw_fetches.jsonl", run.as_dict())
            return run

        hits, warnings = self._parse_search_hits(search_payload)
        run.search_ok = bool(hits)
        prioritized_tiers = self._priority_source_tiers(topic)
        run.search_hits = hits[: max(run.fetch_cycles, 1) * 3]
        run.search_hits.sort(
            key=lambda hit: 0 if any(tier.lower() in (hit.source or "").lower() or tier.lower() in hit.url.lower() for tier in prioritized_tiers[:3]) else 1
        )
        run.warnings.extend(warnings)
        if not run.search_ok and search_errors:
            run.warnings.extend(search_errors)

        fetch_payloads: dict[str, Any] = {}
        fetch_provider = self._fetch_provider()
        run.fetch_provider = fetch_provider or "python-requests"
        for hit in run.search_hits[: run.fetch_cycles]:
            if "wikipedia" in hit.url.lower() or "wikipedia" in (hit.source or "").lower():
                wikipedia_doc = self._fetch_wikipedia_summary(hit.url)
                run.fetched_documents.append(wikipedia_doc)
                fetch_payloads[hit.url] = asdict(wikipedia_doc)
                run.warnings.append(f"Wikipedia summary fetched via REST API, cross-reference with Tier 1 sources: {hit.url}")
                continue
            if fetch_provider:
                document = self._fetch_one(hit.url, fetch_provider)
            else:
                document = self._local_fetch_one(hit.url)
                if not run.warnings or "OpenClaw web.fetch provider is not configured" not in run.warnings:
                    run.warnings.append("OpenClaw web.fetch provider is not configured; using local Python fetch fallback.")
            run.fetched_documents.append(document)
            fetch_payloads[hit.url] = asdict(document)
        run.fetch_ok = any(doc.ok for doc in run.fetched_documents)

        cache_data = {
            "run": run.as_dict(),
            "search_payload": search_payload,
            "fetch_payloads": fetch_payloads,
        }
        cache_path = self.paths.state_root / "openclaw" / "research" / f"{run.ts[:10]}-{_slugify(topic_text)}.json"
        write_json(cache_path, cache_data)
        run.cache_path = str(cache_path)
        append_jsonl(self.paths.state_root / "run_journal" / "openclaw_fetches.jsonl", run.as_dict())
        return run


def build_research_plan(*, topic_text: str, priority: str = "medium") -> dict[str, Any]:
    """Plan-only layer: classify topic + source strategy without live fetch."""
    engine = OpenClawResearchEngine()
    topic_class = engine.classify_topic(topic_text)
    source_tiers, freshness, effect_size = engine.SOURCE_TABLE[topic_class]
    approved, reason, cycles = engine.budget_guard(topic_text, priority)
    topic = ResearchTopic(
        topic=topic_text,
        topic_class=topic_class,
        priority=priority,
        source_tiers=source_tiers,
        needs_freshness_check=freshness,
        effect_size_required=effect_size,
    )
    hypothesis = f"Research should clarify the highest-leverage decision behind: {topic_text}"
    query = engine._search_query(topic, hypothesis)
    plan = {
        "ts": now_iso(),
        "topic": topic_text,
        "topic_class": topic_class,
        "priority": priority,
        "approved": approved,
        "budget_reason": reason,
        "planned_cycles": min(max(cycles, 0), 3),
        "source_tiers": source_tiers,
        "needs_freshness_check": freshness,
        "effect_size_required": effect_size,
        "search_query": query,
        "hypothesis": hypothesis,
        "plan_only": True,
        "fetch_executed": False,
    }
    append_jsonl(engine.paths.state_root / "run_journal" / "research_plans.jsonl", plan)
    write_json(engine.paths.state_root / "openclaw" / "research_latest_plan.json", plan)
    return plan
