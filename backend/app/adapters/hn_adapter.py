from __future__ import annotations

import asyncio
import logging

import httpx

from app.adapters.base import RawPost, SourceAdapter

logger = logging.getLogger(__name__)

ALGOLIA_SEARCH_URL = "https://hn.algolia.com/api/v1/search"


class HNAdapter(SourceAdapter):
    source_type = "hn"

    # Algolia tag values for each watchlist source_type
    TAG_MAP: dict[str, str] = {
        "hn_ask": "ask_hn",
        "hn_show": "show_hn",
        "hn_tag": "story",
    }

    def __init__(self) -> None:
        self._rate_delay = 1.0  # seconds between requests

    async def search(self, queries: list[str], limit: int = 25, tags: str = "story") -> list[RawPost]:
        posts: list[RawPost] = []
        seen_ids: set[str] = set()
        per_query = max(1, limit // len(queries)) if queries else limit

        async with httpx.AsyncClient(timeout=15.0) as client:
            for i, query in enumerate(queries):
                if i > 0:
                    await asyncio.sleep(self._rate_delay)
                try:
                    resp = await client.get(
                        ALGOLIA_SEARCH_URL,
                        params={
                            "query": query,
                            "tags": tags,
                            "hitsPerPage": per_query,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    for hit in data.get("hits", []):
                        obj_id = hit.get("objectID", "")
                        if obj_id in seen_ids:
                            continue
                        seen_ids.add(obj_id)

                        body_parts = []
                        if hit.get("story_text"):
                            body_parts.append(hit["story_text"])
                        if hit.get("url"):
                            body_parts.append(hit["url"])
                        body = "\n".join(body_parts)[:3000]

                        posts.append(
                            RawPost(
                                source_id=obj_id,
                                source_type="hn",
                                source_url=f"https://news.ycombinator.com/item?id={obj_id}",
                                title=hit.get("title", ""),
                                body=body,
                                score=hit.get("points", 0) or 0,
                                comment_count=hit.get("num_comments", 0) or 0,
                                subreddit=None,
                                created_utc=hit.get("created_at_i", 0),
                            )
                        )
                except Exception:
                    logger.exception("HN search failed for query=%s", query)

        return posts[:limit]
