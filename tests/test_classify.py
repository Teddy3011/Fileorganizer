import zipfile

import pytest

from studysort.classify import classify, correction_token, find_codes
from studysort.extract import ExtractionError, extract_text

PROFILE = {"courses": ["CS101", "Data Structures", "MEE 323", "Calculus"], "corrections": {}}


@pytest.mark.parametrize("text, codes", [
    ("MEE 323 Exam 2", ["MEE323"]),
    ("2023_MAT_275_Exam_2_practice", ["MAT275"]),
    ("phy101 lab writeup", ["PHY101"]),
    ("hw 3 for 445", []),          # lowercase word + gap is not a course
    ("2024_Practice_Exam", []),    # a year is not a course
])
def test_course_code_detection(text, codes):
    assert find_codes(text) == codes


def test_configured_course_code_beats_general():
    r = classify("CS101_assignment.pdf", "CS101_assignment.pdf", "", PROFILE)
    assert (r["course"], r["type"], r["confidence"]) == ("CS101", "Assignments", "high")
    assert r["destination"] == "_StudySort/CS101/Assignments/CS101_assignment.pdf"
    assert 'Course code "CS101" found in filename' in r["reason"]


def test_spaced_code_matches_configured_course():
    assert classify("MEE323 Exam 2 Solution.pdf", profile=PROFILE)["course"] == "MEE 323"


def test_unlisted_course_code_still_used():
    assert classify("PHY210_midterm.pdf", profile=PROFILE)["course"] == "PHY210"


@pytest.mark.parametrize("name", ["example.pdf", "latest_report_data.txt", "contest.docx"])
def test_word_boundaries_prevent_exam_and_test_false_hits(name):
    assert classify(name, profile=PROFILE)["type"] != "Exams & Quizzes"


def test_latest_notes_is_notes_not_test():
    assert classify("latest_notes.txt", profile=PROFILE)["type"] == "Lecture Notes"


def test_broad_course_name_needs_the_whole_name():
    assert classify("data_export.csv", profile=PROFILE)["course"] == "General"
    assert classify("structures_and_data_notes.pdf", profile=PROFILE)["course"] == "Data Structures"
    assert classify("Data Structures HW3.pdf", profile=PROFILE)["course"] == "Data Structures"


def test_solutions_beat_exams_and_extension_fallback():
    assert classify("Exam 2 Solution.pdf", profile=PROFILE)["type"] == "Solutions"
    r = classify("setup.exe", profile=PROFILE)
    assert (r["type"], r["confidence"]) == ("Installers", "low")
    assert classify("calc.pptx", profile=PROFILE)["type"] == "Lecture Slides"


def test_filename_outweighs_content_and_content_is_used():
    assert classify("week1.pdf", text="Welcome to Calculus", profile=PROFILE)["course"] == "Calculus"
    r = classify("CS101_quiz.pdf", text="Calculus review", profile=PROFILE)
    assert r["course"] == "CS101"


def test_learned_correction_wins():
    profile = {**PROFILE, "corrections": {"thermodynamics": {"type": "Reading", "course": ""}}}
    r = classify("thermodynamics_exam.pdf", profile=profile)
    assert r["type"] == "Reading" and "Learned" in r["reason"]
    assert correction_token("CS101 thermodynamics notes.pdf") == "thermodynamics"
    assert correction_token("final notes.pdf") == ""


def test_style_controls_destination():
    profile = {**PROFILE, "style": "By type, then course"}
    expected = "_StudySort/Exams & Quizzes/CS101/CS101_quiz.pdf"
    assert classify("CS101_quiz.pdf", profile=profile)["destination"] == expected


def _zip(path, member, xml):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(member, xml)


def test_extract_supported_formats(tmp_path):
    docx = tmp_path / "a.docx"
    _zip(docx, "word/document.xml", '<w:document xmlns:w="urn:w"><w:t>CS101 Homework</w:t></w:document>')
    pptx = tmp_path / "a.pptx"
    _zip(pptx, "ppt/slides/slide1.xml", '<p:sld xmlns:a="urn:a" xmlns:p="urn:p"><a:t>Lecture 1</a:t></p:sld>')
    html = tmp_path / "a.html"
    html.write_text("<html><style>x{}</style><body><h1>Syllabus</h1></body></html>")
    md = tmp_path / "a.md"
    md.write_text("# Notes\n\nweek   3")
    assert extract_text(docx, ".docx") == "CS101 Homework"
    assert extract_text(pptx, ".pptx") == "Lecture 1"
    assert extract_text(html, ".html") == "Syllabus"
    assert extract_text(md, ".md") == "# Notes week 3"
    assert extract_text(md, ".zip") == ""


@pytest.mark.parametrize("ext", [".pdf", ".docx", ".pptx"])
def test_corrupted_documents_raise_extraction_error(tmp_path, ext):
    bad = tmp_path / f"bad{ext}"
    bad.write_bytes(b"this is not a real document")
    with pytest.raises(ExtractionError):
        extract_text(bad, ext)
