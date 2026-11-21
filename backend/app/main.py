import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

load_dotenv()

from app.api.cases import router as cases_router  # noqa: E402
from app.api.dispatch import router as dispatch_router  # noqa: E402
from app.api.extract import router as intake_router  # noqa: E402
from app.api.notifications import router as notifications_router  # noqa: E402
from app.api.partner_events import router as partner_events_router  # noqa: E402
from app.api.scheduling import router as scheduling_router  # noqa: E402
from app.db import init_db  # noqa: E402
from app.partners.heatfix import router as delivery_router  # noqa: E402
from app.partners.registry import router as registry_router  # noqa: E402
from app.services.notifications import deliver_pending  # noqa: E402
from app.states import InvalidTransition  # noqa: E402


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db(seed=True)
    yield


app = FastAPI(title="centrix stand-in + mock partner", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(cases_router)
app.include_router(dispatch_router)
app.include_router(intake_router)
app.include_router(partner_events_router)
app.include_router(notifications_router)
app.include_router(delivery_router)
app.include_router(registry_router)
app.include_router(scheduling_router)


@app.middleware("http")
async def deliver_notifications(request: Request, call_next):
    response = await call_next(request)
    # Writes have committed by now. Delivery records failures itself and never raises.
    if request.method != "GET":
        await run_in_threadpool(deliver_pending)
    return response


@app.exception_handler(InvalidTransition)
async def invalid_transition(_request: Request, exc: InvalidTransition):
    return JSONResponse(status_code=409, content={"detail": str(exc)})
