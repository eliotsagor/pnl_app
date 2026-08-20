import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import tradesteward_fetch as tsf
from backend.routers import calendar, days, export, mappings, tradesteward

app = FastAPI(title="Daily P&L Tracker API")


@app.on_event("shutdown")
def _close_tradesteward_session():
    # Releases the shared browser session (see tradesteward_fetch.get_shared_client)
    # kept open across fetches so repeated single-day fetches don't each re-trigger
    # TradeSteward's login challenge.
    tsf.close_shared_client()

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
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="frontend-assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        # Serve any real static file (favicon, manifest, etc.) directly; for
        # every other path -- a client-side React Router route like /risk,
        # /positions, or a hard refresh on one of them -- fall back to
        # index.html so the SPA can take over and route it itself. Without
        # this, only client-side navigation from within the app worked;
        # a direct hit or refresh on a route other than "/" 404'd, since
        # StaticFiles(html=True) only serves index.html for exact/root
        # matches, not for unmatched paths.
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        index = FRONTEND_DIST / "index.html"
        if not index.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(index)
