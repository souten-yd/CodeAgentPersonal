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
