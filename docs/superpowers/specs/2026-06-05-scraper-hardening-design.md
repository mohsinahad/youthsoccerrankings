# Scraper Hardening (Plan 3) — Design Spec

**Date:** 2026-06-05
**Status:** Draft for review
**Depends on:** Plan 2 (ECNL scraper), Plan 1 (data layer).

## 1. Summary

A focused hardening pass over the existing ECNL scraper to make it production-solid:
clearer failure on API errors, resilience to individual malformed records, run tracking
on the `Source` row, and a single schema source of truth (Alembic). Scope is the four
deferred review follow-ups numbered 1, 2, 3, 5 (see `memory/scraper-followups.md`).
Multi-flight ingestion (#6) and team-rename refresh (#4) are explicitly out of scope.

## 2. Goals & Non-Goals

### Goals
- Fail with a clear, diagnostic error when the AthleteOne API returns a non-success body.
- Skip an individual malformed game record (logging it) instead of aborting the batch.
- Record on the `Source` row when it last ran and whether the run succeeded.
- Make Alembic the single schema source of truth — the CLI no longer creates tables.

### Non-Goals
- Multi-flight / whole-event iteration (#6 — next pass).
- Refreshing `Team.display_name`/`club` on upstream rename (#4).
- Any change to ranking, web, or new data sources.
- Retry/alerting beyond what the Plan 2 HTTP client already does.

## 3. Changes

### 3.1 API envelope check (`src/ysr/scrapers/ecnl.py`)
`fetch_division` validates the response envelope before returning: if
`payload.get("result") != "success"`, raise `RuntimeError` naming the event/flight and
including the returned `result` (and any message field). This converts a downstream
`KeyError: 'data'` into an actionable error at the fetch boundary.

### 3.2 Per-record parse isolation (`src/ysr/scrapers/ecnl.py`)
Extract `_parse_match(match: dict[str, Any]) -> ScrapedGame | None` (returns `None` for an
unplayed game — both scores null). `parse_division` iterates `payload["data"]`, calls
`_parse_match` inside a `try/except Exception`, and on failure logs a warning (via the
`logging` module, logger `ysr.scrapers.ecnl`) identifying the record (e.g. its `matchID`)
and continues. Normal unplayed games are skipped silently (return `None`); only genuine
parse failures are logged. Signature stays `parse_division(payload) -> list[ScrapedGame]`.

### 3.3 Run tracking (`src/ysr/ingest.py` + `src/ysr/cli.py`)
Add `mark_source_run(session, source, status: str) -> None` in `ingest.py` that sets
`source.last_run = datetime.now(tz=UTC)` and `source.status = status`. The CLI wraps the
fetch+ingest in `try/except`: on success it calls `mark_source_run(..., "ok")` and commits;
on any exception it calls `mark_source_run(..., "error")`, commits the status, and re-raises
(so the failure still surfaces / non-zero exit). `Source.last_run` is a naive `DateTime`
column, so store a UTC value.

### 3.4 Alembic as single schema source (`src/ysr/cli.py`)
Remove `create_all(engine)` from the CLI. At startup the CLI verifies the schema exists
via SQLAlchemy `inspect(engine)` — if the `sources`/`games` tables are absent, raise a
clear `RuntimeError("database not initialized; run `alembic upgrade head`")` and exit
non-zero before any fetch. Production therefore has one schema authority (Alembic).
Tests create their temp-DB schema explicitly with `create_all` in the test setup (not via
the CLI), so they remain network- and migration-free.

## 4. Components Touched

- `src/ysr/scrapers/ecnl.py` — envelope check in `fetch_division`; `_parse_match` helper
  + isolation/logging in `parse_division`.
- `src/ysr/ingest.py` — new `mark_source_run`.
- `src/ysr/cli.py` — schema pre-check (no `create_all`); run-tracking try/except.
- Tests updated/added accordingly.

## 5. Error Handling Summary

- API non-success body → `RuntimeError` at fetch (clear, names event/flight).
- Malformed individual record → logged warning + skipped; batch continues.
- Unmigrated DB → `RuntimeError` with remediation hint before any network call.
- Any run failure → `Source.status="error"` persisted, then the error propagates.

## 6. Testing

- `fetch_division` raises a clear `RuntimeError` on a `{"result":"error",...}` body
  (MockTransport), and still returns normally on success.
- `parse_division` skips a malformed record (e.g. missing `homeTeam` or a bad `gameDate`)
  while still returning the valid games from the same payload; a `caplog` assertion
  confirms the skip is logged.
- `mark_source_run` sets `last_run` (non-null) and `status` on the row.
- CLI: raises the clear "run alembic" error when tables are absent; on a simulated fetch
  failure (patched `fetch_division` raising) the `Source.status` is persisted as `"error"`
  and the command exits non-zero; the happy path (schema present, patched fetch) sets
  `status="ok"` and `last_run`.
- Full suite + `mypy --strict` stay green.

## 7. Success Criteria

- A non-success API body and an unmigrated DB both produce clear, actionable errors.
- A single malformed record never aborts an otherwise-good batch.
- After any run, the `Source` row reflects the time and outcome.
- `create_all` no longer appears in production code paths; Alembic is authoritative.

## 8. Out of Scope / Follow-ups

- Multi-flight ingestion (#6) — next plan; will rely on the error isolation added here.
- Team rename refresh (#4) — deferred.
