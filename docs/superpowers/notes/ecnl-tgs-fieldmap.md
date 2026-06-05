# ECNL / TGS (AthleteOne) API Field Map

Captured during the Plan 2 discovery spike (2026-06-04). The ECNL public schedules site
(`public.totalglobalsports.com`, an Angular SPA) is backed by the AthleteOne JSON API.
**Reachable with plain `httpx` + browser-like headers — no headless browser needed.**

## Base & headers

- Base URL: `https://api.athleteone.com/api/Event`
- Required headers (browser-like): `User-Agent: Mozilla/5.0 ... Chrome/124.0 Safari/537.36`,
  `Accept: application/json`, `Origin: https://public.totalglobalsports.com`.
- All responses are `{"result": "success", "data": <payload>}`.

## Endpoints (confirmed live)

| Purpose | Path | Params |
|---------|------|--------|
| Division + flight tree for an event | `/get-event-schedule-or-standings/{eventID}` | eventID |
| Division list for an event | `/get-division-list-by-event/{eventID}` | eventID |
| **Games for a flight** | `/get-schedules-by-flight/{eventID}/{flightID}/{teamID}` | eventID, flightID, **teamID=0 for all teams** |
| Standings | `/get-standings-by-div-and-flight/{eventID}/{divisionID}/{flightID}` | eventID, divisionID, flightID |

**Important:** `get-schedules-by-flight` params are `(eventID, flightID, teamID)` — NOT
`(eventID, divisionID, flightID)`. Pass `teamID=0` to get every game in the flight.

### Flow to reach games
1. `GET /get-event-schedule-or-standings/{eventID}` → `data.boysDivAndFlightList` /
   `data.girlsDivAndFlightList`, each division has a `flightList` with `flightID`,
   `flightName`, `hasActiveSchedule`.
2. For a flight with `hasActiveSchedule: true`:
   `GET /get-schedules-by-flight/{eventID}/{flightID}/0` → `data` = list of game records.

## Game record fields (from `get-schedules-by-flight`)

| Our field | TGS field | Notes |
|-----------|-----------|-------|
| home team name | `homeTeam` | e.g. `"Pittsburgh Riverhounds - Pre ECNL B13"` (club + team) |
| away team name | `awayTeam` | |
| **home team stable id** | `hometeamID` | int — stable per-source team key (use for identity) |
| **away team stable id** | `awayteamID` | int |
| home club | `homeTeamClub` | e.g. `"Pittsburgh Riverhounds"` |
| away club | `awayTeamClub` | |
| home score | `hometeamscore` | int, or **null when unplayed** |
| away score | `awayteamscore` | int, or **null when unplayed** |
| date | `gameDate` | ISO `"2024-08-18T11:00:00"` → take `.date()` |
| competition | `flight` | e.g. `"U12 (2013) Pre-ECNL North - 9v9"` |
| raw | (whole record) | preserved in `games.raw_payload` |

**Completed game = both `hometeamscore` and `awayteamscore` are non-null.** There is no
explicit boolean; unplayed games carry null scores.

## Plan revision driven by this spike

- **Identity by stable TGS team id, not fuzzy name matching, for ECNL.** TGS provides
  `hometeamID`/`awayteamID`. Keying identity on these (exact match) is more robust and
  avoids conflating a club's sibling teams (e.g. "... Boys Pink" vs "... Boys Blue") that
  fuzzy `token_set_ratio` could merge. The Plan 1 fuzzy matcher (`ysr.identity`) remains
  for future sources that lack stable IDs. We store the TGS team id (as a string) in
  `TeamAlias.alias_name` (the source's stable key) and the human name in
  `Team.display_name`; `Team.club` is populated from `homeTeamClub`/`awayTeamClub`.
- **Fetch via httpx** (no Playwright fallback needed).

## Spike capture used for the test fixture

`tests/fixtures/ecnl_event_sample.json` = `get-schedules-by-flight/3210/26840/0`
(event 3210, flight 26840 "U12 (2013) Pre-ECNL North"), trimmed to 3 real records. That
flight's games are all played, so the third record's scores were set to `null` to
represent an unplayed game exactly as TGS would (null scores) — structure otherwise
unchanged.
