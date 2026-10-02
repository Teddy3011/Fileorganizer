"""Watches a folder and walks every new file through detect -> classify -> approve -> copy."""

import asyncio
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .classify import classify
from .extract import ExtractionError, extract_text
from .fileops import OUTPUT_DIR, StillDownloading, is_ignored, safe_copy, wait_until_stable

ACTIVE = {"detected", "analyzing", "awaiting_approval", "copying"}
DEFAULT_PROFILE = {"name": "", "level": "", "courses": [], "style": "", "corrections": {}}


class DestinationUnavailable(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def friendly_error(exc, source_path=""):
    if isinstance(exc, StillDownloading):
        return f"File still downloading: it was {exc}. Retry once the download finishes."
    if isinstance(exc, DestinationUnavailable):
        return f"Destination unavailable: {exc}. Check the drive is connected and writable."
    if isinstance(exc, FileNotFoundError) and not os.path.exists(source_path):
        return "File disappeared: it was moved, renamed, or deleted before StudySort could copy it."
    if isinstance(exc, PermissionError):
        return "Permission denied: another program may have the file open, or StudySort lacks access."
    if isinstance(exc, OSError):
        return f"Copy failed: {exc.strerror or exc}. The original file was not changed."
    return f"Unexpected error: {exc}"


class _Handler(FileSystemEventHandler):
    def __init__(self, service):
        self.service = service

    def on_created(self, event):
        if not event.is_directory:
            self.service.submit(event.src_path)

    def on_moved(self, event):
        # Browsers finish a download by renaming "x.pdf.crdownload" -> "x.pdf".
        if not event.is_directory:
            self.service.submit(event.dest_path)


class StudySortService:
    def __init__(self, watch_dir, store, auto_organize=False, move=False, stability=None):
        self.watch_dir = os.path.abspath(watch_dir)
        self.store = store
        self.auto_organize = auto_organize
        self.move = move
        self.stability = stability or {}
        self.observer = None
        self._lock = threading.RLock()
        self._active = {}  # source_path -> id, so duplicate events don't double-process
        self._subscribers = []  # (loop, asyncio.Queue)
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="studysort")
        self._recover()

    # ---- lifecycle -------------------------------------------------------------
    def _recover(self):
        """After a restart, half-finished work becomes a retryable failure."""
        for rec in self.store.list(limit=10000):
            if rec["status"] in ("detected", "analyzing", "copying"):
                self.store.update(rec["id"], status="failed",
                                  error="Interrupted when StudySort stopped. Retry to process it again.")
            elif rec["status"] == "awaiting_approval":
                self._active[rec["source_path"]] = rec["id"]

    def start(self):
        self.observer = Observer()
        self.observer.schedule(_Handler(self), self.watch_dir, recursive=False)
        self.observer.start()

    def stop(self):
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=5)
        self._pool.shutdown(wait=False, cancel_futures=True)

    def status(self):
        counts = {}
        for rec in self.store.list(limit=10000):
            counts[rec["status"]] = counts.get(rec["status"], 0) + 1
        return {
            "watch_dir": self.watch_dir,
            "watch_name": os.path.basename(self.watch_dir) or self.watch_dir,
            "output_dir": os.path.join(self.watch_dir, OUTPUT_DIR),
            "watcher_alive": bool(self.observer and self.observer.is_alive()),
            "auto_organize": self.auto_organize,
            "move": self.move,
            "counts": counts,
        }

    # ---- events ----------------------------------------------------------------
    def subscribe(self):
        q = asyncio.Queue()
        with self._lock:
            self._subscribers.append((asyncio.get_running_loop(), q))
        return q

    def unsubscribe(self, q):
        with self._lock:
            self._subscribers = [s for s in self._subscribers if s[1] is not q]

    def publish(self, event):
        with self._lock:
            subscribers = list(self._subscribers)
        for loop, q in subscribers:
            try:
                loop.call_soon_threadsafe(q.put_nowait, event)
            except RuntimeError:  # loop closed: client went away
                self.unsubscribe(q)

    # ---- state machine ---------------------------------------------------------
    def _transition(self, file_id, allowed, **fields):
        """Update only if the current status is in `allowed`; returns the record or None."""
        with self._lock:
            rec = self.store.get(file_id)
            if not rec or rec["status"] not in allowed:
                return None
            rec = self.store.update(file_id, **fields)
            if rec["status"] in ACTIVE:
                self._active[rec["source_path"]] = file_id
            elif self._active.get(rec["source_path"]) == file_id:
                del self._active[rec["source_path"]]
        self.publish({"type": "file", "file": rec})
        return rec

    def _fail(self, file_id, exc, source_path):
        self._transition(file_id, ACTIVE - {"awaiting_approval"},
                         status="failed", error=friendly_error(exc, source_path))

    def submit(self, path):
        """Called by the watcher for every created/moved-in file."""
        path = os.path.abspath(path)
        if is_ignored(path, self.watch_dir):
            return None
        with self._lock:
            if path in self._active:
                return None
            previous = self.store.latest_for_path(path)
            if previous and previous["status"] == "failed":
                return self.retry(previous["id"])  # same file came back: reuse its card
            rec = self.store.add({
                "id": uuid.uuid4().hex[:12], "name": os.path.basename(path), "source_path": path,
                "detected_at": now(), "status": "detected", "analysis": "Waiting for the download to finish",
            })
            self._active[path] = rec["id"]
        self.publish({"type": "file", "file": rec})
        self._pool.submit(self._process, rec["id"])
        return rec

    def _process(self, file_id):
        rec = self.store.get(file_id)
        path = rec["source_path"]
        try:
            size = wait_until_stable(path, **self.stability)
            if not self._transition(file_id, {"detected"}, status="analyzing", size=size,
                                    analysis="Reading the document"):
                return
            ext = os.path.splitext(path)[1]
            try:
                text = extract_text(path, ext)
                analysis = "Classified from filename and document text" if text else "Classified from filename"
            except ExtractionError as exc:
                text, analysis = "", f"Unsupported or corrupted document ({exc}); classified from filename"
            rel = os.path.relpath(path, self.watch_dir)
            result = classify(rec["name"], rel, text, self.profile())
            if not self._transition(
                file_id, {"analyzing"}, status="awaiting_approval", course=result["course"],
                type=result["type"], confidence=result["confidence"], reason=result["reason"],
                planned_destination=result["destination"], analysis=analysis,
            ):
                return
            if self.auto_organize:
                self._copy(file_id)
        except Exception as exc:  # one bad file must never stop the watcher
            self._fail(file_id, exc, path)

    def _copy(self, file_id):
        rec = self._transition(file_id, {"awaiting_approval"}, status="copying")
        if not rec:
            return
        try:
            parts = rec["planned_destination"].split("/")
            folder = os.path.join(self.watch_dir, *parts[:-1])
            try:
                os.makedirs(folder, exist_ok=True)
            except OSError as exc:
                raise DestinationUnavailable(exc.strerror or str(exc)) from exc
            dest = safe_copy(rec["source_path"], folder, rec["name"], move=self.move)
            self._transition(
                file_id, {"copying"}, status="moved" if self.move else "copied", error=None,
                actual_destination=os.path.relpath(dest, self.watch_dir).replace(os.sep, "/"),
                completed_at=now(),
            )
        except Exception as exc:
            self._fail(file_id, exc, rec["source_path"])

    # ---- user actions (return None when the action isn't valid now) -------------
    def approve(self, file_id):
        rec = self.store.get(file_id)
        if not rec or rec["status"] != "awaiting_approval":
            return None
        self._pool.submit(self._copy, file_id)
        return rec

    def retry(self, file_id):
        rec = self._transition(file_id, {"failed"}, status="detected", error=None,
                               analysis="Waiting for the download to finish")
        if rec:
            self._pool.submit(self._process, file_id)
        return rec

    def cancel(self, file_id):
        return self._transition(file_id, {"detected", "analyzing", "awaiting_approval"}, status="cancelled")

    def clear_history(self):
        with self._lock:
            self.store.clear()
            self._active.clear()
        self.publish({"type": "cleared"})

    # ---- profile ---------------------------------------------------------------
    def profile(self):
        return {**DEFAULT_PROFILE, **self.store.get_json("profile", {})}

    def save_profile(self, profile):
        merged = {**DEFAULT_PROFILE, **{k: v for k, v in profile.items() if k in DEFAULT_PROFILE}}
        self.store.set_json("profile", merged)
        return merged
