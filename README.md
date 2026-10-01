# StudySort

StudySort organizes a student's files into course folders. It runs entirely on your computer:

- **Live Downloads watcher.** A small Python service watches your Downloads folder. When a download finishes, StudySort works out the course and file type and shows the file's whole journey in a live flow chart. With your approval, it copies the file into `_StudySort/<Course>/<Type>/`.
- **Chat organizer.** In the browser dashboard you can pick files, a folder, or a whole drive. StudySort suggests a folder plan, you adjust it in chat or in a review table, and it creates organized copies.

Both parts use the same classifier and follow the same safety rule: **originals are copied, never moved or overwritten** (unless you start the watcher with `--move`).

## How it works

```
┌────────────────────────── your computer ───────────────────────────┐
│                                                                    │
│  Downloads/            Python service (app_server.py, 127.0.0.1)   │
│  CS101_hw.pdf ──────►  watchdog ─► wait until stable ─► classify   │
│                                │                       │           │
│                                ▼                       ▼           │
│                         SQLite history ◄──── plan + approval ──┐   │
│                                │                               │   │
│                     Server-Sent Events                         │   │
│                                ▼                               │   │
│              Browser dashboard (http://127.0.0.1:4173)         │   │
│              "View file flow" ─────── Approve / Retry / Cancel ┘   │
│                                                                    │
│  Downloads/_StudySort/CS101/Assignments/CS101_hw.pdf  ◄── copy     │
└────────────────────────────────────────────────────────────────────┘
```

Each file in the flow chart is shown as one card:

```
[Source]                 [Detected course]  [Detected type]  [Planned destination]                        [Status]
Downloads/CS101_hw.pdf → CS101            → Assignments    → Downloads/_StudySort/CS101/Assignments/... → Copied successfully
```

On large screens the steps run left to right. On phones they stack vertically. Status colors:

| Status | Color |
| --- | --- |
| Detected | blue |
| Analyzing | purple |
| Awaiting approval | orange |
| Copying | blue, animated |
| Copied or Moved | green |
| Failed | red |
| Cancelled | gray |

## Requirements

- Python 3.10 or newer
- A current Chrome or Edge, if you want to use the chat organizer's "choose folder" and "create copies" features. The live flow chart works in any modern browser.
- Node.js 20 or newer, only for running the JavaScript tests

## Install

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux
pip install -r requirements.txt
```

## Start the service

```bash
python app_server.py
```

Then open **http://127.0.0.1:4173**.

With no options, StudySort watches your own Downloads folder (`~/Downloads`). To watch another folder, pass `--watch`:

```bash
python app_server.py --watch "C:\Users\User\Downloads"
python app_server.py --watch "D:\School\Inbox"
```

| Option | Default | What it does |
| --- | --- | --- |
| `--watch PATH` | `~/Downloads` | Folder to watch. It must already exist. |
| `--auto-organize` | off | Copies each file as soon as it is classified, with no approval step. |
| `--move` | off | Moves files instead of copying them. The original is deleted only after a verified copy. |
| `--port` | `4173` | Dashboard port. |
| `--host` | `127.0.0.1` | Network interface to bind. Change it only if you understand that this exposes your file history to your network. |
| `--data-dir` | `./data` | Where `history.sqlite3` (file history and student profile) is kept. |

Press `Ctrl+C` to stop the service.

## Using the flow chart

1. Click **View file flow** in the right-hand panel. On a phone, open the panel with the profile icon first.
2. Download a file or save one into the watched folder. A card appears straight away, with no page refresh.
3. The card moves through **Detected → Analyzing → Awaiting approval**.
4. Check the course, type, and planned destination, then click **Approve**. The card moves through **Copying → Copied successfully** and shows the final location.

You can also:

- Search by name, course, type, or path, and filter by status, course, or type. The chart shows the 100 most recent matches.
- Click **Cancel** on a file that is still waiting.
- Click **Retry** on a failed file. If a failed file reappears in the folder, it is retried automatically on its existing card.
- Click **Clear history** to forget the history. This never deletes any files.

History is stored in SQLite and reloads when the service restarts. Files that were still waiting for approval stay waiting. Files that were partway through processing when the service stopped are marked failed so you can retry them.

The courses StudySort recognizes come from the chat onboarding ("Which courses are you taking?"). The dashboard sends them to the service, so set up your profile once before relying on the watcher.

## Safe copying

- **Copy by default.** The original stays in Downloads.
- **Never overwrites.** If the destination already has `notes.pdf`, the copy becomes `notes (2).pdf`, then `notes (3).pdf`, and so on. StudySort checks both files on disk and files being copied at the same moment.
- **Atomic copy.** Each file is written to a hidden temporary file in the destination folder first. It is renamed to its final name only after the copy finishes and the size matches. The rename refuses to replace an existing file.
- **Waits for downloads to finish.** A file is processed only once:
  - its size and modified time have stopped changing across several checks,
  - it can be opened for reading,
  - no `.crdownload`, `.part`, `.tmp`, or `.download` file for it is still being written.
  If that hasn't happened within 2 minutes, the file is marked *File still downloading* and can be retried.
- **Ignores** folders, hidden files, Office lock files (`~$…`), in-progress downloads, and everything inside `_StudySort`, so StudySort never processes its own output.
- **One failure doesn't stop anything.** The card shows a plain-language error and the watcher keeps running. Possible errors are:
  - permission denied
  - file disappeared
  - still downloading
  - destination unavailable
  - copy failed
  - unsupported or corrupted document (StudySort then classifies the file by name)
- The chat organizer follows the same rules. Its copies never overwrite files already in the chosen `_StudySort` folder, and a failed copy is cleaned up.

## Auto-organize

Without `--auto-organize`, every new file waits in **Awaiting approval** until you approve it in the dashboard. With `--auto-organize`, StudySort copies each file as soon as it is classified. Copies still never overwrite anything. The flow chart still shows every step, so you can check where each file went.

## How files are classified

StudySort looks at the filename, the file's relative path, its extension, and the opening text of PDF, DOCX, PPTX, TXT, Markdown, CSV, and HTML files. It compares these against your courses and any corrections you've made.

- **Whole words only.** `example.pdf` does not match "exam", and `latest_notes.txt` does not match "test".
- **Course codes** such as `CS101`, `CS 101`, `MEE-323`, or `phy101` are matched exactly. A code that isn't one of your courses is still used as the folder name, rather than "General".
- **Course names** must match in full. "Data Structures" matches `data_structures_hw.pdf` or `structures and data notes`, but not `data_export.csv`.
- **Weighting.** A match in the filename counts more than one in the folder path, and a path match counts more than one in the document text. When keywords conflict, Solutions wins over Exams, and so on.
- **Learned corrections.** When you change a file's type in the review table, StudySort remembers the most distinctive word in its filename and applies that correction to future files.

Every result includes a course, a type, a confidence level (high, medium, or low), an explanation such as `Course code "CS101" found in filename; Keyword "assignment" found in filename`, and the planned destination.

## Privacy

- Everything runs locally. No file contents, names, or paths are sent to any external service.
- The server listens only on `127.0.0.1` by default. It refuses requests that carry another website's `Origin` header, and requests addressed to a host name other than localhost (this blocks DNS-rebinding attacks).
- Your profile, corrections, and file history are stored in `data/history.sqlite3`. Your profile is also cached in your browser's `localStorage`. Clearing history removes database rows only.

## Project layout

```
app_server.py          entry point: argument parsing, starts the watcher and the web server
studysort/
  classify.py          the single course/type classifier
  extract.py           local text extraction (pypdf; DOCX and PPTX via the standard library)
  fileops.py           ignore rules, download-stability check, never-overwrite copy
  service.py           watchdog handler and the detected → copied state machine
  server.py            FastAPI routes and the Server-Sent Events stream
  store.py             SQLite history and profile
frontend/              dashboard (index.html, app.js, flow.js, styles.css, vendor/, assets/)
tests/                 pytest suites; tests/js holds the Node tests for the flow chart
```

### API

All endpoints are served on `127.0.0.1` only.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/status` | Watched folder, whether the watcher is alive, mode, and counts |
| GET | `/api/files` | Recent file history, newest first |
| DELETE | `/api/files` | Clear history (does not delete files) |
| GET | `/api/files/{id}` | One file |
| POST | `/api/files/{id}/approve` | Copy a file that is awaiting approval |
| POST | `/api/files/{id}/retry` | Retry a failed file |
| POST | `/api/files/{id}/cancel` | Cancel a file that is detected, analyzing, or awaiting approval |
| GET | `/api/events/stream` | Server-Sent Events: `file`, `status`, and `cleared` events |
| GET / PUT | `/api/profile` | Student profile (courses, folder style, corrections) |
| POST | `/api/classify` | Classify files for the chat organizer |
| POST | `/api/corrections` | Remember a correction made in the review table |

## Testing

```bash
pip install -r requirements-dev.txt
pytest -q                 # Python: classifier, file safety, watcher, API, live events
ruff check .              # Python lint

npm ci
npm test                  # Node: flow-chart rendering, filtering, search
npm run lint              # ESLint
npm run check             # JavaScript syntax check
```

Filesystem tests run only in temporary folders, never in your real Downloads folder. GitHub Actions runs the Python tests on Ubuntu and Windows, plus the JavaScript checks. It also starts the real service against a temporary folder and confirms that a new file reaches *Awaiting approval*.

## Known limitations

- **A web page cannot watch folders by itself.** The live flow chart needs `app_server.py` to be running. If the service stops, the dashboard shows a "Server disconnected" banner and reconnects automatically when the service comes back.
- **The watcher only sees new files.** Files already in the folder when the service starts are not processed. Only the top level of the watched folder is watched, not its subfolders.
- **The chat organizer needs Chrome or Edge to write files.** Choosing a writable destination uses the File System Access API. Other browsers can preview a plan but cannot create copies. Some managed school devices block picking a whole drive; choosing a top-level folder such as `D:\School` works instead.
- **No OCR.** Scanned or image-only PDFs have no readable text, so they are classified by filename only.
- **Course and type can't be changed in the flow chart.** To change them before approving, use the review table in the chat organizer, or record a correction there so future files are classified differently.
- **Network shares.** On filesystems without hard links (FAT, exFAT, some network shares) on macOS or Linux, the final rename falls back to check-then-rename. StudySort still never overwrites its own copies, but in theory another program could create the same file name in the instant between the check and the rename.
