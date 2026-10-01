"""Local text extraction for classification. Nothing leaves the machine."""

import re
import zipfile
from html.parser import HTMLParser
from xml.etree import ElementTree

MAX_CHARS = 12000
PLAIN_EXTS = {"txt", "md", "csv"}
SUPPORTED_EXTS = PLAIN_EXTS | {"pdf", "docx", "pptx", "html", "htm"}


class ExtractionError(Exception):
    """The document is unsupported, encrypted, or corrupted."""


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self._skip = [], False

    def handle_starttag(self, tag, attrs):
        self._skip = tag in ("script", "style")

    def handle_endtag(self, tag):
        self._skip = False

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def _office_text(path, member):
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read(member)
    except KeyError:
        raise ExtractionError("document has no readable text part") from None
    except zipfile.BadZipFile:
        raise ExtractionError("document is corrupted or not a real Office file") from None
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        raise ExtractionError("document XML is corrupted") from None
    # w:t (Word) and a:t (PowerPoint) both end in "}t".
    return " ".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))


def _pdf_text(path):
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(path)
        return " ".join((page.extract_text() or "") for page in reader.pages[:2])
    except (PdfReadError, ValueError, KeyError) as exc:
        raise ExtractionError(f"PDF could not be read ({exc})") from exc


def extract_text(path, extension):
    """Opening text of a supported document, '' for unsupported types.

    Raises ExtractionError for supported-but-unreadable files and OSError for I/O problems.
    """
    ext = extension.lower().lstrip(".")
    if ext == "pdf":
        text = _pdf_text(path)
    elif ext == "docx":
        text = _office_text(path, "word/document.xml")
    elif ext == "pptx":
        text = _office_text(path, "ppt/slides/slide1.xml")
    elif ext in PLAIN_EXTS or ext in ("html", "htm"):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read(64000)
        if ext in ("html", "htm"):
            parser = _HTMLText()
            parser.feed(text)
            text = " ".join(parser.parts)
    else:
        return ""
    return re.sub(r"\s+", " ", text).strip()[:MAX_CHARS]
