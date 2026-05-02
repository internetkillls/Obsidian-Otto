from __future__ import annotations


def scout_sources(topic: str) -> list[dict[str, str]]:
    return [
        {"kind": "university_press_book", "query": f"{topic} university press introduction"},
        {"kind": "review_article", "query": f"{topic} review article"},
        {"kind": "syllabus", "query": f"{topic} university syllabus"},
    ]
