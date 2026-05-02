from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    source_id: str
    uri: str
    captured_at: str
    privacy_class: str
    confidence: float
    checksum: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RetrievalHit:
    hit_id: str
    source_id: str
    path: str
    title: str | None
    snippet: str
    score: float | None
    evidence: EvidenceRef

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["evidence_uri"] = self.evidence.uri
        return data
