import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.routers import calendar, days, export, mappings, tradesteward

app = FastAPI(title="Daily P&L Tracker API")

if os.environ.get("PNL_DEV"):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(calendar.router, prefix="/api")
app.include_router(days.router, prefix="/api")
app.include_router(mappings.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(tradesteward.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}


FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
