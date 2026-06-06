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
from ysr.web.season import u_age as compute_u_age

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
    birth_year: int | None = None,
    gender: str | None = None,
) -> HTMLResponse:
    pools = queries.list_pools(session)
    teams: list[queries.RankedTeam] = []
    selected_u_age: int | None = None
    if pools:
        if birth_year is None or gender is None:
            birth_year, gender = pools[0].birth_year, pools[0].gender
        teams = queries.pool_rankings(session, birth_year, gender)
        selected_u_age = compute_u_age(birth_year)
    return templates.TemplateResponse(
        request,
        "rankings.html",
        {
            "pools": pools,
            "teams": teams,
            "birth_year": birth_year,
            "gender": gender,
            "u_age": selected_u_age,
        },
    )


@app.get("/teams/{team_id}", response_class=HTMLResponse)
def team(request: Request, session: SessionDep, team_id: int) -> HTMLResponse:
    detail = queries.team_detail(session, team_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Team not found")
    return templates.TemplateResponse(request, "team.html", {"d": detail})
