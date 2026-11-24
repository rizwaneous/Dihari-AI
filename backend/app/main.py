import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .db import init_db
from .routers import auth, meta, profiles
from .settings import get_settings

log = logging.getLogger("dihari")

ROUTERS = [meta.router, auth.router, profiles.router]


def _optional_routers():
    """Routers added in later milestones; imported lazily so earlier milestones run."""
    import importlib
    out = []
    for name in ("jobs", "payments", "voice", "admin", "notify", "reports"):
        try:
            out.append(importlib.import_module(f"app.routers.{name}").router)
        except ModuleNotFoundError as e:
            if e.name != f"app.routers.{name}":
                raise
    return out


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from .ai import chain as ai_chain, service as ai_service
    from .db import SessionLocal
    from .models import AICallLog

    def db_sink(rec):
        with SessionLocal() as db:
            db.add(AICallLog(kind=rec.kind, provider=rec.provider, ok=rec.ok, latency_ms=rec.latency_ms, error=rec.error))
            db.commit()
    ai_chain.clear_sinks()
    ai_chain.add_sink(db_sink)
    ai_service.reset()
    ai_service.check_families()   # fail fast if verifier and extractor share a model family
    task = None
    if get_settings().scheduler_enabled:
        from .modules.payments import scheduler_loop
        task = asyncio.create_task(scheduler_loop())
    push_task = None
    if "webpush" in get_settings().notify_providers.split(","):
        if not all((get_settings().vapid_subject, get_settings().vapid_private_key, get_settings().vapid_public_key)):
            raise RuntimeError("Web Push requires VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY and VAPID_SUBJECT")
        from importlib.util import find_spec
        if find_spec("pywebpush") is None:
            raise RuntimeError("Install the backend push extra to enable Web Push")
        from .modules.delivery import run_delivery
        push_task = asyncio.create_task(run_delivery())
    yield
    if push_task:
        push_task.cancel()
    if task:
        task.cancel()


def create_app() -> FastAPI:
    app = FastAPI(title="Dihari", version="0.1.0", lifespan=lifespan)
    for r in ROUTERS + _optional_routers():
        app.include_router(r)

    @app.get("/health")
    def health():
        return {"ok": True}

    return app


app = create_app()
