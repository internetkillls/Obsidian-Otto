from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SongSeed:
    context_anchors: list[str]
    existential_atoms: list[str]


def parse_song_seed(text: str, *, min_anchors: int = 1, max_anchors: int = 3) -> SongSeed:
    anchors: list[str] = []
    atoms: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            anchors.append(line[1:].strip())
        elif line.startswith("@"):
            atoms.append(line[1:].strip())
    if len(anchors) < min_anchors:
        raise ValueError("song_seed_requires_context_anchor")
    if len(anchors) > max_anchors:
        raise ValueError("song_seed_context_anchor_limit_exceeded")
    if not atoms:
        raise ValueError("song_seed_requires_existential_atom")
    return SongSeed(context_anchors=anchors, existential_atoms=atoms)
