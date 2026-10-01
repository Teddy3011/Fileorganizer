"""Local-only HTTP API + Server-Sent Events for the StudySort dashboard."""

import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .classify import classify, correction_token

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "testserver"}


class FileIn(BaseModel):
    name: str = Field(max_length=1000)
    path: str = Field("", max_length=4000)
    text: str = Field("", max_length=20000)


class ClassifyIn(BaseModel):
    files: list[FileIn] = Field(max_length=25000)


class CorrectionIn(BaseModel):
    filename: str
    type: str
    course: str = ""


def _sse(event):
    return f"data: {json.dumps(event)}\n\n"


def create_app(service, heartbeat=15.0):
    app = FastAPI(title="StudySort", docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        # Block other websites (and DNS-rebinding hosts) from driving this local API.
        origin = request.headers.get("origin")
        if (request.url.hostname not in LOCAL_HOSTS
                or (origin and request.method != "GET" and urlsplit(origin).hostname not in LOCAL_HOSTS)):
            return JSONResponse({"detail": "Forbidden origin"}, status_code=403)
        response = await call_next(request)
        response.headers.setdefault("Cache-Control", "no-cache")  # always revalidate after upgrades
        return response

    def found(rec):
        if rec is None:
            raise HTTPException(404, "File not found")
        return rec

    def acted(file_id, rec, action):
        found(service.store.get(file_id))
        if rec is None:
            status = service.store.get(file_id)["status"]
            raise HTTPException(409, f"Cannot {action} a file that is {status.replace('_', ' ')}")
        return service.store.get(file_id)

    @app.get("/api/status")
    def status():
        return service.status()

    @app.get("/api/files")
    def files(limit: int = 500):
        return service.store.list(limit=max(1, min(limit, 5000)))

    @app.delete("/api/files")
    def clear_files():
        service.clear_history()
        return {"cleared": True}

    @app.get("/api/files/{file_id}")
    def file(file_id: str):
        return found(service.store.get(file_id))

    @app.post("/api/files/{file_id}/approve")
    def approve(file_id: str):
        return acted(file_id, service.approve(file_id), "approve")

    @app.post("/api/files/{file_id}/retry")
    def retry(file_id: str):
        return acted(file_id, service.retry(file_id), "retry")

    @app.post("/api/files/{file_id}/cancel")
    def cancel(file_id: str):
        return acted(file_id, service.cancel(file_id), "cancel")

    @app.get("/api/profile")
    def get_profile():
        return service.profile()

    @app.put("/api/profile")
    def put_profile(profile: dict):
        return service.save_profile(profile)

    @app.post("/api/corrections")
    def add_correction(body: CorrectionIn):
        profile = service.profile()
        token = correction_token(body.filename)
        if token:
            profile["corrections"][token] = {"type": body.type, "course": body.course}
            profile = service.save_profile(profile)
        return {"token": token, "profile": profile}

    @app.post("/api/classify")
    def classify_files(body: ClassifyIn):
        profile = service.profile()
        return [classify(f.name, f.path, f.text, profile) for f in body.files]

    @app.get("/api/events/stream")
    async def events(request: Request):
        queue = service.subscribe()

        async def stream():
            try:
                yield _sse({"type": "status", "status": service.status()})
                while not await request.is_disconnected():
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=heartbeat)
                    except asyncio.TimeoutError:
                        event = {"type": "status", "status": service.status()}
                    yield _sse(event)
            finally:
                service.unsubscribe(queue)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    return app
