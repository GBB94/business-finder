from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RawPost:
    source_id: str
    source_type: str
    source_url: str
    title: str
    body: str
    score: int
    comment_count: int
    subreddit: str | None
    created_utc: float


class SourceAdapter(ABC):
    source_type: str

    @abstractmethod
    async def search(self, queries: list[str], limit: int = 25) -> list[RawPost]:
        ...
