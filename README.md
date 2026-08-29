# StudySort

StudySort is a chat-first file organizer for students. It learns a student's name, study level, courses, and preferred folder structure, analyzes selected files, and proposes a customizable organization plan.

The interface includes an original transparent mascot illustration of a cat sorting study papers into folders. The mascot animates gently while a folder or drive is being scanned.

## Run locally

```bash
python3 -m http.server 4173
```

Open `http://localhost:4173` in Chrome or Edge. Folder write access uses the File System Access API, which requires a secure context such as `localhost`.

To scan a Windows data drive, choose the `D:\` drive in the browser's folder picker. The browser will always ask for permission first. Some browsers or managed school devices may block drive-root selection; choosing a top-level folder such as `D:\School` is the reliable fallback.

You can also select multiple individual files. StudySort analyzes them first, suggests the personalized folder structure, and then asks you to choose a separate destination where `_StudySort` should be created.

## Content analysis

- PDF: extracts text from page 1.
- PowerPoint `.pptx`: extracts text from slide 1.
- Word `.docx`: extracts the opening document section because Word pagination depends on fonts and layout.
- Text, Markdown, CSV, and HTML: extracts the beginning of the file.
- Other formats: uses the filename, extension, and available path.

Content and filenames are used together to detect the course and categories including Lecture Slides, Lecture Notes, Questions, Solutions, Assignments, Exams & Quizzes, and Study Materials. Image-only PDFs and scanned images require OCR, which this browser-only version does not perform.

For individually selected files, every supported file is content-scanned. Folder and drive scans content-scan up to 300 supported files and classify the rest from names and paths so the browser remains responsive.

## Chat plan commands

After analysis, the chat understands commands such as:

```text
Show plan
Review files
Move quiz.pdf to CS101 / Questions
Rename Solutions to Answer Keys
Create folders
Execute plan
Where are my files?
Show corrections
Forget correction homework
Clear all corrections
```

Execution always opens a final file-by-file review. After approved copies are created, StudySort shows a report containing each filename, copy status, and destination under the selected `_StudySort` folder.

## Safety and privacy

- The app accesses only a folder the student explicitly chooses.
- Drive scans skip protected system folders, application folders, hidden folders, and existing `_StudySort` output.
- Large scans stop at 25,000 files to keep the browser responsive.
- Suggested empty folders can be created without moving or copying any files.
- Individual file selection works even when the original folders are empty or scattered across locations.
- It previews every destination before organizing.
- It creates copies inside `_StudySort`; original files are not moved or deleted.
- Student profile and learned corrections are stored only in browser `localStorage`.
- Browsers without directory write access can still generate a read-only preview.
- If two planned files would land in the same folder with the same name, the later copy is automatically renamed (e.g. `notes (2).pdf`) instead of silently overwriting the first.

## Personalization

Classification combines course names and codes, extracted first-page content, filename and path keywords, file extensions, folder style, chat changes, and corrections made in the review table. Review-table corrections are remembered on the device for future scans, scoped to the course the correction was made in, and skip generic words (like "notes" or "assignment") so one correction won't misclassify unrelated files. Files the analyzer is least sure about are flagged "Needs review" and sorted to the top of the review table.
