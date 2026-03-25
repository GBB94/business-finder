# IdeaScope Data Source Connectors — Compliance Reference

## Automated Connectors (API-compliant)

### Reddit
- **Method**: Official API via OAuth2
- **Rate limits**: 100 requests/minute per OAuth client ID
- **Terms**: Compliant with Reddit API Terms of Use
- **Data retention**: Store post IDs + metadata only; content summarized, not cached verbatim
- **Last verified**: 2026-03-25

#### Reddit Data API -- Discovery Scanner
- **Status**: Personal/non-commercial use (free tier, 100 QPM per OAuth client ID)
- **CRITICAL**: Commercial use (any monetized product or added users) requires a contract with Reddit. Pricing negotiated, not publicly listed. Re-evaluate before any productization milestone.
- **Deletion compliance**: CandidateSourcePost records are checked by reddit_purge.py and fully purged when source posts are deleted. When last source post is purged, derived fields (evidence_summary, spending_signals, raw_themes) are nulled on the CandidateIdea.

### Hacker News (HN)
- **Method**: Official Firebase API (public, no auth)
- **Rate limits**: None published; use polite crawling (~1 req/sec)
- **Terms**: Public API, no TOS restrictions on read access
- **Data retention**: Store item IDs + metadata
- **Last verified**: 2026-03-03

### GitHub
- **Method**: REST API v3 / GraphQL v4 (PAT or OAuth)
- **Rate limits**: 5,000 requests/hour (authenticated)
- **Terms**: Compliant with GitHub API Terms
- **Data retention**: Store repo metadata + star/issue counts
- **Last verified**: 2026-03-03

### Stripe
- **Method**: Official Stripe SDK (API key auth)
- **Terms**: Compliant — reading own account data
- **Data retention**: Financial metrics only; no PII stored externally
- **Last verified**: 2026-03-03

## Manual-Entry Only (no scraping)

### G2
- **Method**: Manual entry via UI form
- **Reason**: No public API; scraping violates TOS
- **Data captured**: Review counts, ratings, competitor comparisons (user-entered)

### Capterra
- **Method**: Manual entry via UI form
- **Reason**: No public API; scraping violates TOS
- **Data captured**: Category rankings, review summaries (user-entered)

### Google Keyword Planner
- **Method**: Manual entry via UI form
- **Reason**: Requires Google Ads account; API access complex for MVP
- **Data captured**: Search volume, CPC, competition level (user-entered)

### Ubersuggest
- **Method**: Manual entry via UI form
- **Reason**: No public API
- **Data captured**: Keyword difficulty, volume estimates (user-entered)

### Product Hunt
- **Method**: Manual entry via UI form
- **Reason**: API deprecated / limited
- **Data captured**: Launch metrics, upvotes, comments (user-entered)

### App Stores (iOS / Google Play)
- **Method**: Manual entry via UI form
- **Reason**: Scraping violates TOS
- **Data captured**: Ratings, review counts, category rankings (user-entered)
