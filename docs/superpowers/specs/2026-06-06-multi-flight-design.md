# Multi-Flight Ingestion (Plan 4) — Design Spec

**Date:** 2026-06-06
**Status:** Draft for review
**Depends on:** Plans 1–3 (scraper + hardening), Plan 5 (ranking).

## 1. Summary

Turn the ECNL scraper from "one flight per command" into "one **event** per command."
`ysr-scrape ecnl --event <id>` fetches the event's division/flight tree and ingests every
active flight, **auto-deriving** each flight's `age_group` and `gender` (no manual args).
This is what fills the live site with real breadth — a single event spans many flights
across several age/gender pools.

## 2. Goals & Non-Goals

### Goals
- Ingest all active flights in an event in one run.
- Derive `gender` (boys/girls list) and `age_group` (`U##` from the flight name) per flight.
- Per-flight error isolation: one bad flight is logged and skipped, the rest proceed.
- Aggregate, report counts (flights ingested/failed, games, teams).
- Keep a single-flight escape hatch (`--flight <id>`).

### Non-Goals
- Multiple events per run, or scheduling/automation.
- New sources (MLS NEXT/GA) — separate work.
- Changing the parse/ingest internals (reused unchanged).
- Backfilling historical seasons.

## 3. Data Source (confirmed)

`GET /api/Event/get-event-schedule-or-standings/{eventID}` →
`data.boysDivAndFlightList` and `data.girlsDivAndFlightList`. Each division has a
`flightList`; each flight has `flightID`, `flightName` (e.g. `"U12 (2013) Pre-ECNL North - 9v9"`),
`hasActiveSchedule`, `teamsCount`. Games per flight come from the existing
`get-schedules-by-flight/{event}/{flight}/0` endpoint.

**Derivation:**
- `gender`: `M` for flights under `boysDivAndFlightList`, `F` for `girlsDivAndFlightList`.
- `age_group`: first `U(\d+)` match in `flightName` (→ `"U12"`). A flight whose name has no
  `U##` is skipped and logged (never guessed).
- Only flights with `hasActiveSchedule == true` are ingested.

## 4. New / Changed Code

**`src/ysr/scrapers/ecnl.py`:**
- `@dataclass(frozen=True) FlightRef(flight_id: int, age_group: str, gender: str, name: str)`.
- `parse_event_flights(tree: dict) -> list[FlightRef]` — pure. Walks both lists, derives
  age/gender, filters to active + parseable; logs+skips unparseable names.
- `fetch_event_tree(client: HttpClient, *, event_id: int) -> dict` — GETs the tree endpoint
  (with the same `result == "success"` envelope check as `fetch_division`).
- `fetch_division` / `parse_division` unchanged (used per flight).

**`src/ysr/cli.py`:** rework the `ecnl` subcommand:
- Args: `--event <int>` (required), `--flight <int>` (optional). **Remove** `--age-group`
  and `--gender`.
- Flow: schema pre-check → get-or-create source → commit → fetch event tree → derive
  `FlightRef`s (filtered to `--flight` if given) → for each flight, inside a per-flight
  `try/except`: `fetch_division` → `parse_division` → `ingest_games(..., age_group, gender)`
  from the `FlightRef`; tally. A flight error is logged + counted as failed, not fatal.
  → `mark_source_run("ok")` and commit on completion; on a top-level failure (e.g. tree
  fetch) `mark_source_run("error")` + re-raise (as today).
- Prints: `event <id>: ingested N flights (F failed) — X new, Y updated, Z unchanged, T teams`.

**`scripts/replit-populate.sh`:** call `ysr-scrape ecnl --event 3210` (whole event) then
`ysr-rank`. (Drops the per-flight/age/gender args.)

## 5. Result Type

`@dataclass(frozen=True) EventIngestResult(flights_ingested, flights_failed, inserted,
updated, unchanged, teams_created)` — aggregated across flights, returned by the CLI's
event loop (or a small helper) for the summary line and tests.

## 6. Error Handling

- Tree fetch non-success / network error → top-level failure → `mark_source_run("error")`,
  re-raise (non-zero exit).
- A single flight failing (fetch/parse/ingest) → logged with flight id/name, counted in
  `flights_failed`, loop continues. The run still ends `"ok"` if the tree was fetched.
- Flight name without `U##` → skipped in `parse_event_flights` (logged), not counted as a
  processed flight.

## 7. Testing

- `parse_event_flights` against the committed `tests/fixtures/ecnl_event_tree.json`
  (2 boys divisions, 2 flights each): returns 4 `FlightRef`s, all gender `M`, age_groups
  `U12, U12, U11, U11`, correct flight_ids; girls list empty → none; a synthetic flight with
  a non-`U##` name is skipped; a `hasActiveSchedule == false` flight is excluded.
- `fetch_event_tree` raises on a non-success envelope (MockTransport).
- CLI (TestClient/!): mock `fetch_event_tree` (tree fixture) + `fetch_division` (games
  fixture) → `--event` ingests all flights, creating teams across multiple pools; a flight
  whose fetch raises is isolated (counted failed, others succeed); `--flight <id>` ingests
  only that one; source ends `"ok"`; unmigrated DB still errors.
- Full suite + `ruff` + `mypy --strict` green.

## 8. Success Criteria

- `ysr-scrape ecnl --event 3210` ingests every active flight, auto-deriving age/gender,
  creating teams across multiple `(age_group, gender)` pools; idempotent on re-run.
- One malformed/empty flight doesn't abort the event.
- After `ysr-rank`, the web app's pool selector shows multiple pools with populated tables.

## 9. Out of Scope / Follow-ups

- Discovering/listing event IDs (operator supplies them); a future `ysr-scrape ecnl --list-events` could help.
- Scheduling periodic re-ingestion (later).
- MLS NEXT / Girls Academy sources.
