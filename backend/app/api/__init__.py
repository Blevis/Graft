"""API routers. Every group is mounted under /api by app.main."""
from fastapi import APIRouter

from . import (
    access,
    admin,
    audit,
    auth,
    cases,
    inbox,
    insights,
    knowledge,
    org,
    reviews,
    settings,
    tasks,
    timeline,
    users,
)

ROUTERS: list[APIRouter] = [
    auth.router,
    org.router,
    users.router,
    cases.router,
    timeline.router,
    inbox.router,
    tasks.router,
    reviews.router,
    access.router,
    knowledge.router,
    insights.router,
    settings.router,
    audit.router,
    admin.router,
]

from . import agents, ask, home, inbound, people, preferences, responsibilities, workflow

# workflow before cases' "/{case_id}" GET is irrelevant (different methods/paths), but keep it first for clarity.
ROUTERS.insert(0, workflow.router)
ROUTERS.extend((agents.router, ask.router, people.router, responsibilities.router, preferences.router, home.router,
                inbound.router))
