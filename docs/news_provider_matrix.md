# News Provider Matrix

PR4.68c adds a shared no-key News Source layer for Nexus Deep Research, Nexus News MVP, and Lumen lightweight news digest.

| provider | key required | default | usage |
|---|---:|---:|---|
| GDELT DOC 2.0 | no | yes | news source / Nexus evidence |
| SearXNG | no | yes | fallback / local metasearch |
| RSS CNBC | no | yes if reachable | RSS summary only |
| RSS Yahoo!ニュース | no | local/personal only | personal use only, no redistribution |

## Rights and safety defaults

- Public GDELT DOC 2.0 is treated as a no-key metadata/search endpoint, distinct from GDELT Cloud Pro/Enterprise API key products.
- SearXNG is a no-key local/metasearch fallback when `SEARXNG_URL` or `SEARXNG_ENDPOINT` is configured.
- RSS providers are limited to `title`, `link`, `pubDate`, and `description`; article full-text scraping is not performed.
- CNBC RSS defaults to `personal_use_only=false`, `allow_public_redistribution=false`, and `full_text_allowed=false`.
- Yahoo!ニュース RSS defaults to `personal_use_only=true`, `allow_public_redistribution=false`, and `full_text_allowed=false`.
- The default provider list must not include API-key-required providers such as Guardian, Currents, NewsData, or Mediastack.

## Source diversity

The connector layer normalizes URLs, deduplicates repeated `source_domain`/title combinations, applies simple title dedupe, and caps concentration so one provider should not dominate the default selected set and one domain is limited before deferred fill.

## PR4.68c-fix2 status semantics and Runpod smoke diagnostics

`overall_status` is shared by Lumen News, Nexus News MVP, and Deep Research with `source_profile="news"`:

- `ok`: at least one final news item is available and no provider reports failures, skips, or missing endpoints.
- `degraded`: at least one final news item is available, but one or more providers report `error_count > 0`, `skipped=true`, or `endpoint_configured=false`.
- `failed`: no final news items are available, or all providers are failed/skipped/no-result providers.

`provider_status.ok` is true only when that provider returned at least one item, has zero errors, was not skipped, and has an endpoint configured. A successful query with zero matching articles keeps `errors=[]` but reports `ok=false` so runtime smoke checks can distinguish "reachable but no result" from provider failure.

Runpod smoke checks before API splitting:

- Verify Google News RSS can return headline/summary metadata.
- Verify Yahoo RSS can return headline/summary metadata and keeps `personal_use_only=true`.
- Verify CNBC RSS can return headline/summary metadata.
- Verify BBC RSS can return headline/summary metadata.
- Verify NHK is reported as `skipped=true` while its URL remains unvalidated or disabled.
- Verify SearXNG without `SEARXNG_URL`/`SEARXNG_ENDPOINT` reports `endpoint_configured=false` without failing the entire run.
- Verify a run with zero final items returns `overall_status="failed"`.
- Verify a run with items plus a failed/skipped/missing-endpoint provider returns `overall_status="degraded"`.
- Verify news evidence metadata keeps `full_text_scraped=false`; this layer must not fetch article full text or bypass paywalls.
