# Youth Soccer Rankings — Design Spec

**Date:** 2026-06-04
**Status:** Draft for review

## 1. Summary

A modern, free-to-browse web product that publishes credible nationwide rankings of
US youth soccer **teams**, computed from raw public game results. It competes with an
aging iOS app, GotSport's points-based rankings, and elite-only sites like
TopDrawerSoccer by offering an ESPN-quality consumer web experience: fast search,
filterable rankings, SEO-optimized team pages, and team comparison. Rankings are
computed in-house (Glicko-2) from scraped raw match data — never copied from other
sources.

Long-term goal: nationwide coverage and monetization. This spec covers **Phase 1**
(elite-league team rankings) with the architecture deliberately built to expand.

## 2. Goals & Non-Goals

### Goals
- Compute original team ratings from raw, publicly available game results.
- Ship a credible national-elite ranking product fast (lean monolith).
- Be honest about ranking confidence (provisional vs. established).
- Build with a clear path to nationwide coverage and a freemium business model.

### Non-Goals (this phase)
- Player rankings / individual stats (Phase 3 — carries the real monetization upside
  but also minor-privacy/legal weight; out of scope now).
- Copying or re-publishing any third party's computed rankings.
- A distributed scraping/ETL platform (premature — see Architecture).
- Mobile native app.

## 3. Scope & Phasing

Target is **everything nationwide**, reached in phases to manage data sprawl and the
ranking "connectivity" problem (teams must share opponents for cross-region ranking to
be meaningful).

- **Phase 1 — Elite wedge.** ECNL Boys, ECNL Girls, MLS NEXT, Girls Academy (GA).
  These leagues are densely connected (national playoffs, showcases), so rankings are
  statistically sound on day one, and the audience (college-recruiting families) is the
  highest value. Entity ranked: **teams**.
- **Phase 2 — Expand outward.** State/regional competitive leagues, major tournaments
  as inter-region "bridges". Add **club** rankings (aggregate of team ratings — cheap
  once teams exist).
- **Phase 3 — Monetization + players.** Freemium live; begin player-data groundwork
  (requires separate legal review for minors' data).

## 4. Data Sourcing Strategy

**Principle: scrape raw results only, compute our own rankings.** We collect facts
(teams, dates, scores, who-played-whom) from public pages and run our own rating model.
We do not scrape or republish anyone's ranking lists.

### Legal/ToS posture (design constraints, not legal advice)
- Scrape **only public pages**; never log in or scrape account-gated data (avoids
  strong clickwrap-contract and CFAA "unauthorized access" exposure).
- **Do not circumvent** anti-bot measures aggressively. If a source actively blocks
  bots (e.g. leaguetables.soccer returned HTTP 403), back off rather than evade.
- Polite **rate-limiting** and per-source **caching**; behave like a considerate client.
- Compute **our own** ratings from raw facts (facts are not copyrightable; we are not
  copying a protected compilation).
- Attribute sources where reasonable.
- Player data (Phase 3) requires real legal counsel before launch (COPPA / state
  privacy laws — minors).

### Source landscape (verified 2026-06-04)
- **theecnl.com** — SidearmSports platform (`.aspx`); ECNL Boys & Girls schedules,
  scores, standings.
- **mlssoccer.com/mlsnext** — JS-rendered schedule/scores (U13–U19).
- **Girls Academy (GA)** — league site schedule/results.
- **rankings.gotsport.com** — JS-rendered, points-based national rankings U10–U19 B/G.
  Used as a **benchmark to compare our rankings against**, NOT as a data source.
- Note: several key sources are **JavaScript-rendered** and some **actively block
  bots**. The scraper layer therefore needs a **headless browser**, not naive
  HTTP+HTML parsing.

## 5. Architecture

**Lean phased monolith**, single repository:

```
Scrapers (Python + Playwright)
        │  normalized raw results
        ▼
   Postgres  ──►  Ranking engine (nightly Glicko-2 batch)
        │                     │ ratings + confidence
        ▼                     ▼
   Next.js web app  ◄─────────┘
        │
        ▼
   Stripe (accounts/billing scaffolded; premium gated later)
```

Rationale: cheap, fast to ship, easy to reason about; scales to millions of games
before needing a queue/data-lake/microservice split. A full ETL pipeline is where we
*end up* if we win, not where we start.

### Components
1. **Scrapers** — one module per source, common interface, output normalized to a
   shared schema. Playwright-based for JS-rendered sites. Built to fail gracefully and
   **alert when a source's structure breaks** (scraper fragility is the main ongoing
   operational cost). Respect robots/rate limits/blocks.
2. **Data store (Postgres)** — see Data Model.
3. **Ranking engine** — nightly batch; Glicko-2 per (age group × gender) pool; emits
   rating + rating deviation (confidence); flags **provisional** when a team's
   connectivity is thin.
4. **Web app (Next.js)** — rankings tables (filter by age, gender, state, region);
   SEO-optimized team pages (history, schedule, results); team comparison. Free to
   browse.
5. **Monetization hooks** — accounts + Stripe scaffolding from day one; premium
   features (result/schedule alerts, comparison, full history, advanced filters) gated
   in a later phase.

## 6. Data Model (initial)

- **sources** — id, name, base_url, scraper_module, last_run, status.
- **teams** — canonical_id, display_name, club, age_group, gender, state, region.
- **team_aliases** — alias_name, source_id, canonical_team_id. Same team is named
  differently across sources; identity resolution via fuzzy matching + manual override
  is a first-class concern, not an afterthought.
- **games** — id, source_id, date, home_team_id, away_team_id, home_score,
  away_score, competition, raw_payload. De-duplicated across sources.
- **ratings** — team_id, age_group, gender, rating, rating_deviation, volatility,
  is_provisional, computed_at.
- **rating_history** — team_id, rating, computed_at (for trend charts on team pages).

## 7. Ranking Methodology

**Glicko-2** (chosen over plain Elo and over Massey/Colley):
- Tracks a rating **and** a confidence interval, so teams with few or poorly-connected
  games are honestly shown as **provisional** — turning the national connectivity
  weakness into a transparency *feature* competitors lack.
- Handles sparse, uneven schedules better than least-squares methods that assume dense
  connectivity.
- Computed independently per (age group × gender). Season boundaries and roster
  churn handled by rating decay / per-season pools (detail to finalize in plan).
- Tournaments and inter-league play act as connectivity "bridges" enabling
  cross-region comparison.

## 8. Monetization (phased)

- **Phase 1:** all rankings free → SEO + traffic flywheel. (Ads optional later.)
- **Phase 2:** freemium (~$5–15/mo) — team comparison, full history, result/schedule
  alerts, advanced filters, team watching.
- **Phase 3:** claim-your-team / club premium accounts; recruiting tools once player
  data exists; possible data/API licensing to clubs.

## 9. Key Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Scraper fragility (sites change/break) | One module per source, graceful failure, breakage alerts, monitoring. |
| ToS / legal gray area | Public pages only; no login scraping; no anti-bot evasion; compute own rankings; attribute. |
| National connectivity (weak cross-region comparability) | Glicko-2 confidence + provisional flag; lean on tournament/league bridges; phase outward from well-connected elite leagues. |
| Team identity matching across sources | First-class alias table, fuzzy matching, manual override tooling. |
| Anti-bot blocking | Headless browser, polite rate-limits, caching; back off when blocked. |
| Minor-data legal exposure (Phase 3) | Defer player data; obtain legal counsel before that phase. |

## 10. Success Criteria (Phase 1)

- Original team ratings published for ECNL B/G + MLS NEXT + GA across all their age
  groups.
- Rankings track sensibly against GotSport's benchmark where overlap exists, while
  defensibly diverging based on our own model.
- Team pages indexable by search engines (SEO).
- Scraper breakage is detected and alerted, not silently wrong.
- Architecture supports adding a new source by writing a single scraper module.

## 11. Open Questions (for implementation plan)

- Exact season/roster handling in Glicko-2 (decay vs. discrete seasonal pools).
- Margin-of-victory weighting (cap to avoid rewarding blowouts).
- **Hosting: Replit.** Web app on an Autoscale Deployment; Postgres via Replit's
  built-in (Neon-backed) database; nightly Glicko-2 batch via a Scheduled Deployment.
  Open: Playwright scrapers are resource-heavy — decide between Scheduled Deployment vs.
  a Reserved VM (always-on) for scraping jobs.
- Identity-resolution UX for manual alias overrides.
- **Identity candidate scoping (Plan 1 code review):** `best_match` uses
  `token_set_ratio`, which matches abbreviated names against longer canonical names well
  but can over-match across age groups (shared tokens, e.g. "...2010 Boys" vs
  "...2012 Boys"). The scraper (Plan 2) MUST pre-filter candidates to the same
  age_group/gender pool before calling `best_match`.
- **`Rating` denormalization (raised in Plan 1 code review):** `Rating` carries its own
  `age_group`/`gender` (duplicated from `Team`), making the unique constraint
  `(team_id, age_group, gender)` effectively `(team_id)`. Decide in the Ranking Engine
  plan whether to keep this denormalization (self-contained ratings per pool) or derive
  age/gender from `Team` and simplify the constraint.
