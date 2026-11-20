import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from app.api.cases import router as cases_router  # noqa: E402
from app.db import init_db  # noqa: E402
from app.partners.heatfix import router as heatfix_router  # noqa: E402


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
app.include_router(heatfix_router)
