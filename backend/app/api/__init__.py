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

from . import agents, ask

ROUTERS.extend((agents.router, ask.router))
