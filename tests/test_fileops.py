import os
import shutil

import pytest

from studysort import fileops
from studysort.fileops import (
    StillDownloading,
    is_ignored,
    release_destination,
    reserve_destination,
    safe_copy,
    wait_until_stable,
)


@pytest.mark.parametrize("name", ["a.pdf.crdownload", "a.part", "a.tmp", "a.download", ".hidden.pdf", "~$draft.docx"])
def test_temporary_and_hidden_downloads_are_ignored(tmp_path, name):
    (tmp_path / name).write_text("x")
    assert is_ignored(tmp_path / name, tmp_path)


def test_real_files_are_not_ignored(tmp_path):
    (tmp_path / "notes.pdf").write_text("x")
    assert not is_ignored(tmp_path / "notes.pdf", tmp_path)


def test_directories_and_studysort_output_are_ignored(tmp_path):
    out = tmp_path / "_StudySort" / "CS101"
    out.mkdir(parents=True)
    (out / "a.pdf").write_text("x")
    assert is_ignored(out / "a.pdf", tmp_path)
    assert is_ignored(tmp_path / "_StudySort", tmp_path)
    assert is_ignored(tmp_path.parent / "elsewhere.pdf", tmp_path)


def test_stability_waits_for_growth_to_stop(tmp_path):
    f = tmp_path / "big.pdf"
    f.write_bytes(b"a")
    sleeps = []

    def fake_sleep(_):
        sleeps.append(1)
        if len(sleeps) < 3:  # file grows during the first checks
            with open(f, "ab") as fh:
                fh.write(b"more")

    assert wait_until_stable(str(f), checks=2, interval=0, timeout=5, sleep=fake_sleep) == f.stat().st_size
    assert len(sleeps) >= 4


def test_stability_waits_while_temp_sibling_exists(tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"")
    part = tmp_path / "a.pdf.part"
    part.write_bytes(b"downloading")
    with pytest.raises(StillDownloading):
        wait_until_stable(str(f), checks=1, interval=0.01, timeout=0.1)
    part.unlink()
    assert wait_until_stable(str(f), checks=1, interval=0.01, timeout=1) == 0


def test_stability_reports_vanished_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        wait_until_stable(str(tmp_path / "gone.pdf"), checks=1, interval=0, timeout=1)


def test_existing_destination_is_never_overwritten(tmp_path):
    src = tmp_path / "notes.pdf"
    src.write_text("new")
    dest_dir = tmp_path / "out"
    dest_dir.mkdir()
    (dest_dir / "notes.pdf").write_text("old")
    (dest_dir / "notes (2).pdf").write_text("older")
    dest = safe_copy(str(src), str(dest_dir), "notes.pdf")
    assert os.path.basename(dest) == "notes (3).pdf"
    assert (dest_dir / "notes.pdf").read_text() == "old"
    assert (dest_dir / "notes (2).pdf").read_text() == "older"
    assert (dest_dir / "notes (3).pdf").read_text() == "new"


def test_duplicate_names_in_one_operation_get_numbered(tmp_path):
    a = reserve_destination(str(tmp_path), "notes.pdf")
    b = reserve_destination(str(tmp_path), "notes.pdf")
    c = reserve_destination(str(tmp_path), "NOTES.pdf")
    assert [os.path.basename(p) for p in (a, b, c)] == ["notes.pdf", "notes (2).pdf", "NOTES (3).pdf"]
    for p in (a, b, c):
        release_destination(p)


def test_safe_copy_keeps_original_and_leaves_no_temp(tmp_path):
    src = tmp_path / "a.pdf"
    src.write_bytes(b"data")
    dest = safe_copy(str(src), str(tmp_path / "out"), "a.pdf")
    assert src.read_bytes() == b"data" and open(dest, "rb").read() == b"data"
    assert os.listdir(tmp_path / "out") == ["a.pdf"]


def test_move_only_when_enabled(tmp_path):
    src = tmp_path / "a.pdf"
    src.write_bytes(b"data")
    dest = safe_copy(str(src), str(tmp_path / "out"), "a.pdf", move=True)
    assert not src.exists() and open(dest, "rb").read() == b"data"


def test_failed_copy_leaves_nothing_behind_and_keeps_source(tmp_path, monkeypatch):
    src = tmp_path / "a.pdf"
    src.write_bytes(b"data")

    def broken_copy(s, d):
        open(d, "wb").write(b"da")  # partial write, then failure
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(shutil, "copy2", broken_copy)
    with pytest.raises(OSError):
        safe_copy(str(src), str(tmp_path / "out"), "a.pdf", move=True)
    assert src.read_bytes() == b"data"
    assert os.listdir(tmp_path / "out") == []
    assert not fileops._reserved
