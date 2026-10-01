const test = require("node:test");
const assert = require("node:assert/strict");
const {
  MAX_FLOW_CARDS, filterFlowFiles, flowFacets, renderFlowCard, renderFlowList,
} = require("../../frontend/flow.js");

const copied = {
  id: "a1", name: "CS101_assignment.pdf", status: "copied", course: "CS101", type: "Assignments",
  confidence: "high", reason: 'Course code "CS101" found in filename',
  planned_destination: "_StudySort/CS101/Assignments/CS101_assignment.pdf",
  actual_destination: "_StudySort/CS101/Assignments/CS101_assignment (2).pdf",
  detected_at: "2026-10-01T10:00:00.000+00:00",
};
const waiting = {
  id: "b2", name: "week3 notes.txt", status: "awaiting_approval", course: "Calculus", type: "Lecture Notes",
  confidence: "medium", planned_destination: "_StudySort/Calculus/Lecture Notes/week3 notes.txt",
  detected_at: "2026-10-01T11:00:00.000+00:00",
};
const failed = {
  id: "c3", name: "ghost.pdf", status: "failed", error: "File disappeared: it was moved.",
  detected_at: "2026-10-01T12:00:00.000+00:00",
};
const detected = { id: "d4", name: "big.zip", status: "detected", detected_at: "2026-10-01T13:00:00.000+00:00" };
const all = [copied, waiting, failed, detected];

test("card shows the full journey: source, course, type, destination, status", () => {
  const html = renderFlowCard(copied, "Downloads");
  const order = ["Source", "Downloads/CS101_assignment.pdf", "Detected course", "CS101", "Detected type",
    "Assignments", "Final location", "Downloads/_StudySort/CS101/Assignments/CS101_assignment (2).pdf",
    "Copied successfully"];
  let cursor = 0;
  for (const text of order) {
    const at = html.indexOf(text, cursor);
    assert.ok(at >= cursor, `expected "${text}" in order`);
    cursor = at;
  }
  assert.equal(html.match(/class="flow-arrow"/g).length, 4);
  assert.match(html, /status-copied/);
  assert.match(html, /aria-label="CS101_assignment.pdf: Copied successfully"/);
  assert.doesNotMatch(html, /data-action/);
});

test("status decides which actions are offered", () => {
  assert.match(renderFlowCard(waiting), /data-action="approve"/);
  assert.match(renderFlowCard(waiting), /data-action="cancel"/);
  assert.match(renderFlowCard(waiting), /Planned destination/);
  const failedHtml = renderFlowCard(failed);
  assert.match(failedHtml, /data-action="retry"/);
  assert.match(failedHtml, /role="alert"[^>]*>.*File disappeared/s);
  assert.match(failedHtml, /Not determined/);
  assert.match(renderFlowCard(detected), /Waiting…/);
});

test("file names are escaped", () => {
  const html = renderFlowCard({ ...waiting, name: '<img src=x onerror="alert(1)">.pdf' });
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;img src=x onerror=&quot;alert\(1\)&quot;&gt;\.pdf/);
});

test("filters by status, course, type and search text", () => {
  assert.deepEqual(filterFlowFiles(all, { status: "failed" }).map((f) => f.id), ["c3"]);
  assert.deepEqual(filterFlowFiles(all, { course: "Calculus" }).map((f) => f.id), ["b2"]);
  assert.deepEqual(filterFlowFiles(all, { type: "Assignments" }).map((f) => f.id), ["a1"]);
  assert.deepEqual(filterFlowFiles(all, { query: "WEEK3" }).map((f) => f.id), ["b2"]);
  assert.deepEqual(filterFlowFiles(all, { query: "assignment (2)" }).map((f) => f.id), ["a1"]);
  assert.deepEqual(filterFlowFiles(all, { query: "awaiting" }).map((f) => f.id), ["b2"]);
  assert.deepEqual(filterFlowFiles(all, { query: "cs101", status: "failed" }), []);
  assert.equal(filterFlowFiles(all, {}).length, 4);
});

test("facets list each course and type once", () => {
  assert.deepEqual(flowFacets(all), { courses: ["CS101", "Calculus"], types: ["Assignments", "Lecture Notes"] });
});

test("never renders more than 100 cards", () => {
  const many = Array.from({ length: 150 }, (_, i) => ({ ...waiting, id: `f${i}` }));
  const result = renderFlowList(many, {});
  assert.equal(MAX_FLOW_CARDS, 100);
  assert.equal(result.shown, 100);
  assert.equal(result.total, 150);
  assert.equal(result.html.match(/<article/g).length, 100);
});
