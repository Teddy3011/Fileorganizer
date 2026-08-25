#!/usr/bin/env python3
"""
Auto File Organizer & Renamer
------------------------------
Watches a folder. Whenever a new file appears, it:
  1. Sorts it into a subfolder based on file type (Images, Docs, Videos, etc.)
  2. Renames it using a consistent pattern: <category>_<YYYYMMDD>_<counter>.<ext>

Usage:
    python auto_organizer.py /path/to/watch_folder

Requires:
    pip install watchdog
"""

import os
import re
import sys
import time
import shutil
from datetime import datetime

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

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

def get_category(ext):
    ext = ext.lower()
    for category, exts in CATEGORY_MAP.items():
        if ext in exts:
            return category
    return "Other"

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

def get_content_category(filepath, ext):
    """Determine a content-based category using AI (if enabled) or first heading."""
    text = extract_text_snippet(filepath, ext)
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

class AutoOrganizeHandler(FileSystemEventHandler):
    def __init__(self, watch_folder):
        self.watch_folder = watch_folder

    def on_created(self, event):
        if event.is_directory:
            return
        # Small delay to let the file finish writing/copying
        time.sleep(0.5)
        self.process_file(event.src_path)

    def process_file(self, filepath):
        if not os.path.exists(filepath):
            return

        filename = os.path.basename(filepath)
        name, ext = os.path.splitext(filename)

        category = get_category(ext)

        # For readable documents, try to categorize by heading/content instead
        if ext.lower() in CONTENT_EXTS:
            content_category = get_content_category(filepath, ext)
            if content_category:
                category = content_category

        dest_folder = os.path.join(self.watch_folder, category)
        os.makedirs(dest_folder, exist_ok=True)

        date_str = datetime.now().strftime("%Y%m%d")
        counter = next_counter(dest_folder, category, date_str, ext)
        new_name = f"{category}_{date_str}_{counter:03d}{ext}"
        dest_path = os.path.join(dest_folder, new_name)

        try:
            shutil.move(filepath, dest_path)
            print(f"[MOVED] {filename}  ->  {category}/{new_name}")
        except Exception as e:
            print(f"[ERROR] Could not move {filename}: {e}")

def organize_existing_files(watch_folder):
    """One-time pass to sort/rename files already sitting in the folder."""
    handler = AutoOrganizeHandler(watch_folder)
    for item in os.listdir(watch_folder):
        full_path = os.path.join(watch_folder, item)
        if os.path.isfile(full_path):
            handler.process_file(full_path)

def main():
    if len(sys.argv) < 2:
        print("Usage: python auto_organizer.py /path/to/watch_folder")
        sys.exit(1)

    watch_folder = sys.argv[1]
    if not os.path.isdir(watch_folder):
        print(f"Error: '{watch_folder}' is not a valid folder.")
        sys.exit(1)

    print(f"Sorting existing files in: {watch_folder}")
    organize_existing_files(watch_folder)

    print(f"\nWatching for new files in: {watch_folder}")
    print("Press Ctrl+C to stop.\n")

    event_handler = AutoOrganizeHandler(watch_folder)
    observer = Observer()
    observer.schedule(event_handler, watch_folder, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    main()
