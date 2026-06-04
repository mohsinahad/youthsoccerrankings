# ECNL Scraper (Plan 2) — Design Spec

**Date:** 2026-06-04
**Status:** Draft for review
**Depends on:** Plan 1 (Foundation & Data Layer) — uses `ysr.models`, `ysr.db`, `ysr.identity`.

## 1. Summary

The first data source: a scraper that ingests **one ECNL division end-to-end** —
teams and completed games — into the Postgres data layer, on demand and idempotently.
This proves the full scrape → normalize → resolve-identity → upsert pipeline so that
adding more divisions/sources later is iteration, not new architecture. We compute our
own rankings, so the scraper collects **raw completed game results and team identities
only** — not standings (derived later) and not future fixtures (YAGNI).

## 2. Goals & Non-Goals

### Goals
- Fetch one ECNL division's schedule/results from Total Global Sports (TGS).
- Normalize to typed records; resolve each team to a canonical `Team` (creating
  `Team` + `TeamAlias` on first sight, reusing on subsequent runs).
- Upsert completed games idempotently on the `(source, date, home, away)` unique key,
  preserving the original payload in `games.raw_payload`.
- Provide a runnable CLI command to ingest a division on demand.
- Be testable without network access (parse + ingest tested against a committed fixture).

### Non-Goals (this plan)
- Scheduled/automated runs (manual command now; Replit scheduling is a thin later step).
- Standings ingestion (we derive rankings ourselves).
- Future/unplayed fixtures.
- Multiple divisions or other sources (one division proves the pipeline).
- Player-level data.

## 3. Data Source: Total Global Sports (TGS)

ECNL's schedules/standings are powered by **Total Global Sports**, which runs a public
React site (`public.totalglobalsports.com`) and a mobile app, both backed by a JSON API
(an AWS API Gateway endpoint). Direct anonymous fetches from a simple client returned
HTTP 403, indicating bot protection / required browser-like request headers — but the
data is public (no login). The exact endpoints, headers, and JSON shape are confirmed by
the discovery spike (§7, Task 0) before building.

### Legal/ToS posture (carried from product spec §4)
Public endpoints only; no login/account-gated data; browser-like headers are acceptable
but **do not aggressively circumvent anti-bot measures** — back off if hard-blocked.
Polite rate-limiting and caching. We compute our own rankings from raw facts.

## 4. Fetch Strategy

**JSON API first, Playwright fallback.** Primary path: call the TGS JSON API with
`httpx` and browser-like headers, rate-limited and retried. Fallback (only if the spike
shows the API is unreachable without a browser): drive Playwright to render the SPA and
capture its API responses. **Parsing and ingestion are identical either way** — only the
fetch layer differs — so a fallback does not ripple through the design.

## 5. Architecture & Components

Data flow: `fetch (TGS JSON) → parse (pure) → list[ScrapedGame] → ingest (resolve teams
+ upsert games) → Postgres`.

Separation of concerns: **fetch (I/O) is isolated from parse (pure)** so parsing is unit-
tested against a committed fixture with no network; **ingest** keeps pure mapping logic
separable from the DB session at the edge.

New files:
- `src/ysr/scrapers/__init__.py`
- `src/ysr/scrapers/base.py` — typed records `ScrapedTeam`, `ScrapedGame` (frozen
  dataclasses) and a `Scraper` interface (Protocol) describing `fetch()`/`parse()`.
- `src/ysr/scrapers/http.py` — thin `httpx`-based client: browser-like headers, polite
  rate-limiting (configurable delay), bounded retries with backoff. The I/O edge.
- `src/ysr/scrapers/ecnl.py` — `fetch_division(...)` (hits TGS via the http client) and
  `parse_division(payload) -> list[ScrapedGame]` (pure). The fetch/parse split lives here.
- `src/ysr/ingest.py` — `ingest_games(session, source, games, age_group, gender)`:
  get-or-create the ECNL `Source`; resolve each team name via `identity.best_match`
  against candidates **pre-filtered to the division's age_group + gender**; create
  `Team` + `TeamAlias` on first sight; upsert `Game` rows.
- `src/ysr/cli.py` — argument parsing and command wiring.
- `pyproject.toml` — add a `[project.scripts]` console entry: `ysr-scrape = "ysr.cli:main"`.

## 6. Key Behaviors

- **Completed-only:** ingest a game only when both scores are present; skip unplayed.
- **Team identity:** the division fixes `age_group` + `gender`, so identity candidates
  are scoped to that pool before fuzzy matching (honors product-spec caveat about
  `token_set_ratio` over-matching across age groups). First sighting creates a `Team`
  (with parsed club/age/gender) and a `TeamAlias(alias_name=scraped name, source=ECNL)`;
  later sightings match the alias and reuse the `Team`.
- **Idempotent upsert:** keyed on `(source_id, date, home_team_id, away_team_id)`. Insert
  if absent; if present and the score changed (e.g. a result posted later), update
  `home_score`/`away_score`/`raw_payload`. Re-running never duplicates.
- **Source row:** get-or-create a single `Source(name="ECNL", ...)`.
- **Fail loudly:** missing/renamed expected fields raise a clear error naming the event/
  division — never silently ingest partial/garbage data. (Automated alerting deferred to
  the scheduling step; a non-zero exit + clear log is sufficient for a manual command.)
- **Config, not hardcoding:** TGS event/division identifiers and the division's
  age_group/gender come from CLI args.

## 7. Implementation Phasing (informs the plan)

- **Task 0 — Discovery spike (throwaway):** confirm the TGS endpoint(s), required
  headers, and JSON shape for one event; capture a real (trimmed) response and commit it
  as the parser test fixture. Decide JSON-API vs Playwright fetch. De-risks before build.
- Then: `base.py` records → `parse_division` (TDD against fixture) → `http.py` client →
  `fetch_division` → `ingest.py` (TDD against in-memory SQLite) → `cli.py` + console
  script → a manual end-to-end run against the live division.

## 8. Testing

- **Parser:** committed trimmed TGS JSON fixture → `parse_division` yields the expected
  `ScrapedGame` list (including correct handling of unplayed games being excluded).
- **Ingest (in-memory SQLite):** fresh DB + fixture → correct `Team`/`TeamAlias`/`Game`
  rows; run again → no duplicate games + a changed score is updated; two age groups of
  the same club are not conflated (identity scoping).
- **Live fetch:** a separate, manually-run / CI-skippable integration check; unit tests
  never hit the live API.

## 9. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| TGS API needs a browser / hard bot-block | Spike confirms first; Playwright fallback isolated to the fetch layer. |
| TGS JSON shape changes | Parse fails loudly; fixture-based tests catch regressions; one module to fix. |
| Team-name variants across runs/divisions | Alias table + scoped `token_set_ratio` matching; first-sight create, then reuse. |
| Late-posted/corrected scores | Upsert updates score + raw_payload on the unique key. |
| Over-aggressive requests | Rate-limit + retry/backoff in the http client; back off on hard blocks. |

## 10. Success Criteria

- `ysr-scrape ecnl --event <id> ...` ingests one real ECNL division's teams + completed
  games into the DB.
- Running it twice produces no duplicate games and updates any changed scores.
- Parser and ingest are covered by fixture-based tests (no network); `mypy --strict`
  clean; the live fetch is verified once manually.
- Adding a second division is a config/argument change, not a code change.

## 11. Open Questions (for the plan / resolved during spike)

- Exact TGS endpoint paths, required headers, and pagination (if any) — resolved by the
  spike and encoded in `fetch_division`.
- How club vs. team name is represented in TGS data (for populating `Team.club` /
  `Team.display_name`) — resolved by inspecting the spike's real payload.
- Whether age_group/gender can be derived from the TGS event metadata or must be passed
  as CLI args — default to CLI args; use event metadata if cleanly available.
