// Live Downloads file-flow chart. The top half is pure (rendered to strings, tested in
// Node); the bottom half wires it to the local StudySort service with Server-Sent Events.

const MAX_FLOW_CARDS = 100;

const FLOW_STATUS = {
  detected: { label: "Detected", icon: "radar" },
  analyzing: { label: "Analyzing", icon: "scan-search" },
  awaiting_approval: { label: "Awaiting approval", icon: "hourglass" },
  copying: { label: "Copying", icon: "copy" },
  copied: { label: "Copied successfully", icon: "circle-check" },
  moved: { label: "Moved successfully", icon: "circle-check" },
  failed: { label: "Failed", icon: "circle-alert" },
  cancelled: { label: "Cancelled", icon: "ban" },
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function statusLabel(status) {
  return FLOW_STATUS[status]?.label || status;
}

function filterFlowFiles(files, filters = {}) {
  const query = (filters.query || "").trim().toLowerCase();
  return files.filter((file) => {
    if (filters.status && file.status !== filters.status) return false;
    if (filters.course && file.course !== filters.course) return false;
    if (filters.type && file.type !== filters.type) return false;
    if (!query) return true;
    return [file.name, file.course, file.type, file.planned_destination, file.actual_destination, statusLabel(file.status)]
      .some((value) => String(value || "").toLowerCase().includes(query));
  });
}

function flowFacets(files) {
  const sorted = (key) => [...new Set(files.map((file) => file[key]).filter(Boolean))].sort();
  return { courses: sorted("course"), types: sorted("type") };
}

function flowStep(label, icon, value, { path = false, pending = false, extraClass = "" } = {}) {
  const valueClass = `flow-step-value${path ? " is-path" : ""}${pending ? " is-pending" : ""}`;
  return `<div class="flow-step ${extraClass}" role="listitem">
      <span class="flow-step-label"><i data-lucide="${icon}" aria-hidden="true"></i>${escapeHtml(label)}</span>
      <span class="${valueClass}">${escapeHtml(value)}</span>
    </div>`;
}

const FLOW_ARROW = '<span class="flow-arrow" aria-hidden="true"><i data-lucide="arrow-right"></i></span>';

function flowActions(file) {
  const name = escapeHtml(file.name);
  const button = (action, icon, label, primary = false) =>
    `<button type="button" class="${primary ? "primary-button" : "secondary-button"} flow-action" data-action="${action}" data-id="${escapeHtml(file.id)}" data-focus-key="${escapeHtml(file.id)}-${action}" aria-label="${label} ${name}"><i data-lucide="${icon}" aria-hidden="true"></i>${label}</button>`;
  const buttons = [];
  if (file.status === "awaiting_approval") buttons.push(button("approve", "copy-check", "Approve", true));
  if (file.status === "failed") buttons.push(button("retry", "rotate-cw", "Retry", true));
  if (["detected", "analyzing", "awaiting_approval"].includes(file.status)) buttons.push(button("cancel", "x", "Cancel"));
  return buttons.length ? `<div class="flow-actions">${buttons.join("")}</div>` : "";
}

function renderFlowCard(file, watchName = "Downloads") {
  const analyzed = Boolean(file.course);
  const waiting = file.status === "failed" || file.status === "cancelled" ? "Not determined" : "Waiting…";
  const destination = file.actual_destination || file.planned_destination;
  const status = FLOW_STATUS[file.status] || { label: file.status, icon: "circle" };
  const time = file.detected_at ? new Date(file.detected_at).toLocaleString() : "";
  const confidence = file.confidence
    ? `<span class="confidence-badge conf-${escapeHtml(file.confidence)}">${escapeHtml(file.confidence)} confidence</span>`
    : "";
  const details = [file.reason, file.analysis].filter(Boolean).map(escapeHtml).join(" · ");

  return `<article class="flow-card status-${escapeHtml(file.status)}" tabindex="0" data-focus-key="${escapeHtml(file.id)}" aria-label="${escapeHtml(file.name)}: ${escapeHtml(status.label)}">
    <header class="flow-card-head">
      <strong class="flow-file">${escapeHtml(file.name)}</strong>
      ${confidence}
      <time class="flow-time" datetime="${escapeHtml(file.detected_at)}">${escapeHtml(time)}</time>
    </header>
    <div class="flow-steps" role="list" aria-label="File journey">
      ${flowStep("Source", "download", `${watchName}/${file.name}`, { path: true })}
      ${FLOW_ARROW}
      ${flowStep("Detected course", "graduation-cap", analyzed ? file.course : waiting, { pending: !analyzed })}
      ${FLOW_ARROW}
      ${flowStep("Detected type", "tag", analyzed ? file.type : waiting, { pending: !analyzed })}
      ${FLOW_ARROW}
      ${flowStep(file.actual_destination ? "Final location" : "Planned destination", "folder-output",
        destination ? `${watchName}/${destination}` : waiting, { path: true, pending: !destination })}
      ${FLOW_ARROW}
      ${flowStep("Status", status.icon, status.label, { extraClass: "flow-status-step" })}
    </div>
    ${details ? `<p class="flow-details">${details}</p>` : ""}
    ${file.error ? `<p class="flow-error" role="alert"><i data-lucide="triangle-alert" aria-hidden="true"></i>${escapeHtml(file.error)}</p>` : ""}
    ${flowActions(file)}
  </article>`;
}

function renderFlowList(files, filters = {}, watchName = "Downloads") {
  const matches = filterFlowFiles(files, filters);
  const shown = matches.slice(0, MAX_FLOW_CARDS);
  return { html: shown.map((file) => renderFlowCard(file, watchName)).join(""), shown: shown.length, total: matches.length };
}

if (typeof module !== "undefined") {
  module.exports = { MAX_FLOW_CARDS, FLOW_STATUS, escapeHtml, filterFlowFiles, flowFacets, renderFlowCard, renderFlowList };
}

// ---- Browser wiring ----------------------------------------------------------------
if (typeof document !== "undefined") {
  const flow = { files: new Map(), status: null, connected: false, renderQueued: false };
  const $ = (selector) => document.querySelector(selector);
  const el = {
    open: $("#view-flow-button"),
    modal: $("#flow-modal"),
    close: $("#close-flow-button"),
    list: $("#flow-list"),
    empty: $("#flow-empty"),
    emptyText: $("#flow-empty-text"),
    count: $("#flow-count"),
    banner: $("#flow-banner"),
    search: $("#flow-search"),
    status: $("#flow-status-filter"),
    course: $("#flow-course-filter"),
    type: $("#flow-type-filter"),
    clear: $("#flow-clear-button"),
    watchName: $("#live-watch-name"),
    liveSummary: $("#live-summary"),
    liveDot: $("#live-dot"),
    subtitle: $("#flow-subtitle"),
  };

  const sortedFiles = () => [...flow.files.values()].sort((a, b) => (b.detected_at || "").localeCompare(a.detected_at || ""));
  const watchName = () => flow.status?.watch_name || "Downloads";

  function setOptions(select, values, allLabel) {
    const current = select.value;
    select.innerHTML = `<option value="">${allLabel}</option>${values.map((v) => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`).join("")}`;
    select.value = values.includes(current) ? current : "";
  }

  function render() {
    flow.renderQueued = false;
    const files = sortedFiles();
    const facets = flowFacets(files);
    setOptions(el.course, facets.courses, "All courses");
    setOptions(el.type, facets.types, "All types");

    const focusKey = document.activeElement?.closest?.("#flow-list") ? document.activeElement.dataset.focusKey : null;
    const filters = { query: el.search.value, status: el.status.value, course: el.course.value, type: el.type.value };
    const { html, shown, total } = renderFlowList(files, filters, watchName());
    el.list.innerHTML = html;
    el.empty.classList.toggle("hidden", shown > 0);
    el.emptyText.textContent = files.length
      ? "No files match these filters."
      : `No downloads yet. Save or download a file into ${flow.status?.watch_dir || "your Downloads folder"} and it will appear here automatically.`;
    el.count.textContent = total > shown ? `Showing ${shown} of ${total} files` : `${total} ${total === 1 ? "file" : "files"}`;
    if (focusKey) el.list.querySelector(`[data-focus-key="${CSS.escape(focusKey)}"]`)?.focus();
    renderLiveSummary(files);
    if (window.lucide) window.lucide.createIcons();
  }

  function queueRender() {
    if (flow.renderQueued) return;
    flow.renderQueued = true;
    requestAnimationFrame(render);
  }

  function renderLiveSummary(files) {
    const waiting = files.filter((file) => file.status === "awaiting_approval").length;
    const failed = files.filter((file) => file.status === "failed").length;
    el.watchName.textContent = flow.status ? flow.status.watch_dir : "Connecting to StudySort service…";
    const parts = [`${files.length} tracked`];
    if (waiting) parts.push(`${waiting} awaiting approval`);
    if (failed) parts.push(`${failed} failed`);
    el.liveSummary.textContent = flow.connected ? parts.join(" · ") : "Service offline. Start app_server.py.";
    el.liveDot.classList.toggle("offline", !flow.connected || !flow.status?.watcher_alive);
    if (flow.status) {
      const mode = flow.status.move ? "move" : "copy";
      el.subtitle.textContent = `Watching ${flow.status.watch_dir} · ${mode} mode · ${flow.status.auto_organize ? "auto-organize on" : "approval required"}`;
    }
  }

  function showBanner(message) {
    el.banner.textContent = message || "";
    el.banner.classList.toggle("hidden", !message);
  }

  function updateBanner() {
    if (!flow.connected) showBanner("Server disconnected. StudySort is trying to reconnect. Make sure app_server.py is still running.");
    else if (flow.status && !flow.status.watcher_alive) showBanner("Watcher stopped: new downloads are not being detected. Restart app_server.py.");
    else showBanner("");
  }

  async function api(path, options) {
    const response = await fetch(path, options);
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
    return body;
  }

  async function reload() {
    const [status, files] = await Promise.all([api("/api/status"), api("/api/files")]);
    flow.status = status;
    flow.files = new Map(files.map((file) => [file.id, file]));
    queueRender();
  }

  function notify(message) {
    if (typeof showToast === "function") showToast(message);
  }

  function connect() {
    const source = new EventSource("/api/events/stream");
    source.onopen = () => {
      flow.connected = true;
      updateBanner();
      reload().catch(() => {});
    };
    source.onerror = () => {
      flow.connected = false;
      updateBanner();
      queueRender();
    };
    source.onmessage = (message) => {
      const event = JSON.parse(message.data);
      if (event.type === "file") {
        if (!flow.files.has(event.file.id)) notify(`New download detected: ${event.file.name}`);
        flow.files.set(event.file.id, event.file);
      } else if (event.type === "cleared") {
        flow.files.clear();
      } else if (event.type === "status") {
        flow.status = event.status;
        updateBanner();
      }
      queueRender();
    };
  }

  let returnFocus = null;
  function openFlow() {
    returnFocus = document.activeElement;
    el.modal.classList.remove("hidden");
    document.body.style.overflow = "hidden";
    render();
    el.search.focus();
  }

  function closeFlow() {
    el.modal.classList.add("hidden");
    document.body.style.overflow = "";
    returnFocus?.focus();
  }

  el.open.addEventListener("click", openFlow);
  el.close.addEventListener("click", closeFlow);
  el.modal.addEventListener("click", (event) => {
    if (event.target === el.modal) closeFlow();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !el.modal.classList.contains("hidden")) closeFlow();
  });
  const applyFilters = () => {
    el.list.parentElement.scrollTop = 0;
    render();
  };
  el.search.addEventListener("input", applyFilters);
  [el.status, el.course, el.type].forEach((select) => select.addEventListener("change", applyFilters));

  el.list.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    button.disabled = true;
    try {
      const file = await api(`/api/files/${encodeURIComponent(button.dataset.id)}/${button.dataset.action}`, { method: "POST" });
      flow.files.set(file.id, file);
      queueRender();
    } catch (error) {
      showBanner(error.message);
      button.disabled = false;
    }
  });

  el.clear.addEventListener("click", async () => {
    if (!window.confirm("Clear the file-flow history? Files on disk are not touched.")) return;
    try {
      await api("/api/files", { method: "DELETE" });
      flow.files.clear();
      queueRender();
    } catch (error) {
      showBanner(error.message);
    }
  });

  connect();
}
