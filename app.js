const STORAGE_KEY = "studysort-profile-v1";

const FILE_TYPES = [
  "Assignments",
  "Lecture Slides",
  "Lecture Notes",
  "Questions",
  "Solutions",
  "Study Materials",
  "Exams & Quizzes",
  "Projects",
  "Syllabi",
  "Reading",
  "Documents",
  "Presentations",
  "Spreadsheets",
  "Images",
  "Videos",
  "Audio",
  "Archives",
  "Code",
  "Installers",
  "Other",
];

const EXTENSION_TYPES = {
  Documents: ["doc", "docx", "odt", "rtf", "txt", "md"],
  Presentations: ["ppt", "pptx", "key", "odp"],
  Spreadsheets: ["xls", "xlsx", "csv", "ods"],
  Images: ["jpg", "jpeg", "png", "gif", "webp", "heic", "svg"],
  Videos: ["mp4", "mov", "mkv", "avi", "webm", "m4v"],
  Audio: ["mp3", "wav", "m4a", "aac", "flac", "ogg"],
  Archives: ["zip", "rar", "7z", "tar", "gz"],
  Code: ["js", "ts", "jsx", "tsx", "py", "java", "c", "cpp", "cs", "html", "css", "sql", "ipynb"],
  Installers: ["exe", "msi", "iso", "dmg", "pkg"],
};

const MAX_SCAN_FILES = 25000;
const MAX_DRIVE_CONTENT_FILES = 300;
const CONTENT_EXTENSIONS = new Set(["pdf", "pptx", "docx", "txt", "md", "csv", "html", "htm"]);
let pdfLibraryPromise;
const SKIPPED_DIRECTORY_NAMES = new Set([
  "$recycle.bin",
  "system volume information",
  "recovery",
  "windowsapps",
  "program files",
  "program files (x86)",
  "programdata",
  "node_modules",
  ".git",
  "_studysort",
]);

const TYPE_RULES = [
  { type: "Solutions", words: ["worked solutions", "worked solution", "answer key", "model answers", "model answer", "solutions", "solution"] },
  { type: "Questions", words: ["practice questions", "practice problems", "question bank", "questions", "question", "problem set", "exercises", "exercise"] },
  { type: "Syllabi", words: ["syllabus", "syllabi", "course outline", "schedule"] },
  { type: "Exams & Quizzes", words: ["exam", "quiz", "midterm", "final", "test", "practice test"] },
  { type: "Assignments", words: ["assignment", "homework", "worksheet", "problem set", "pset", "submission"] },
  { type: "Projects", words: ["project", "presentation", "capstone", "report", "portfolio"] },
  { type: "Lecture Slides", words: ["lecture slides", "learning objectives", "slide deck", "slides"] },
  { type: "Lecture Notes", words: ["lecture notes", "class notes", "notes", "lecture", "week", "lesson"] },
  { type: "Reading", words: ["reading", "chapter", "textbook", "article", "paper", "journal"] },
  { type: "Study Materials", words: ["study guide", "flashcard", "revision", "review", "summary", "cheat sheet"] },
];

const TYPE_PRIORITY = {
  Solutions: 60,
  Questions: 50,
  "Exams & Quizzes": 40,
  Syllabi: 35,
  Assignments: 30,
  "Lecture Slides": 25,
};

const GENERIC_TOKENS = new Set(
  TYPE_RULES.flatMap((rule) => rule.words.join(" ").split(/[^a-z0-9]+/))
    .concat([
      "file", "files", "copy", "final", "draft", "new", "old", "untitled", "document",
      "scan", "page", "week", "class", "course", "unit", "part", "version", "updated",
    ])
    .filter(Boolean),
);

const LEVELS = ["High school", "College", "University", "Graduate school"];
const STYLES = ["By course, then type", "By course, then semester", "By type, then course"];

const state = {
  step: "name",
  profile: loadProfile(),
  directoryHandle: null,
  scannedFiles: [],
  scanStats: { skipped: 0, limited: false },
  contentStats: { attempted: 0, analyzed: 0, failed: 0, limited: false },
  lastResults: [],
  sourceMode: "folder",
  sourceLabel: "",
  destinationName: "",
  busy: false,
};

const elements = {
  messages: document.querySelector("#messages"),
  suggestions: document.querySelector("#suggestions"),
  composer: document.querySelector("#composer"),
  input: document.querySelector("#message-input"),
  restart: document.querySelector("#restart-button"),
  filesInput: document.querySelector("#files-input"),
  folderInput: document.querySelector("#folder-input"),
  profileName: document.querySelector("#profile-name"),
  profileLevel: document.querySelector("#profile-level"),
  profileCourses: document.querySelector("#profile-courses"),
  profileStyle: document.querySelector("#profile-style"),
  fileCount: document.querySelector("#file-count"),
  emptyPlan: document.querySelector("#empty-plan"),
  planContent: document.querySelector("#plan-content"),
  folderName: document.querySelector("#folder-name"),
  folderSummary: document.querySelector("#folder-summary"),
  folderCount: document.querySelector("#folder-count"),
  suggestedFolderList: document.querySelector("#suggested-folder-list"),
  categoryList: document.querySelector("#category-list"),
  chooseDestinationButton: document.querySelector("#choose-destination-button"),
  createFoldersButton: document.querySelector("#create-folders-button"),
  organizeButton: document.querySelector("#organize-button"),
  reviewModal: document.querySelector("#review-modal"),
  reviewBody: document.querySelector("#review-table-body"),
  reviewSummary: document.querySelector("#review-summary"),
  closeReview: document.querySelector("#close-review-button"),
  cancelReview: document.querySelector("#cancel-review-button"),
  confirmOrganize: document.querySelector("#confirm-organize-button"),
  reportModal: document.querySelector("#report-modal"),
  reportBody: document.querySelector("#report-table-body"),
  reportSummary: document.querySelector("#report-summary"),
  closeReport: document.querySelector("#close-report-button"),
  doneReport: document.querySelector("#done-report-button"),
  mobileProfile: document.querySelector("#mobile-profile-button"),
  closeProfile: document.querySelector("#close-profile-button"),
  organizerPanel: document.querySelector("#organizer-panel"),
  toast: document.querySelector("#toast"),
  appShell: document.querySelector(".app-shell"),
};

function defaultProfile() {
  return { name: "", level: "", courses: [], style: "", corrections: {} };
}

function loadProfile() {
  try {
    return { ...defaultProfile(), ...JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}") };
  } catch {
    return defaultProfile();
  }
}

function saveProfile() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state.profile));
  renderProfile();
}

function renderProfile() {
  elements.profileName.textContent = state.profile.name || "Not set";
  elements.profileLevel.textContent = state.profile.level || "Not set";
  elements.profileCourses.textContent = state.profile.courses.length ? state.profile.courses.join(", ") : "Not set";
  elements.profileStyle.textContent = state.profile.style || "Not set";
}

function refreshIcons() {
  if (window.lucide) window.lucide.createIcons();
}

function addMessage(text, sender = "assistant", options = {}) {
  const row = document.createElement("div");
  row.className = `message-row ${sender}`;

  if (sender === "assistant") {
    const avatar = document.createElement("span");
    avatar.className = "assistant-avatar";
    avatar.setAttribute("aria-hidden", "true");
    avatar.innerHTML = '<i data-lucide="sparkles"></i>';
    row.appendChild(avatar);
  }

  const bubble = document.createElement("div");
  bubble.className = "message";
  const paragraph = document.createElement("p");
  paragraph.textContent = text;
  bubble.appendChild(paragraph);

  const actions = options.actions || (options.action ? [options.action] : []);
  if (actions.length) {
    const actionGroup = document.createElement("div");
    actionGroup.className = "message-actions";
    actions.forEach((actionConfig) => {
      const action = document.createElement("button");
      action.className = "message-action";
      action.type = "button";
      action.innerHTML = `<i data-lucide="${actionConfig.icon}"></i><span>${escapeHtml(actionConfig.label)}</span>`;
      action.addEventListener("click", actionConfig.onClick);
      actionGroup.appendChild(action);
    });
    bubble.appendChild(actionGroup);
  }

  row.appendChild(bubble);
  elements.messages.appendChild(row);
  elements.messages.scrollTop = elements.messages.scrollHeight;
  refreshIcons();
}

function showSuggestions(items = []) {
  elements.suggestions.innerHTML = "";
  items.forEach((label) => {
    const button = document.createElement("button");
    button.className = "suggestion-button";
    button.type = "button";
    button.textContent = label;
    button.addEventListener("click", () => handleReply(label));
    elements.suggestions.appendChild(button);
  });
}

function startConversation() {
  elements.messages.innerHTML = "";
  showSuggestions([]);

  if (state.profile.name && state.profile.courses.length && state.profile.style) {
    state.step = "ready";
    addMessage(`Welcome back, ${state.profile.name}. I remember your ${state.profile.courses.length} courses and how you like them organized.`);
    showReadyPrompt();
    return;
  }

  state.step = "name";
  addMessage("Hi, I'm StudySort. I'll learn how you study, then organize a folder around your courses. What should I call you?");
  elements.input.placeholder = "Your name";
  elements.input.focus();
}

function handleReply(rawText) {
  const text = rawText.trim();
  if (!text || state.busy) return;

  addMessage(text, "user");
  elements.input.value = "";
  showSuggestions([]);

  switch (state.step) {
    case "name":
      state.profile.name = cleanName(text);
      state.step = "level";
      saveProfile();
      addMessage(`Nice to meet you, ${state.profile.name}. What level are you studying at?`);
      showSuggestions(LEVELS);
      elements.input.placeholder = "For example: university";
      break;
    case "level":
      state.profile.level = normalizeChoice(text, LEVELS);
      state.step = "courses";
      saveProfile();
      addMessage("Which courses are you taking? Separate them with commas. Course codes work too, like CS101 or BIO 204.");
      elements.input.placeholder = "Calculus, CS101, World History";
      break;
    case "courses":
      state.profile.courses = parseCourses(text);
      if (!state.profile.courses.length) {
        addMessage("I didn't catch a course name. Try entering one or more courses separated by commas.");
        return;
      }
      state.step = "style";
      saveProfile();
      addMessage(`Got them: ${naturalList(state.profile.courses)}. How should I build your folders?`);
      showSuggestions(STYLES);
      elements.input.placeholder = "Choose a folder style";
      break;
    case "style":
      state.profile.style = normalizeChoice(text, STYLES);
      state.step = "ready";
      saveProfile();
      addMessage(`Perfect. I'll organize for ${state.profile.name} using "${state.profile.style}." You can correct any guess before files are copied.`);
      showReadyPrompt();
      break;
    case "ready":
      handleReadyMessage(text);
      break;
    default:
      showReadyPrompt();
  }
}

function showReadyPrompt() {
  elements.input.placeholder = "Ask me to scan or update your profile";
  addMessage("Select individual files, or scan a study folder or data drive. I'll show you the suggested folder structure before asking where to create it.", "assistant", {
    actions: [
      { label: "Select files", icon: "files", onClick: chooseFiles },
      { label: "Choose folder or drive", icon: "folder-search", onClick: chooseFolder },
    ],
  });
  showSuggestions(["Change my courses", "Change folder style"]);
}

function handleReadyMessage(text) {
  const lower = text.toLowerCase();
  if (handleCorrectionCommand(text, lower)) {
    return;
  }
  if (state.scannedFiles.length && handlePlanCommand(text)) {
    return;
  }
  if (lower.includes("course") || lower.includes("class") || lower.includes("subject")) {
    state.step = "courses";
    addMessage("Tell me your updated course list, separated by commas.");
    elements.input.placeholder = "Calculus, CS101, World History";
  } else if (lower.includes("file") && !lower.includes("style")) {
    chooseFiles();
  } else if (lower.includes("scan") || lower.includes("choose") || lower.includes("start") || lower.includes("drive")) {
    chooseFolder();
  } else if (lower.includes("style") || lower.includes("organize")) {
    state.step = "style";
    addMessage("Which folder structure should I use?");
    showSuggestions(STYLES);
  } else {
    addMessage("I can scan selected files, a folder, or a data drive. I can also change your courses or folder style. What would you like to do?");
    showSuggestions(["Select files", "Scan folder or drive", "Change my courses", "Change folder style"]);
  }
}

function handleCorrectionCommand(text, lower) {
  if (/^(show|list|view)\s+(my\s+)?corrections?/.test(lower)) {
    describeCorrections();
    return true;
  }
  if (/^(clear|forget)\s+all\s+corrections?/.test(lower)) {
    state.profile.corrections = {};
    saveProfile();
    addMessage("I cleared all learned corrections. Future files will rely on the course and category rules again.");
    return true;
  }
  const forgetMatch = text.match(/^(?:clear|forget)\s+correction(?:s)?\s+(?:for\s+)?(.+)$/i);
  if (forgetMatch) {
    const query = cleanCommandPart(forgetMatch[1]).toLowerCase();
    const tokens = Object.keys(state.profile.corrections || {}).filter(
      (token) => token.includes(query) || query.includes(token),
    );
    if (!tokens.length) {
      addMessage(`I couldn't find a learned correction matching "${query}." Say "Show corrections" to see what I've learned.`);
      return true;
    }
    tokens.forEach((token) => delete state.profile.corrections[token]);
    saveProfile();
    addMessage(`Forgot ${tokens.length} learned ${pluralize("correction", tokens.length)} matching "${query}."`);
    return true;
  }
  return false;
}

function describeCorrections() {
  const entries = Object.entries(state.profile.corrections || {});
  if (!entries.length) {
    addMessage("I haven't learned any corrections yet. When you change a file's course or type in the review table, I'll remember it for similar filenames.");
    return;
  }
  const lines = entries.slice(0, 15).map(([token, value]) => {
    const info = typeof value === "string" ? { type: value, course: null } : value;
    return `- "${token}" -> ${info.type}${info.course ? ` (${info.course})` : ""}`;
  });
  if (entries.length > 15) lines.push(`- ...and ${entries.length - 15} more`);
  addMessage(`Here's what I've learned from your corrections:\n${lines.join("\n")}\n\nSay "Forget correction <word>" to remove one, or "Clear all corrections" to reset.`);
}

function showPlanActions() {
  elements.input.placeholder = 'Customize the plan, for example: Move quiz.pdf to CS101 / Questions';
  showSuggestions(["Show plan", "Review files", "Execute plan"]);
}

function handlePlanCommand(text) {
  const lower = text.toLowerCase().trim();

  if (/^(show|view).*(plan|folder)/.test(lower)) {
    describePlanInChat();
    return true;
  }
  if (lower.includes("where") || lower.includes("location")) {
    if (state.lastResults.length) openReport();
    else describePlannedLocations();
    return true;
  }
  if (lower.includes("review")) {
    openReview();
    return true;
  }
  if (lower.includes("create") && lower.includes("folder")) {
    if (state.directoryHandle) createSuggestedFolders();
    else requestDestination("I can create the suggested empty folders after you choose their destination.");
    return true;
  }
  if (/^(execute|apply|approve|confirm)/.test(lower) || lower.includes("looks good") || lower.includes("copy files")) {
    requestExecution();
    return true;
  }
  if (/^rename\s+/i.test(text)) {
    renamePlanCategory(text);
    return true;
  }
  if (/^(move|put)\s+/i.test(text)) {
    movePlanFiles(text);
    return true;
  }
  return false;
}

function describePlanInChat() {
  const folders = [...getSuggestedFolders().entries()].sort((a, b) => b[1] - a[1]);
  const lines = folders.slice(0, 10).map(([path, count]) => `- ${path} (${count} ${pluralize("file", count)})`);
  if (folders.length > 10) lines.push(`- ...and ${folders.length - 10} more folders`);
  addMessage(`Here is the current plan:\n${lines.join("\n")}\n\nYou can say "Rename Questions to Practice Questions" or "Move quiz.pdf to CS101 / Questions."`, "assistant", {
    actions: [
      { label: "Review every file", icon: "list-tree", onClick: openReview },
      { label: "Execute plan", icon: "copy-check", onClick: requestExecution },
    ],
  });
  showPlanActions();
}

function describePlannedLocations() {
  const lines = state.scannedFiles.slice(0, 8).map((file) => {
    const location = state.destinationName ? displayDestination(file) : `[destination]/${destinationFor(file)}`;
    return `- ${file.name} -> ${location}`;
  });
  if (state.scannedFiles.length > 8) lines.push(`- ...and ${state.scannedFiles.length - 8} more files`);
  addMessage(`These are the planned locations:\n${lines.join("\n")}\n\nNo copies have been created yet.`);
  showPlanActions();
}

function requestDestination(message) {
  addMessage(message, "assistant", {
    action: { label: "Choose destination", icon: "folder-output", onClick: chooseDestinationFolder },
  });
}

function requestExecution() {
  if (!state.directoryHandle) {
    requestDestination("The plan is ready, but I need a destination before execution. After you choose one, I will still show the final file-by-file review.");
    return;
  }
  addMessage("I will show the complete placement list now. Copies are created only after you press the final approval button.");
  openReview();
}

function cleanCommandPart(value) {
  return value.trim().replace(/^["']|["']$/g, "").trim();
}

function findCaseInsensitive(items, value) {
  const lower = value.toLowerCase();
  return items.find((item) => item.toLowerCase() === lower);
}

function renamePlanCategory(text) {
  const match = text.match(/^rename\s+(.+?)\s+to\s+(.+)$/i);
  if (!match) {
    addMessage('Use a command such as "Rename Questions to Practice Questions."');
    return;
  }

  const source = cleanCommandPart(match[1]);
  const target = cleanCommandPart(match[2]).slice(0, 60);
  const sourceType = findCaseInsensitive([...new Set(state.scannedFiles.map((file) => file.type))], source);
  const sourceCourse = findCaseInsensitive([...new Set(state.scannedFiles.map((file) => file.course))], source);
  let changed = 0;

  if (sourceType) {
    state.scannedFiles.forEach((file) => {
      if (file.type === sourceType) {
        file.type = target;
        changed += 1;
      }
    });
    if (!FILE_TYPES.includes(target)) FILE_TYPES.push(target);
  } else if (sourceCourse) {
    state.scannedFiles.forEach((file) => {
      if (file.course === sourceCourse) {
        file.course = target;
        changed += 1;
      }
    });
  }

  if (!changed) {
    addMessage(`I could not find a course or category named "${source}." Say "Show plan" to see the current names.`);
    return;
  }
  renderPlan(state.sourceLabel, Boolean(state.directoryHandle));
  addMessage(`Updated ${changed} ${pluralize("file", changed)}: "${source}" is now "${target}." Nothing has been copied yet.`);
  showPlanActions();
}

function movePlanFiles(text) {
  const match = text.match(/^(?:move|put)\s+(.+?)\s+(?:to|into|in)\s+(.+)$/i);
  if (!match) {
    addMessage('Use a command such as "Move quiz.pdf to CS101 / Questions."');
    return;
  }

  let source = cleanCommandPart(match[1]).replace(/^all\s+/i, "");
  const target = cleanCommandPart(match[2]);
  const sourceLower = source.toLowerCase();
  const matches = state.scannedFiles.filter((file) =>
    file.name.toLowerCase().includes(sourceLower) ||
    file.type.toLowerCase() === sourceLower ||
    file.course.toLowerCase() === sourceLower,
  );
  if (!matches.length) {
    addMessage(`I could not find a file, course, or category matching "${source}." Say "Review files" to see the exact names.`);
    return;
  }

  const parts = target.split(/\s*[\/>]\s*/).map(cleanCommandPart).filter(Boolean);
  let targetCourse = parts.map((part) => findCaseInsensitive(["General", ...state.profile.courses], part)).find(Boolean);
  let targetType = parts.map((part) => findCaseInsensitive(FILE_TYPES, part)).find(Boolean);

  if (parts.length >= 2) {
    targetCourse ||= parts[0];
    targetType ||= parts[1];
  } else if (!targetCourse) {
    targetType ||= parts[0];
  }

  matches.forEach((file) => {
    if (targetCourse) file.course = targetCourse;
    if (targetType) file.type = targetType;
  });
  if (targetType && !FILE_TYPES.includes(targetType)) FILE_TYPES.push(targetType);
  renderPlan(state.sourceLabel, Boolean(state.directoryHandle));
  addMessage(`Moved ${matches.length} planned ${pluralize("file", matches.length)} to ${targetCourse ? `${targetCourse} / ` : ""}${targetType || matches[0].type}. This changed only the plan.`);
  showPlanActions();
}

function chooseFiles() {
  if (state.busy) return;
  showSuggestions([]);
  elements.filesInput.click();
}

async function chooseFolder() {
  if (state.busy) return;
  showSuggestions([]);

  if ("showDirectoryPicker" in window) {
    try {
      const handle = await window.showDirectoryPicker({ mode: "readwrite" });
      state.directoryHandle = handle;
      state.sourceMode = "folder";
      state.sourceLabel = handle.name;
      state.destinationName = handle.name;
      await scanDirectoryHandle(handle);
      return;
    } catch (error) {
      if (error.name === "AbortError") {
        addMessage("No problem. Nothing was opened or changed.");
        return;
      }
      addMessage("I couldn't open that folder with write permission. You can still choose files for a read-only preview.");
    }
  }

  elements.folderInput.click();
}

async function scanDirectoryHandle(handle) {
  setBusy(true);
  addMessage(`I'm scanning "${handle.name}" now. On a large drive this can take a little while. I'll skip protected, hidden, application, and existing _StudySort folders.`);
  try {
    const entries = [];
    const stats = { skipped: 0, limited: false };
    await walkDirectory(handle, "", entries, stats);
    state.scanStats = stats;
    const analysis = await analyzeEntries(entries, false);
    state.scannedFiles = analysis.files;
    state.contentStats = analysis.stats;
    renderPlan(handle.name, true);
    const uncertain = state.scannedFiles.filter((file) => file.confidence === "low").length;
    const folderCount = getSuggestedFolders().size;
    const scanNote = stats.limited
      ? ` I stopped at ${MAX_SCAN_FILES.toLocaleString()} files so the browser stays responsive.`
      : stats.skipped
        ? ` I safely skipped ${stats.skipped} inaccessible or protected ${pluralize("folder", stats.skipped)}.`
        : "";
    const contentNote = analysis.stats.analyzed
      ? ` I read the first page, first slide, or opening section of ${analysis.stats.analyzed} supported ${pluralize("file", analysis.stats.analyzed)}.`
      : "";
    const contentLimitNote = analysis.stats.limited
      ? ` Content reading was limited to ${MAX_DRIVE_CONTENT_FILES} files; remaining files use names and paths.`
      : "";
    addMessage(`I found ${state.scannedFiles.length} ${pluralize("file", state.scannedFiles.length)} and suggest ${folderCount} ${pluralize("folder", folderCount)}.${contentNote}${contentLimitNote}${scanNote} ${uncertain ? `${uncertain} files need a closer look. ` : ""}Nothing has been created or moved yet.`);
    showPlanActions();
  } catch (error) {
    addMessage(`I couldn't finish scanning that folder: ${error.message || "permission was interrupted"}.`);
  } finally {
    setBusy(false);
  }
}

async function walkDirectory(handle, relativePath, entries, stats) {
  if (entries.length >= MAX_SCAN_FILES) {
    stats.limited = true;
    return;
  }

  try {
    for await (const [name, child] of handle.entries()) {
      if (entries.length >= MAX_SCAN_FILES) {
        stats.limited = true;
        return;
      }
      if (name.startsWith(".") || SKIPPED_DIRECTORY_NAMES.has(name.toLowerCase())) {
        if (child.kind === "directory") stats.skipped += 1;
        continue;
      }
      const path = relativePath ? `${relativePath}/${name}` : name;
      if (child.kind === "directory") {
        await walkDirectory(child, path, entries, stats);
      } else {
        entries.push({ name, path, file: null, handle: child });
      }
    }
  } catch {
    stats.skipped += 1;
  }
}

function fileExtension(name) {
  return name.includes(".") ? name.split(".").pop().toLowerCase() : "";
}

function supportsContentAnalysis(entry) {
  return CONTENT_EXTENSIONS.has(fileExtension(entry.name));
}

async function getEntryFile(entry) {
  if (entry.file) return entry.file;
  if (entry.handle) return entry.handle.getFile();
  throw new Error("File is no longer available");
}

async function loadPdfLibrary() {
  if (!pdfLibraryPromise) {
    pdfLibraryPromise = import("./vendor/pdf.min.mjs").then((pdfjs) => {
      pdfjs.GlobalWorkerOptions.workerSrc = new URL("./vendor/pdf.worker.min.mjs", window.location.href).href;
      return pdfjs;
    });
  }
  return pdfLibraryPromise;
}

async function extractPdfFirstPage(file) {
  const pdfjs = await loadPdfLibrary();
  const standardFontDataUrl = new URL("./vendor/pdf-standard-fonts/", window.location.href).href;
  const documentTask = pdfjs.getDocument({
    data: new Uint8Array(await file.arrayBuffer()),
    standardFontDataUrl,
  });
  const pdf = await documentTask.promise;
  try {
    const page = await pdf.getPage(1);
    const content = await page.getTextContent();
    return content.items.map((item) => item.str || "").join(" ");
  } finally {
    await pdf.destroy();
  }
}

function extractXmlText(xmlText) {
  const xml = new DOMParser().parseFromString(xmlText, "application/xml");
  if (xml.querySelector("parsererror")) throw new Error("Document XML could not be read");
  return Array.from(xml.getElementsByTagNameNS("*", "t"))
    .map((node) => node.textContent || "")
    .join(" ");
}

async function extractOfficeOpening(file, extension) {
  if (!window.JSZip) throw new Error("Office document parser did not load");
  const zip = await window.JSZip.loadAsync(await file.arrayBuffer());
  const internalPath = extension === "pptx" ? "ppt/slides/slide1.xml" : "word/document.xml";
  const part = zip.file(internalPath);
  if (!part) throw new Error(extension === "pptx" ? "First slide was not found" : "Document text was not found");
  return extractXmlText(await part.async("string"));
}

async function extractPreviewText(entry) {
  const extension = fileExtension(entry.name);
  const file = await getEntryFile(entry);
  let text = "";
  let source = "Filename and path";

  if (extension === "pdf") {
    text = await extractPdfFirstPage(file);
    source = "First PDF page scanned";
  } else if (extension === "pptx") {
    text = await extractOfficeOpening(file, extension);
    source = "First PowerPoint slide scanned";
  } else if (extension === "docx") {
    text = await extractOfficeOpening(file, extension);
    source = "Opening Word section scanned";
  } else if (["html", "htm"].includes(extension)) {
    const html = await file.slice(0, 64000).text();
    text = new DOMParser().parseFromString(html, "text/html").body.textContent || "";
    source = "Opening document text scanned";
  } else {
    text = await file.slice(0, 64000).text();
    source = "Opening file text scanned";
  }

  return { text: text.replace(/\s+/g, " ").trim().slice(0, 12000), source };
}

async function analyzeEntries(entries, analyzeEverySupportedFile) {
  const files = entries.map((entry) =>
    classifyEntry({ ...entry, previewText: "", analysisSource: "Filename and path" }),
  );
  const supportedIndexes = entries
    .map((entry, index) => (supportsContentAnalysis(entry) ? index : -1))
    .filter((index) => index >= 0);
  const queue = analyzeEverySupportedFile ? supportedIndexes : supportedIndexes.slice(0, MAX_DRIVE_CONTENT_FILES);
  const stats = {
    attempted: queue.length,
    analyzed: 0,
    failed: 0,
    limited: supportedIndexes.length > queue.length,
  };

  let cursor = 0;
  async function worker() {
    while (cursor < queue.length) {
      const index = queue[cursor];
      cursor += 1;
      try {
        const preview = await extractPreviewText(entries[index]);
        files[index] = classifyEntry({
          ...entries[index],
          previewText: preview.text,
          analysisSource: preview.text ? preview.source : `${preview.source}; no readable text`,
        });
        stats.analyzed += 1;
      } catch {
        files[index] = classifyEntry({
          ...entries[index],
          previewText: "",
          analysisSource: "Content unavailable; used filename and path",
        });
        stats.failed += 1;
      }
    }
  }

  await Promise.all(Array.from({ length: Math.min(4, queue.length) }, () => worker()));
  return { files, stats };
}

elements.folderInput.addEventListener("change", async () => {
  const files = Array.from(elements.folderInput.files || []);
  if (!files.length) return;
  setBusy(true);
  addMessage(`I found ${files.length} files. I'm reading supported first pages and slides before I suggest folders.`);
  state.directoryHandle = null;
  state.sourceMode = "folder-preview";
  state.scanStats = { skipped: 0, limited: false };
  const entries = files
    .filter((file) => !file.name.startsWith(".") && !file.webkitRelativePath.includes("/_StudySort/"))
    .map((file) =>
      ({
        name: file.name,
        path: file.webkitRelativePath || file.name,
        file,
        handle: null,
      }),
    );
  const analysis = await analyzeEntries(entries, false);
  state.scannedFiles = analysis.files;
  state.contentStats = analysis.stats;
  const rootName = files[0].webkitRelativePath?.split("/")[0] || "Selected files";
  state.sourceLabel = rootName;
  state.destinationName = "";
  renderPlan(rootName, false);
  addMessage(`I analyzed ${state.scannedFiles.length} ${pluralize("file", state.scannedFiles.length)} and read content from ${analysis.stats.analyzed}. Choose a destination folder only when the plan looks right.`);
  showPlanActions();
  elements.folderInput.value = "";
  setBusy(false);
});

elements.filesInput.addEventListener("change", async () => {
  const files = Array.from(elements.filesInput.files || []);
  if (!files.length) return;
  setBusy(true);
  addMessage(`I'm analyzing all ${files.length} selected ${pluralize("file", files.length)}. For supported documents, I'll read page 1, slide 1, or the opening section.`);
  state.directoryHandle = null;
  state.sourceMode = "files";
  state.sourceLabel = `${files.length} selected ${pluralize("file", files.length)}`;
  state.destinationName = "";
  state.scanStats = { skipped: 0, limited: false };
  const entries = files
    .filter((file) => !file.name.startsWith("."))
    .map((file) => ({ name: file.name, path: file.name, file, handle: null }));
  const analysis = await analyzeEntries(entries, true);
  state.scannedFiles = analysis.files;
  state.contentStats = analysis.stats;
  renderPlan(state.sourceLabel, false);
  const folderCount = getSuggestedFolders().size;
  const failedNote = analysis.stats.failed ? ` ${analysis.stats.failed} could not be read internally and use their names instead.` : "";
  addMessage(`Analysis complete. I read content from ${analysis.stats.analyzed} supported ${pluralize("file", analysis.stats.analyzed)}, analyzed the remaining files by name, and suggest ${folderCount} ${pluralize("folder", folderCount)}.${failedNote} You can customize the plan here in chat before choosing a destination.`);
  showPlanActions();
  elements.filesInput.value = "";
  setBusy(false);
});

async function chooseDestinationFolder() {
  if (state.busy || !state.scannedFiles.length) return;
  if (!("showDirectoryPicker" in window)) {
    addMessage("This browser can preview the plan, but it cannot choose a writable destination. Open StudySort in Chrome or Edge on localhost to create folders or copies.");
    return;
  }

  try {
    const handle = await window.showDirectoryPicker({ mode: "readwrite" });
    state.directoryHandle = handle;
    state.destinationName = handle.name;
    renderPlan(state.sourceLabel, true);
    addMessage(`Destination set to "${handle.name}." The suggested folders will be created inside ${handle.name}/_StudySort, and your selected files remain unchanged until you approve copying.`, "assistant", {
      action: { label: "Review and execute", icon: "copy-check", onClick: requestExecution },
    });
    showPlanActions();
  } catch (error) {
    if (error.name === "AbortError") {
      addMessage("No destination selected. Your folder suggestions are still available, and no files were changed.");
      return;
    }
    addMessage(`I couldn't open that destination: ${error.message || "permission was interrupted"}.`);
  }
}

function classifyEntry(entry) {
  const searchable = `${entry.path} ${entry.name} ${entry.previewText || ""}`
    .toLowerCase()
    .replace(/[_\-.]+/g, " ")
    .replace(/\s+/g, " ");
  const compactSearchable = searchable.replace(/\s+/g, "");
  const extension = fileExtension(entry.name);
  let course = "General";
  let courseScore = 0;

  state.profile.courses.forEach((candidate) => {
    const aliases = courseAliases(candidate);
    const score = aliases.reduce((best, alias) => {
      const compactAlias = alias.replace(/\s+/g, "");
      return searchable.includes(alias) || compactSearchable.includes(compactAlias)
        ? Math.max(best, compactAlias.length)
        : best;
    }, 0);
    if (score > courseScore) {
      course = candidate;
      courseScore = score;
    }
  });

  let type = "Other";
  let typeScore = 0;
  TYPE_RULES.forEach((rule) => {
    const wordScore = rule.words.reduce((best, word) => (searchable.includes(word) ? Math.max(best, word.length) : best), 0);
    const score = wordScore ? wordScore + (TYPE_PRIORITY[rule.type] || 0) : 0;
    if (score > typeScore) {
      type = rule.type;
      typeScore = score;
    }
  });

  if (type === "Other") {
    if (["epub", "mobi"].includes(extension)) type = "Reading";
    if (["ppt", "pptx", "key", "odp"].includes(extension)) type = "Lecture Slides";
    const extensionMatch = Object.entries(EXTENSION_TYPES).find(([, extensions]) => extensions.includes(extension));
    if (extensionMatch && type === "Other") type = extensionMatch[0];
  }
  if (["ppt", "pptx", "key", "odp"].includes(extension) && type === "Lecture Notes") {
    type = "Lecture Slides";
  }

  const learnedType = findLearnedType(searchable, course);
  if (learnedType) type = learnedType;

  return {
    ...entry,
    extension,
    course,
    type,
    analysisSource: entry.analysisSource || "Filename and path",
    confidence: entry.previewText && (courseScore || typeScore) ? "high" : courseScore || typeScore ? "medium" : "low",
  };
}

function courseAliases(course) {
  const normalized = course.toLowerCase().replace(/[_\-.]+/g, " ").replace(/\s+/g, " ").trim();
  const compact = normalized.replace(/\s+/g, "");
  const words = normalized.split(" ").filter((word) => word.length > 2);
  return [...new Set([normalized, compact, ...words])].filter(Boolean);
}

function findLearnedType(searchable, course) {
  const matches = Object.entries(state.profile.corrections || {})
    .filter(([token]) => searchable.includes(token))
    .map(([token, value]) => {
      const info = typeof value === "string" ? { type: value, course: null } : value;
      return { token, type: info.type, courseMatch: info.course && info.course === course ? 1 : 0 };
    });
  matches.sort((a, b) => b.courseMatch - a.courseMatch || b.token.length - a.token.length);
  return matches[0]?.type || "";
}

function renderPlan(folderName, canWrite) {
  elements.emptyPlan.classList.add("hidden");
  elements.planContent.classList.remove("hidden");
  elements.folderName.textContent = folderName;
  const skippedText = state.scanStats.skipped ? `, ${state.scanStats.skipped} skipped` : "";
  const contentText = state.contentStats.analyzed ? `, ${state.contentStats.analyzed} content-scanned` : "";
  elements.folderSummary.textContent = canWrite
    ? state.sourceMode === "files" || state.sourceMode === "folder-preview"
      ? `Destination: ${state.destinationName}${contentText}`
      : `Scan complete${contentText}${skippedText}`
    : `Suggestions ready${contentText}; destination not selected`;
  elements.fileCount.textContent = `${state.scannedFiles.length} ${pluralize("file", state.scannedFiles.length)}`;
  elements.organizeButton.disabled = !state.scannedFiles.length;
  elements.organizeButton.querySelector("span").textContent = "Review file placements";
  elements.createFoldersButton.disabled = !canWrite || !state.scannedFiles.length;
  elements.createFoldersButton.classList.toggle("hidden", !canWrite);
  elements.chooseDestinationButton.classList.toggle("hidden", canWrite || !state.scannedFiles.length);

  const suggestedFolders = getSuggestedFolders();
  elements.folderCount.textContent = suggestedFolders.size;
  elements.suggestedFolderList.innerHTML = "";
  [...suggestedFolders.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 12)
    .forEach(([path, count]) => {
      const row = document.createElement("div");
      row.className = "suggested-folder-row";
      row.title = `_StudySort/${path}`;
      row.innerHTML = `<i data-lucide="folder"></i><span class="suggested-folder-path">${escapeHtml(path)}</span><span>${count}</span>`;
      elements.suggestedFolderList.appendChild(row);
    });
  if (suggestedFolders.size > 12) {
    const more = document.createElement("div");
    more.className = "suggested-folder-more";
    more.textContent = `+ ${suggestedFolders.size - 12} more suggested folders`;
    elements.suggestedFolderList.appendChild(more);
  }

  const counts = new Map();
  state.scannedFiles.forEach((file) => counts.set(file.type, (counts.get(file.type) || 0) + 1));
  elements.categoryList.innerHTML = "";
  [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .forEach(([type, count]) => {
      const row = document.createElement("div");
      row.className = "category-row";
      row.innerHTML = `<span class="category-mark"></span><strong>${escapeHtml(type)}</strong><span>${count}</span>`;
      elements.categoryList.appendChild(row);
    });
  refreshIcons();
}

function getSuggestedFolders() {
  const folders = new Map();
  state.scannedFiles.forEach((file) => {
    const path = destinationParts(file).folders.map(safeFolderName).join("/");
    folders.set(path, (folders.get(path) || 0) + 1);
  });
  return folders;
}

async function createSuggestedFolders() {
  if (!state.directoryHandle || state.busy || !state.scannedFiles.length) return;
  setBusy(true);
  elements.createFoldersButton.disabled = true;
  elements.createFoldersButton.querySelector("span").textContent = "Creating folders...";
  let created = 0;

  try {
    const outputRoot = await state.directoryHandle.getDirectoryHandle("_StudySort", { create: true });
    const folderPaths = [...getSuggestedFolders().keys()];
    for (const path of folderPaths) {
      let directory = outputRoot;
      for (const part of path.split("/")) {
        directory = await directory.getDirectoryHandle(part, { create: true });
      }
      created += 1;
      elements.createFoldersButton.querySelector("span").textContent = `Creating folders... (${created}/${folderPaths.length})`;
    }
    addMessage(`I created ${created} suggested ${pluralize("folder", created)} inside _StudySort. No files were moved or copied.`);
    showToast(`${created} suggested folders created. Files were not changed.`);
  } catch (error) {
    addMessage(`I couldn't create the folder structure: ${error.message || "write permission was interrupted"}. No files were moved.`);
  } finally {
    setBusy(false);
    elements.createFoldersButton.disabled = false;
    elements.createFoldersButton.querySelector("span").textContent = "Create suggested folders";
  }
}

function openReview() {
  if (!state.scannedFiles.length) return;
  elements.reviewBody.innerHTML = "";

  const ordered = state.scannedFiles
    .map((file, index) => ({ file, index }))
    .sort((a, b) => (a.file.confidence === "low" ? 0 : 1) - (b.file.confidence === "low" ? 0 : 1));

  ordered.forEach(({ file, index }) => {
    const row = document.createElement("tr");
    const flag = file.confidence === "low"
      ? '<span class="confidence-flag" title="Low-confidence guess — please check the course and type">Needs review</span>'
      : "";
    row.innerHTML = `
      <td><div class="file-name-cell"><span>${escapeHtml(file.name)}</span>${flag}<span class="analysis-source">${escapeHtml(file.analysisSource || "Filename and path")}</span></div></td>
      <td>${selectMarkup("course", index, ["General", ...state.profile.courses], file.course)}</td>
      <td>${selectMarkup("type", index, FILE_TYPES, file.type)}</td>
      <td class="destination-cell">${escapeHtml(destinationFor(file))}</td>
    `;
    elements.reviewBody.appendChild(row);
  });

  elements.reviewBody.querySelectorAll("select").forEach((select) => {
    select.addEventListener("change", handleClassificationChange);
  });

  const lowCount = state.scannedFiles.filter((file) => file.confidence === "low").length;
  const lowNote = lowCount ? ` ${lowCount} ${pluralize("file", lowCount)} flagged "Needs review" at the top — double-check those.` : "";
  elements.reviewSummary.textContent = state.directoryHandle
    ? `${state.scannedFiles.length} ${pluralize("file", state.scannedFiles.length)} will be copied. Originals stay where they are.${lowNote}`
    : `${state.scannedFiles.length} ${pluralize("file", state.scannedFiles.length)} planned. Choose a destination before creating copies.${lowNote}`;
  elements.confirmOrganize.classList.toggle("hidden", !state.directoryHandle);
  elements.reviewModal.classList.remove("hidden");
  document.body.style.overflow = "hidden";
  elements.closeReview.focus();
}

function handleClassificationChange(event) {
  const index = Number(event.target.dataset.index);
  const field = event.target.dataset.field;
  const file = state.scannedFiles[index];
  const previousType = file.type;
  file[field] = event.target.value;

  if (field === "type" && previousType !== file.type) {
    const token = strongestFilenameToken(file.name);
    if (token) state.profile.corrections[token] = { type: file.type, course: file.course };
    saveProfile();
  }

  const row = event.target.closest("tr");
  row.querySelector(".destination-cell").textContent = destinationFor(file);
  renderPlan(elements.folderName.textContent, Boolean(state.directoryHandle));
}

async function organizeFiles() {
  if (!state.directoryHandle || state.busy) return;
  setBusy(true);
  elements.confirmOrganize.disabled = true;
  elements.confirmOrganize.textContent = "Creating copies...";

  let copied = 0;
  let renamedForCollision = 0;
  const failures = [];
  const results = [];
  const usedNames = new Map();
  const total = state.scannedFiles.length;
  const progressStep = Math.max(1, Math.ceil(total / 50));
  try {
    const outputRoot = await state.directoryHandle.getDirectoryHandle("_StudySort", { create: true });
    let index = 0;
    for (const file of state.scannedFiles) {
      index += 1;
      if (index === total || index % progressStep === 0) {
        elements.confirmOrganize.textContent = `Creating copies... (${index}/${total})`;
      }
      let finalName = file.name;
      try {
        const destination = destinationParts(file);
        const dirKey = destination.folders.map(safeFolderName).join("/");
        finalName = uniqueFileName(usedNames, dirKey, file.name);
        if (finalName !== file.name) renamedForCollision += 1;
        let directory = outputRoot;
        for (const part of destination.folders) {
          directory = await directory.getDirectoryHandle(safeFolderName(part), { create: true });
        }
        const outputHandle = await directory.getFileHandle(finalName, { create: true });
        const writable = await outputHandle.createWritable();
        const sourceFile = file.file || (await file.handle.getFile());
        await writable.write(sourceFile);
        await writable.close();
        copied += 1;
        results.push({ name: file.name, status: "Copied", location: displayDestination(file, finalName) });
      } catch (error) {
        failures.push(`${file.name}: ${error.message || "copy failed"}`);
        results.push({ name: file.name, status: "Failed", location: displayDestination(file, finalName) });
      }
    }

    state.lastResults = results;
    closeReview();
    const message = failures.length
      ? `I copied ${copied} files into _StudySort. ${failures.length} couldn't be copied, and their originals are still safe.`
      : `Done, ${state.profile.name}. I created organized copies of all ${copied} files inside _StudySort. Your originals are exactly where you left them.`;
    const collisionNote = renamedForCollision
      ? ` ${renamedForCollision} ${pluralize("file", renamedForCollision)} shared a name with another file in the same folder, so I added a number to keep both.`
      : "";
    addMessage(`${message}${collisionNote} I saved a file-location report so you can see where every copy was created.`, "assistant", {
      action: { label: "View file locations", icon: "map-pin", onClick: openReport },
    });
    showToast(failures.length ? `Copied ${copied}; ${failures.length} skipped.` : `${copied} files organized successfully.`);
  } finally {
    setBusy(false);
    elements.confirmOrganize.disabled = false;
    elements.confirmOrganize.innerHTML = '<i data-lucide="copy-check" aria-hidden="true"></i>Create organized copies';
    refreshIcons();
  }
}

function destinationParts(file) {
  const style = state.profile.style;
  if (style === "By type, then course") return { folders: [file.type, file.course] };
  if (style === "By course, then semester") return { folders: [file.course, currentSemester()] };
  return { folders: [file.course, file.type] };
}

function destinationFor(file, nameOverride) {
  return `_StudySort/${destinationParts(file).folders.join("/")}/${nameOverride || file.name}`;
}

function displayDestination(file, nameOverride) {
  const root = state.destinationName || "Selected destination";
  const location = `${root}/${destinationFor(file, nameOverride)}`;
  return /^[A-Za-z]:$/.test(root) ? location.replaceAll("/", "\\") : location;
}

function uniqueFileName(usedNames, dirKey, name) {
  if (!usedNames.has(dirKey)) usedNames.set(dirKey, new Set());
  const set = usedNames.get(dirKey);
  const lower = name.toLowerCase();
  if (!set.has(lower)) {
    set.add(lower);
    return name;
  }
  const dotIndex = name.lastIndexOf(".");
  const base = dotIndex > 0 ? name.slice(0, dotIndex) : name;
  const ext = dotIndex > 0 ? name.slice(dotIndex) : "";
  let counter = 2;
  let candidate = `${base} (${counter})${ext}`;
  while (set.has(candidate.toLowerCase())) {
    counter += 1;
    candidate = `${base} (${counter})${ext}`;
  }
  set.add(candidate.toLowerCase());
  return candidate;
}

function openReport() {
  if (!state.lastResults.length) {
    describePlannedLocations();
    return;
  }
  elements.reportBody.innerHTML = "";
  state.lastResults.forEach((result) => {
    const row = document.createElement("tr");
    const statusClass = result.status === "Failed" ? "report-status failed" : "report-status";
    row.innerHTML = `
      <td>${escapeHtml(result.name)}</td>
      <td><span class="${statusClass}">${escapeHtml(result.status)}</span></td>
      <td class="destination-cell">${escapeHtml(result.location)}</td>
    `;
    elements.reportBody.appendChild(row);
  });
  const copied = state.lastResults.filter((result) => result.status === "Copied").length;
  const reportRoot = /^[A-Za-z]:$/.test(state.destinationName)
    ? `${state.destinationName}\\_StudySort`
    : `${state.destinationName}/_StudySort`;
  elements.reportSummary.textContent = `${copied} of ${state.lastResults.length} ${pluralize("file", state.lastResults.length)} copied inside ${reportRoot}.`;
  elements.reportModal.classList.remove("hidden");
  document.body.style.overflow = "hidden";
  elements.closeReport.focus();
}

function closeReport() {
  elements.reportModal.classList.add("hidden");
  document.body.style.overflow = "";
}

function currentSemester() {
  const date = new Date();
  const month = date.getMonth();
  const term = month < 5 ? "Spring" : month < 8 ? "Summer" : "Fall";
  return `${term} ${date.getFullYear()}`;
}

function safeFolderName(value) {
  return value.replace(/[\\/:*?"<>|]/g, "-").trim() || "General";
}

function selectMarkup(field, index, options, selected) {
  const uniqueOptions = [...new Set([selected, ...options])];
  return `<select class="table-select" data-field="${field}" data-index="${index}" aria-label="${field} for file">
    ${uniqueOptions.map((option) => `<option value="${escapeHtml(option)}" ${option === selected ? "selected" : ""}>${escapeHtml(option)}</option>`).join("")}
  </select>`;
}

function strongestFilenameToken(filename) {
  return filename
    .toLowerCase()
    .replace(/\.[^.]+$/, "")
    .split(/[^a-z0-9]+/)
    .filter((token) => token.length >= 5 && !/^\d+$/.test(token) && !GENERIC_TOKENS.has(token))
    .sort((a, b) => b.length - a.length)[0] || "";
}

function parseCourses(text) {
  return [...new Set(text.split(/[,;\n]+/).map((course) => course.trim()).filter(Boolean))].slice(0, 12);
}

function normalizeChoice(text, choices) {
  const exact = choices.find((choice) => choice.toLowerCase() === text.toLowerCase());
  if (exact) return exact;
  const included = choices.find((choice) => text.toLowerCase().includes(choice.toLowerCase().split(",")[0]));
  return included || text.slice(0, 60);
}

function cleanName(text) {
  return text.replace(/[^\p{L}\p{M}' -]/gu, "").trim().split(/\s+/).slice(0, 3).join(" ").slice(0, 40) || "Student";
}

function naturalList(items) {
  if (items.length < 2) return items[0] || "your courses";
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(", ")}, and ${items.at(-1)}`;
}

function pluralize(word, count) {
  return count === 1 ? word : `${word}s`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setBusy(value) {
  state.busy = value;
  elements.input.disabled = value;
  elements.appShell.classList.toggle("is-busy", value);
}

function closeReview() {
  elements.reviewModal.classList.add("hidden");
  document.body.style.overflow = "";
}

let toastTimer;
function showToast(message) {
  clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.remove("hidden");
  toastTimer = setTimeout(() => elements.toast.classList.add("hidden"), 4200);
}

function resetApp() {
  if (!window.confirm("Clear this student profile and restart the conversation? Your files will not be touched.")) return;
  localStorage.removeItem(STORAGE_KEY);
  state.profile = defaultProfile();
  state.scannedFiles = [];
  state.directoryHandle = null;
  state.scanStats = { skipped: 0, limited: false };
  state.contentStats = { attempted: 0, analyzed: 0, failed: 0, limited: false };
  state.lastResults = [];
  state.sourceMode = "folder";
  state.sourceLabel = "";
  state.destinationName = "";
  elements.emptyPlan.classList.remove("hidden");
  elements.planContent.classList.add("hidden");
  elements.fileCount.textContent = "0 files";
  renderProfile();
  startConversation();
}

elements.composer.addEventListener("submit", (event) => {
  event.preventDefault();
  handleReply(elements.input.value);
});
elements.restart.addEventListener("click", resetApp);
elements.chooseDestinationButton.addEventListener("click", chooseDestinationFolder);
elements.createFoldersButton.addEventListener("click", createSuggestedFolders);
elements.organizeButton.addEventListener("click", openReview);
elements.closeReview.addEventListener("click", closeReview);
elements.cancelReview.addEventListener("click", closeReview);
elements.confirmOrganize.addEventListener("click", organizeFiles);
elements.closeReport.addEventListener("click", closeReport);
elements.doneReport.addEventListener("click", closeReport);
elements.reviewModal.addEventListener("click", (event) => {
  if (event.target === elements.reviewModal) closeReview();
});
elements.reportModal.addEventListener("click", (event) => {
  if (event.target === elements.reportModal) closeReport();
});
elements.mobileProfile.addEventListener("click", () => elements.organizerPanel.classList.add("open"));
elements.closeProfile.addEventListener("click", () => elements.organizerPanel.classList.remove("open"));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !elements.reviewModal.classList.contains("hidden")) closeReview();
  if (event.key === "Escape" && !elements.reportModal.classList.contains("hidden")) closeReport();
});
window.addEventListener("load", refreshIcons);

renderProfile();
startConversation();
