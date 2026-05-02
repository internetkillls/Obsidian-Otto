from __future__ import annotations


def artifact_affinities(text: str) -> dict[str, float]:
    lowered = text.lower()
    paper = 0.35 + 0.2 * sum(token in lowered for token in ["paper", "research", "theory", "seminar", "critique"])
    song = 0.2 + 0.2 * sum(token in lowered for token in ["song", "lyric", "chord", "melody"])
    prose = 0.25 + 0.15 * sum(token in lowered for token in ["essay", "prose", "paragraph", "voice"])
    return {
        "artifact_affinity_song": min(song, 0.98),
        "artifact_affinity_paper": min(paper, 0.98),
        "artifact_affinity_prose": min(prose, 0.98),
    }
