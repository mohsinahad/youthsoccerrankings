from __future__ import annotations

import pathlib
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ysr.db import make_engine, make_session_factory
from ysr.web import queries

_BASE = pathlib.Path(__file__).parent
templates = Jinja2Templates(directory=str(_BASE / "templates"))

app = FastAPI(title="Youth Soccer Rankings")
app.mount("/static", StaticFiles(directory=str(_BASE / "static")), name="static")

_session_factory = make_session_factory(make_engine())


def get_session() -> Iterator[Session]:
    with _session_factory() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


@app.get("/", response_class=HTMLResponse)
def index(request: Request, session: SessionDep) -> HTMLResponse:
    pools = queries.list_pools(session)
    return templates.TemplateResponse(request, "index.html", {"pools": pools})


@app.get("/rankings", response_class=HTMLResponse)
def rankings(
    request: Request,
    session: SessionDep,
    age_group: str | None = None,
    gender: str | None = None,
) -> HTMLResponse:
    pools = queries.list_pools(session)
    teams: list[queries.RankedTeam] = []
    if pools:
        if age_group is None or gender is None:
            age_group, gender = pools[0].age_group, pools[0].gender
        teams = queries.pool_rankings(session, age_group, gender)
    return templates.TemplateResponse(
        request,
        "rankings.html",
        {"pools": pools, "teams": teams, "age_group": age_group, "gender": gender},
    )


@app.get("/teams/{team_id}", response_class=HTMLResponse)
def team(request: Request, session: SessionDep, team_id: int) -> HTMLResponse:
    detail = queries.team_detail(session, team_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Team not found")
    return templates.TemplateResponse(request, "team.html", {"d": detail})
