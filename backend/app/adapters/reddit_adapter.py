from __future__ import annotations

import asyncio
import logging
import time

import httpx

from app.adapters.base import RawPost, SourceAdapter
from app.config import settings

logger = logging.getLogger(__name__)

_MOCK_POSTS: list[dict] = [
    {
        "id": "mock_r1",
        "subreddit": "SaaS",
        "title": "What tools are you using for pricing page A/B tests?",
        "selftext": "We're a small SaaS startup trying to optimize our pricing page. Currently testing manually but it's painful. Looking for recommendations.",
        "score": 87,
        "num_comments": 34,
        "created_utc": time.time() - 86400 * 3,
        "permalink": "/r/SaaS/comments/mock_r1/what_tools_pricing/",
    },
    {
        "id": "mock_r2",
        "subreddit": "indiehackers",
        "title": "I spent 6 months building a product nobody wanted — here's what I learned",
        "selftext": "Classic mistake: I built what I thought was cool instead of talking to customers first. Spent $3k on ads before realizing the problem wasn't painful enough. Lesson: validate before you build.",
        "score": 234,
        "num_comments": 67,
        "created_utc": time.time() - 86400 * 7,
        "permalink": "/r/indiehackers/comments/mock_r2/spent_6_months/",
    },
    {
        "id": "mock_r3",
        "subreddit": "startups",
        "title": "How do you validate ideas before writing code?",
        "selftext": "Tired of building MVPs that go nowhere. What's your process for validating a startup idea? Landing pages? Reddit posts? Cold emails? Would love to hear what actually works.",
        "score": 156,
        "num_comments": 89,
        "created_utc": time.time() - 86400 * 2,
        "permalink": "/r/startups/comments/mock_r3/validate_ideas/",
    },
    {
        "id": "mock_r4",
        "subreddit": "Entrepreneur",
        "title": "The 'build in public' trend is overrated — change my mind",
        "selftext": "Everyone says build in public, but I've seen more people get copied than get customers from it. Am I wrong? What's your actual experience with building in public?",
        "score": 312,
        "num_comments": 145,
        "created_utc": time.time() - 86400 * 5,
        "permalink": "/r/Entrepreneur/comments/mock_r4/build_in_public/",
    },
    {
        "id": "mock_r5",
        "subreddit": "SaaS",
        "title": "What metrics do you track in the first 30 days after launch?",
        "selftext": "Just launched my SaaS and I'm overwhelmed by all the analytics tools. What are the 3-5 metrics that actually matter early on? Activation rate? Time to value? MRR feels premature.",
        "score": 98,
        "num_comments": 42,
        "created_utc": time.time() - 86400,
        "permalink": "/r/SaaS/comments/mock_r5/metrics_first_30_days/",
    },
    {
        "id": "mock_r6",
        "subreddit": "microsaas",
        "title": "Is $29/mo too cheap? Struggling with SaaS pricing",
        "selftext": "My tool saves small businesses about 5 hours/week on invoicing. Currently charging $29/mo and getting good conversion but wondering if I'm leaving money on the table. Users seem to love it.",
        "score": 67,
        "num_comments": 28,
        "created_utc": time.time() - 86400 * 4,
        "permalink": "/r/microsaas/comments/mock_r6/pricing_too_cheap/",
    },
    {
        "id": "mock_r7",
        "subreddit": "startups",
        "title": "Killed my startup after 14 months — AMA",
        "selftext": "Built a competitor research tool. Got to $800 MRR but couldn't get past it. Churn was 12% monthly. Decided to shut it down and try something new. Happy to share learnings.",
        "score": 445,
        "num_comments": 203,
        "created_utc": time.time() - 86400 * 6,
        "permalink": "/r/startups/comments/mock_r7/killed_startup_ama/",
    },
]


class RedditAdapter(SourceAdapter):
    source_type = "reddit"

    def __init__(self) -> None:
        self._use_mock = not settings.REDDIT_CLIENT_ID
        self._token: str | None = None
        self._token_expires: float = 0

    async def _authenticate(self, client: httpx.AsyncClient) -> str:
        if self._token and time.time() < self._token_expires:
            return self._token

        resp = await client.post(
            "https://www.reddit.com/api/v1/access_token",
            data={"grant_type": "client_credentials"},
            auth=(settings.REDDIT_CLIENT_ID, settings.REDDIT_CLIENT_SECRET),
            headers={"User-Agent": settings.REDDIT_USER_AGENT},
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expires = time.time() + data.get("expires_in", 3600) - 60
        return self._token

    async def search(self, queries: list[str], limit: int = 25) -> list[RawPost]:
        if self._use_mock:
            return self._mock_search(queries, limit)
        return await self._live_search(queries, limit)

    def _mock_search(self, queries: list[str], limit: int) -> list[RawPost]:
        query_lower = " ".join(queries).lower()
        posts = []
        for mock in _MOCK_POSTS:
            text = f"{mock['title']} {mock['selftext']}".lower()
            if any(q.lower() in text for q in queries) or not queries:
                posts.append(self._to_raw_post(mock))
            if len(posts) >= limit:
                break
        # If no query matches, return all mocks up to limit
        if not posts:
            posts = [self._to_raw_post(m) for m in _MOCK_POSTS[:limit]]
        return posts

    async def _live_search(self, queries: list[str], limit: int) -> list[RawPost]:
        posts: list[RawPost] = []
        seen_ids: set[str] = set()
        per_query = max(1, limit // len(queries)) if queries else limit

        async with httpx.AsyncClient(timeout=15.0) as client:
            token = await self._authenticate(client)

            for i, query in enumerate(queries):
                if i > 0:
                    await asyncio.sleep(1.0)
                try:
                    resp = await client.get(
                        "https://oauth.reddit.com/search",
                        params={
                            "q": query,
                            "sort": "relevance",
                            "t": "month",
                            "limit": per_query,
                            "type": "link",
                        },
                        headers={
                            "Authorization": f"Bearer {token}",
                            "User-Agent": settings.REDDIT_USER_AGENT,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    for child in data.get("data", {}).get("children", []):
                        post = child.get("data", {})
                        pid = post.get("id", "")
                        if pid in seen_ids:
                            continue
                        seen_ids.add(pid)
                        posts.append(
                            RawPost(
                                source_id=pid,
                                source_type="reddit",
                                source_url=f"https://reddit.com{post.get('permalink', '')}",
                                title=post.get("title", ""),
                                body=(post.get("selftext", "") or "")[:3000],
                                score=post.get("score", 0),
                                comment_count=post.get("num_comments", 0),
                                subreddit=post.get("subreddit", ""),
                                created_utc=post.get("created_utc", 0),
                            )
                        )
                except Exception:
                    logger.exception("Reddit search failed for query=%s", query)

        return posts[:limit]

    @staticmethod
    def _to_raw_post(mock: dict) -> RawPost:
        return RawPost(
            source_id=mock["id"],
            source_type="reddit",
            source_url=f"https://reddit.com{mock['permalink']}",
            title=mock["title"],
            body=mock["selftext"],
            score=mock["score"],
            comment_count=mock["num_comments"],
            subreddit=mock["subreddit"],
            created_utc=mock["created_utc"],
        )
