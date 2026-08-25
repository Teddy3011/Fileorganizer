#!/usr/bin/env python3
"""
Auto File Organizer & Renamer
------------------------------
Watches a folder. Whenever a new file appears, it:
  1. Sorts it into a subfolder based on file type (Images, Docs, Videos, etc.)
  2. Renames it using a consistent pattern: <category>_<YYYYMMDD>_<counter>.<ext>

Documents (.pdf/.docx/.txt/.md) instead go to <course>/<Exams|Solutions|Resources>/
when a course code is found, keeping their original filename.

Usage:
    python auto_organizer.py /path/to/watch_folder
    python auto_organizer.py --self-check      # run the built-in asserts

Requires:
    pip install watchdog
"""

import os
import re
import sys
import time
import shutil
from datetime import datetime

# ---- CONFIG: extension -> category folder ----
CATEGORY_MAP = {
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".heic"],
    "Documents": [".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt"],
    "Spreadsheets": [".xls", ".xlsx", ".csv"],
    "Presentations": [".ppt", ".pptx"],
    "Videos": [".mp4", ".mov", ".avi", ".mkv"],
    "Audio": [".mp3", ".wav", ".m4a", ".flac"],
    "Archives": [".zip", ".rar", ".7z", ".tar", ".gz"],
    "Code": [".py", ".js", ".html", ".css", ".json", ".java", ".cpp"],
}

# Content-readable extensions eligible for heading/AI-based categorization
CONTENT_EXTS = [".pdf", ".docx", ".txt", ".md"]

# ---- Toggle: True = call Claude for the folder name, False = just use the file's first line ----
USE_AI_CLASSIFICATION = False  # off by default — no API key needed, heading works fine for class notes/PDFs
AI_MODEL = "claude-sonnet-4-6"
# To turn on: set True and `export ANTHROPIC_API_KEY="your-key-here"`

# ---- Course code detection ----
# Uppercase codes may be separated (MEE 323, MAT_275, EEE-202); lowercase must be
# glued (phy101), so ordinary words do not turn into courses ("hw 3 for 445").
# Boundaries are non-alphanumeric, not \b: underscore is a word char, so \b would
# never fire on "2023_MAT_275_Exam".
COURSE_RES = [
    re.compile(r"(?<![A-Za-z0-9])([A-Z]{2,4})[\s_-]?(\d{3})(?![A-Za-z0-9])"),
    re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{2,4})(\d{3})(?![A-Za-z0-9])"),
]
LEADING_NUM_RE = re.compile(r"^\s*(\d{3})(?![A-Za-z0-9])")  # "318 HW6.pdf" -> 318

# ---- Exam / Solution / Resources split ----
# Order matters: "Exam 2 Solution" is a solution, not an exam.
# Same non-alphanumeric boundaries as above, so "360_Final_Cheat_Sheet" is seen.
def _kind_re(*words):
    return re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(words) + r")(?![A-Za-z0-9])", re.I)

KIND_RES = [
    ("Solutions", _kind_re("solutions?", "solns?", "answers?", "keys?", "rubrics?", "solved")),
    ("Exams", _kind_re("exams?", "midterms?", "finals?", "quiz(?:zes)?", "tests?", "prelims?")),
]
DEFAULT_KIND = "Resources"


def get_category(ext):
    ext = ext.lower()
    for category, exts in CATEGORY_MAP.items():
        if ext in exts:
            return category
    return "Other"

def get_course(text):
    """'MEE 323 Exam 2' -> 'MEE323'; '318 HW6' -> '318'; None if no course code."""
    text = text or ""
    for rx in COURSE_RES:
        m = rx.search(text)
        if m:
            return f"{m.group(1).upper()}{m.group(2)}"
    m = LEADING_NUM_RE.match(text)
    return m.group(1) if m else None

def get_kind(text):
    """Bucket a document as Exams / Solutions / Resources by keyword."""
    # ponytail: keyword match, no content analysis. "final project" lands in Exams —
    # add patterns to KIND_RES if that bites.
    for kind, rx in KIND_RES:
        if rx.search(text or ""):
            return kind
    return DEFAULT_KIND

def sanitize_folder_name(name):
    """Turn arbitrary text into a safe, short folder name."""
    name = re.sub(r"[^\w\s-]", "", name).strip()
    name = re.sub(r"\s+", "_", name)
    return name[:40] if name else "Unclassified"

def extract_text_snippet(filepath, ext, max_chars=1500):
    """Pull the first chunk of readable text from a file, for heading/AI use."""
    ext = ext.lower()
    try:
        if ext == ".txt" or ext == ".md":
            with open(filepath, "r", errors="ignore") as f:
                return f.read(max_chars)

        elif ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(filepath)
            text = ""
            for page in reader.pages[:2]:
                text += page.extract_text() or ""
                if len(text) >= max_chars:
                    break
            return text[:max_chars]

        elif ext == ".docx":
            import docx
            doc = docx.Document(filepath)
            text = "\n".join(p.text for p in doc.paragraphs[:30])
            return text[:max_chars]

    except Exception as e:
        print(f"[WARN] Could not extract text from {filepath}: {e}")
    return ""

def get_first_heading(text):
    """Fallback heuristic: use the first non-empty line as a 'heading'."""
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line
    return None

def classify_with_ai(text):
    """Ask Claude to produce a short category name based on file content."""
    if not text.strip():
        return None
    try:
        import anthropic
        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
        prompt = (
            "Read this document excerpt and respond with ONLY a short category "
            "or folder name (2-4 words, no punctuation) that best describes its "
            "topic or heading. No explanation, just the name.\n\n"
            f"Excerpt:\n{text[:1500]}"
        )
        response = client.messages.create(
            model=AI_MODEL,
            max_tokens=20,
            messages=[{"role": "user", "content": prompt}],
        )
        category = response.content[0].text.strip()
        return sanitize_folder_name(category)
    except Exception as e:
        print(f"[WARN] AI classification failed, falling back to heading: {e}")
        return None

def get_content_category(text):
    """Determine a content-based category using AI (if enabled) or first heading."""
    if not text:
        return None

    if USE_AI_CLASSIFICATION:
        ai_category = classify_with_ai(text)
        if ai_category:
            return ai_category

    heading = get_first_heading(text)
    return sanitize_folder_name(heading) if heading else None

def next_counter(dest_folder, category, date_str, ext):
    """Find the next available counter number for this category+date+ext."""
    n = 1
    while True:
        candidate = f"{category}_{date_str}_{n:03d}{ext}"
        if not os.path.exists(os.path.join(dest_folder, candidate)):
            return n
        n += 1

def unique_path(path):
    """Append _1, _2, ... until the path is free."""
    base, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(path):
        path = f"{base}_{n}{ext}"
        n += 1
    return path

def doc_destination(name, ext, text):
    """Relative folder for a document: <course-or-topic>/<Exams|Solutions|Resources>."""
    heading = get_first_heading(text) or ""
    # Filename first — course codes survive there even when the PDF text will not parse.
    subject = get_course(name) or get_course(heading)
    if not subject:
        subject = get_content_category(text) or get_category(ext)
    return os.path.join(subject, get_kind(f"{name} {heading}"))

def process_file(filepath, watch_folder):
    if not os.path.exists(filepath):
        return

    filename = os.path.basename(filepath)
    name, ext = os.path.splitext(filename)

    if ext.lower() in CONTENT_EXTS:
        relative = doc_destination(name, ext, extract_text_snippet(filepath, ext))
        dest_folder = os.path.join(watch_folder, relative)
        os.makedirs(dest_folder, exist_ok=True)
        # Keep the original name: every doc in a course would otherwise be MEE323_<date>_NNN.
        dest_path = unique_path(os.path.join(dest_folder, filename))
    else:
        category = get_category(ext)
        relative = category
        dest_folder = os.path.join(watch_folder, category)
        os.makedirs(dest_folder, exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d")
        counter = next_counter(dest_folder, category, date_str, ext)
        dest_path = os.path.join(dest_folder, f"{category}_{date_str}_{counter:03d}{ext}")

    try:
        shutil.move(filepath, dest_path)
        print(f"[MOVED] {filename}  ->  {relative}{os.sep}{os.path.basename(dest_path)}")
    except Exception as e:
        print(f"[ERROR] Could not move {filename}: {e}")

def organize_existing_files(watch_folder):
    """One-time pass to sort/rename files already sitting in the folder."""
    for item in os.listdir(watch_folder):
        full_path = os.path.join(watch_folder, item)
        if os.path.isfile(full_path):
            process_file(full_path, watch_folder)

def self_check():
    import tempfile

    assert get_course("MEE 323 Exam 2") == "MEE323"
    assert get_course("2023_MAT_275_Exam_2_practice") == "MAT275"
    assert get_course("phy101 lab writeup") == "PHY101"
    assert get_course("318 HW6") == "318"
    assert get_course("hw 3 for 445") is None          # lowercase word + gap is not a course
    assert get_course("2024_Practice_Exam") is None    # 4-digit year is not a course

    assert get_kind("MEE323 Exam 2 Solution") == "Solutions"   # solutions beat exams
    assert get_kind("Midterm review") == "Exams"
    assert get_kind("Lecture notes week 3") == "Resources"
    assert get_kind("2023_MAT_275_Exam_2_practice") == "Exams"  # underscores are separators
    assert get_kind("360_Final_Cheat_Sheet") == "Exams"
    assert get_kind("monkey keyboard latest") == "Resources"   # no substring false hits

    assert doc_destination("EEE-202 Final", ".pdf", "") == os.path.join("EEE202", "Exams")
    assert doc_destination("notes", ".txt", "Intro to Thermo\n") == os.path.join("Intro_to_Thermo", "Resources")

    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "hw3.txt")
        with open(src, "w") as f:
            f.write("MEE 323 Homework 3 Answer Key\n")
        process_file(src, d)
        assert os.path.isfile(os.path.join(d, "MEE323", "Solutions", "hw3.txt"))

    print("self-check OK")

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--self-check":
        self_check()
        return

    if len(sys.argv) < 2:
        print("Usage: python auto_organizer.py /path/to/watch_folder")
        sys.exit(1)

    watch_folder = sys.argv[1]
    if not os.path.isdir(watch_folder):
        print(f"Error: '{watch_folder}' is not a valid folder.")
        sys.exit(1)

    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    class AutoOrganizeHandler(FileSystemEventHandler):
        def on_created(self, event):
            if event.is_directory:
                return
            # Small delay to let the file finish writing/copying
            time.sleep(0.5)
            process_file(event.src_path, watch_folder)

    print(f"Sorting existing files in: {watch_folder}")
    organize_existing_files(watch_folder)

    print(f"\nWatching for new files in: {watch_folder}")
    print("Press Ctrl+C to stop.\n")

    observer = Observer()
    observer.schedule(AutoOrganizeHandler(), watch_folder, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    main()
