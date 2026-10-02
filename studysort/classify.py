"""The one StudySort classifier, used by the watcher and by the browser (via /api/classify).

Matching is token-based, never substring-based: "example" is not "exam", "latest" is
not "test", and a multi-word course name only matches when the whole name appears.
"""

import os
import re
from datetime import date

FILE_TYPES = [
    "Assignments", "Lecture Slides", "Lecture Notes", "Questions", "Solutions",
    "Study Materials", "Exams & Quizzes", "Projects", "Syllabi", "Reading",
    "Documents", "Presentations", "Spreadsheets", "Images", "Videos", "Audio",
    "Archives", "Code", "Installers", "Other",
]

# Phrases are token sequences. Plurals are listed explicitly because matching is exact.
TYPE_RULES = [
    ("Solutions", ["worked solutions", "worked solution", "answer key", "answer keys", "model answers",
                   "model answer", "solutions", "solution", "soln", "solns", "answers", "rubric", "solved"]),
    ("Questions", ["practice questions", "practice problems", "question bank", "questions", "question",
                   "problem set", "exercises", "exercise"]),
    ("Syllabi", ["syllabus", "syllabi", "course outline", "schedule"]),
    ("Exams & Quizzes", ["exam", "exams", "quiz", "quizzes", "midterm", "midterms", "final exam", "finals",
                         "test", "tests", "practice test", "prelim"]),
    ("Assignments", ["assignment", "assignments", "homework", "hw", "worksheet", "problem set", "pset",
                     "submission", "lab report"]),
    ("Projects", ["project", "projects", "capstone", "report", "portfolio"]),
    ("Lecture Slides", ["lecture slides", "learning objectives", "slide deck", "slides"]),
    ("Lecture Notes", ["lecture notes", "class notes", "notes", "lecture", "lectures", "week", "lesson"]),
    ("Reading", ["reading", "readings", "chapter", "textbook", "article", "paper", "journal"]),
    ("Study Materials", ["study guide", "flashcards", "flashcard", "revision", "review", "summary",
                         "cheat sheet"]),
]
TYPE_PRIORITY = {"Solutions": 6, "Questions": 5, "Exams & Quizzes": 4, "Syllabi": 3.5,
                 "Assignments": 3, "Lecture Slides": 2.5}

EXTENSION_TYPES = {
    "Documents": ["doc", "docx", "odt", "rtf", "txt", "md", "pdf"],
    "Presentations": ["ppt", "pptx", "key", "odp"],
    "Spreadsheets": ["xls", "xlsx", "csv", "ods"],
    "Images": ["jpg", "jpeg", "png", "gif", "webp", "heic", "svg"],
    "Videos": ["mp4", "mov", "mkv", "avi", "webm", "m4v"],
    "Audio": ["mp3", "wav", "m4a", "aac", "flac", "ogg"],
    "Archives": ["zip", "rar", "7z", "tar", "gz"],
    "Code": ["js", "ts", "jsx", "tsx", "py", "java", "c", "cpp", "cs", "html", "css", "sql", "ipynb"],
    "Installers": ["exe", "msi", "iso", "dmg", "pkg"],
}
SLIDE_EXTS = {"ppt", "pptx", "key", "odp"}

# Filename beats folder path beats document text.
SOURCE_WEIGHT = {"filename": 3, "path": 2, "content": 1}

# Uppercase codes may be separated (MEE 323, MAT_275); lowercase must be glued (phy101),
# so ordinary text such as "hw 3 for 445" does not become a course.
CODE_RES = [
    re.compile(r"(?<![A-Za-z0-9])([A-Z]{2,4})[\s_-]?(\d{3})(?![A-Za-z0-9])"),
    re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{2,4})(\d{3})(?![A-Za-z0-9])"),
]

GENERIC_TOKENS = {t for _, phrases in TYPE_RULES for p in phrases for t in p.split()} | {
    "file", "files", "copy", "final", "draft", "new", "old", "untitled", "document", "scan", "page",
    "class", "course", "unit", "part", "version", "updated",
}
STOP_WORDS = {"and", "the", "of", "to", "in", "for", "a", "an", "intro", "introduction"}


def tokens(text):
    """'CS101_Week3-notes.pdf' -> ['cs', '101', 'week', '3', 'notes', 'pdf']"""
    spaced = re.sub(r"(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])", " ", text or "")
    return re.findall(r"[a-z0-9]+", spaced.lower())


def _has_phrase(token_text, phrase):
    return f" {phrase} " in token_text


def find_codes(text):
    """All course codes in text, normalised: 'MEE 323 / phy101' -> ['MEE323', 'PHY101']."""
    found = []
    for rx in CODE_RES:
        for m in rx.finditer(text or ""):
            code = f"{m.group(1).upper()}{m.group(2)}"
            if code not in found:
                found.append(code)
    return found


def _course_matchers(course):
    """(kind, needle, strength) rules for one configured course like 'CS101 Data Structures'."""
    rules = [("code", code, 10) for code in find_codes(course)]
    without_codes = CODE_RES[1].sub(" ", CODE_RES[0].sub(" ", course))
    name = " ".join(t for t in tokens(without_codes) if not t.isdigit())
    words = [w for w in name.split() if w not in STOP_WORDS]
    if name:
        rules.append(("phrase", name, 8))
    if len(words) > 1:
        # Every significant word somewhere, not one broad word like "data".
        rules.append(("all_words", words, 5))
    return rules


def _sources(name, path, text):
    folder = os.path.dirname((path or "").replace("\\", "/"))
    return [("filename", name), ("path", folder), ("content", text or "")]


def detect_course(name, path, text, courses):
    srcs = [(s, raw, f" {' '.join(tokens(raw))} ", set(find_codes(raw))) for s, raw in _sources(name, path, text)]
    best = (0, "General", "No course name or code found")
    for course in courses:
        for kind, needle, strength in _course_matchers(course):
            for src, _, tok_text, codes in srcs:
                if kind == "code":
                    hit = needle in codes
                elif kind == "phrase":
                    hit = _has_phrase(tok_text, needle)
                else:
                    hit = all(_has_phrase(tok_text, w) for w in needle)
                score = strength * SOURCE_WEIGHT[src] if hit else 0
                if score > best[0]:
                    label = needle if kind != "all_words" else " + ".join(needle)
                    what = "Course code" if kind == "code" else "Course name"
                    best = (score, course, f'{what} "{label}" found in {src}')
    if best[0]:
        return best
    # Unconfigured course code in the filename or path still beats "General".
    for src, raw, _, _ in srcs[:2]:
        codes = find_codes(raw)
        if codes:
            return (SOURCE_WEIGHT[src] * 4, codes[0], f'Unlisted course code "{codes[0]}" found in {src}')
    return best


def detect_type(name, path, text, extension, corrections=None):
    srcs = [(s, f" {' '.join(tokens(raw))} ") for s, raw in _sources(name, path, text)]
    best = (0, None, "")
    for ftype, phrases in TYPE_RULES:
        for phrase in phrases:
            for src, tok_text in srcs:
                if _has_phrase(tok_text, phrase):
                    score = SOURCE_WEIGHT[src] * (len(phrase.split()) + TYPE_PRIORITY.get(ftype, 0))
                    if score > best[0]:
                        best = (score, ftype, f'Keyword "{phrase}" found in {src}')
    if extension in SLIDE_EXTS and best[1] in (None, "Lecture Notes"):
        best = (max(best[0], 1), "Lecture Slides", f".{extension} file is a slide deck")

    # A learned correction outranks keyword rules.
    name_tokens = set(tokens(name))
    for token, info in (corrections or {}).items():
        info = info if isinstance(info, dict) else {"type": info}
        if token in name_tokens and info.get("type"):
            return (100, info["type"], f'Learned from your correction for "{token}"')

    if best[1]:
        return best
    for ftype, exts in EXTENSION_TYPES.items():
        if extension in exts:
            return (0, ftype, f".{extension} extension")
    return (0, "Other", "Unknown file type")


def current_semester(today=None):
    today = today or date.today()
    term = "Spring" if today.month <= 5 else "Summer" if today.month <= 8 else "Fall"
    return f"{term} {today.year}"


def safe_folder_name(value):
    return re.sub(r'[\\/:*?"<>|]', "-", value or "").strip(" .") or "General"


def destination_folders(course, ftype, style=""):
    if style == "By type, then course":
        parts = [ftype, course]
    elif style == "By course, then semester":
        parts = [course, current_semester()]
    else:
        parts = [course, ftype]
    return [safe_folder_name(p) for p in parts]


def classify(name, path="", text="", profile=None):
    profile = profile or {}
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    c_score, course, c_reason = detect_course(name, path, text, profile.get("courses") or [])
    t_score, ftype, t_reason = detect_type(name, path, text, extension, profile.get("corrections"))
    matched = (c_score > 0) + (t_score > 0)
    confidence = ["low", "medium", "high"][matched]
    folders = destination_folders(course, ftype, profile.get("style", ""))
    return {
        "course": course,
        "type": ftype,
        "confidence": confidence,
        "reason": f"{c_reason}; {t_reason}",
        "destination": "/".join(["_StudySort", *folders, name]),
    }


def correction_token(filename):
    """Most distinctive filename token to remember a user's correction by, or ''."""
    stem = filename.rsplit(".", 1)[0]
    candidates = [t for t in re.findall(r"[a-z0-9]+", stem.lower())
                  if len(t) >= 5 and not t.isdigit() and t not in GENERIC_TOKENS]
    return max(candidates, key=len, default="")
