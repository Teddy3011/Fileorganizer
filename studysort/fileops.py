"""Download detection rules and copy-never-overwrite file operations."""

import os
import shutil
import stat
import threading
import time
import uuid
from pathlib import Path

OUTPUT_DIR = "_StudySort"
TEMP_EXTS = (".crdownload", ".part", ".partial", ".tmp", ".download", ".opdownload")


class StillDownloading(Exception):
    pass


def is_ignored(path, watch_root):
    """True for directories, hidden/temp files, and anything inside _StudySort."""
    p, root = Path(path), Path(watch_root)
    try:
        rel = p.resolve().relative_to(root.resolve())
    except ValueError:
        return True  # outside the watched folder
    if any(part.lower() == OUTPUT_DIR.lower() for part in rel.parts):
        return True
    if any(part.startswith(".") for part in rel.parts) or p.name.startswith("~$"):
        return True
    if p.name.lower().endswith(TEMP_EXTS):
        return True
    try:
        st = p.stat()
    except OSError:
        return False  # gone already; stability check will report it
    if stat.S_ISDIR(st.st_mode):
        return True
    return bool(getattr(st, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 0))


def _temp_sibling_exists(path):
    # Firefox writes "file.pdf.part" next to an empty "file.pdf" until it finishes.
    return any(os.path.exists(path + ext) for ext in TEMP_EXTS)


def wait_until_stable(path, checks=3, interval=1.0, timeout=120.0, sleep=time.sleep):
    """Block until size and mtime stop changing and the file opens; bounded by timeout.

    Raises FileNotFoundError if the file vanishes, StillDownloading on timeout.
    """
    deadline = time.monotonic() + timeout
    last, stable = None, 0
    while True:
        st = os.stat(path)  # FileNotFoundError propagates: the file disappeared
        sig = (st.st_size, st.st_mtime_ns)
        stable = stable + 1 if sig == last else 0
        last = sig
        if stable >= checks and not _temp_sibling_exists(path):
            try:
                with open(path, "rb") as f:
                    f.read(1)
                return st.st_size
            except PermissionError:
                stable = 0  # still locked by the browser or antivirus
        if time.monotonic() >= deadline:
            raise StillDownloading(f"still downloading or locked after {int(timeout)} seconds")
        sleep(interval)


_reserved = set()
_reserved_lock = threading.Lock()


def reserve_destination(folder, name):
    """Pick a name in folder that is free on disk AND not claimed by an in-flight copy."""
    stem, ext = os.path.splitext(name)
    n = 1
    with _reserved_lock:
        while True:
            candidate = name if n == 1 else f"{stem} ({n}){ext}"
            full = os.path.join(folder, candidate)
            if full.lower() not in _reserved and not os.path.exists(full):
                _reserved.add(full.lower())
                return full
            n += 1


def release_destination(full):
    with _reserved_lock:
        _reserved.discard(full.lower())


def _commit(tmp, dest):
    """Rename tmp -> dest, raising FileExistsError instead of ever overwriting."""
    if os.name == "nt":
        os.rename(tmp, dest)  # Windows rename refuses to replace an existing file
        return
    try:
        os.link(tmp, dest)  # atomic, fails if dest exists
    except FileExistsError:
        raise
    except OSError:
        # ponytail: FAT/exFAT and some network shares lack hard links; check-then-rename
        # has a tiny race there, but reserve_destination already guards our own copies.
        if os.path.exists(dest):
            raise FileExistsError(dest) from None
        os.rename(tmp, dest)
        return
    os.unlink(tmp)


def safe_copy(src, folder, name, move=False):
    """Copy src into folder under a never-colliding name; returns the final path.

    The copy is written to a hidden temp file first and only renamed into place once
    complete. With move=True the source is removed only after a verified copy.
    """
    os.makedirs(folder, exist_ok=True)
    src_size = os.path.getsize(src)
    for _ in range(20):
        dest = reserve_destination(folder, name)
        tmp = os.path.join(folder, f".studysort-{uuid.uuid4().hex}.tmp")
        try:
            shutil.copy2(src, tmp)
            if os.path.getsize(tmp) != src_size:
                raise OSError("copy was incomplete (size mismatch)")
            _commit(tmp, dest)
        except FileExistsError:
            continue  # something else created dest after we checked; pick the next name
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
            release_destination(dest)
        if move:
            os.remove(src)
        return dest
    raise OSError("could not find a free destination name")
