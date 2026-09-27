// Clip review: source span playback, boundaries, captions, save, preview render, decision.
const $ = (id) => document.getElementById(id);
const root = $("review");
const base = root.dataset.base;
const data = JSON.parse($("data").textContent);
const src = $("source");
let dirty = false;
let state = data.state;

const fmt = (s) => {
  const h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60, sec = (s % 60).toFixed(1).padStart(4, "0");
  return `${h}:${String(m).padStart(2, "0")}:${sec}`;
};
const val = (id) => parseFloat($(id).value);

// ---- captions ----
function addCaption(c = { start: 0, end: 1, text: "" }) {
  const row = $("cap-row").content.firstElementChild.cloneNode(true);
  row.querySelector(".c-start").value = c.start;
  row.querySelector(".c-end").value = c.end;
  row.querySelector(".c-text").value = c.text;
  row.querySelector(".c-del").addEventListener("click", () => { row.remove(); markDirty(); });
  $("cap-rows").append(row);
}
function setCaptions(list) { $("cap-rows").replaceChildren(); list.forEach(addCaption); }
setCaptions(data.rv.captions);
$("cap-add").addEventListener("click", () => {
  const rows = [...document.querySelectorAll("#cap-rows tr")];
  const last = rows.length ? parseFloat(rows.at(-1).querySelector(".c-end").value) || 0 : 0;
  addCaption({ start: last, end: last + 2, text: "" });
  markDirty();
  $("cap-rows").lastElementChild.querySelector(".c-text").focus();
});

// ---- span, transcript, duration ----
function refreshSpan() {
  const s = val("start"), e = val("end"), d = e - s;
  $("duration").textContent = isFinite(d) ? `${d.toFixed(1)} s` : "–";
  $("span-label").textContent = isFinite(d) ? `${fmt(s)} – ${fmt(e)}` : "";
  const warn = $("dur-warn");
  warn.hidden = !(d < 15 || d > 60);
  warn.textContent = d > 60 ? "over 60 s: longer complete explanation — your choice" : "under 15 s: check the point is complete";
  for (const b of document.querySelectorAll(".unit")) {
    b.classList.toggle("in", parseFloat(b.dataset.end) > s && parseFloat(b.dataset.start) < e);
  }
}
for (const b of document.querySelectorAll(".unit")) {
  b.addEventListener("click", () => { src.currentTime = parseFloat(b.dataset.start); src.play(); });
}
$("play-span").addEventListener("click", () => { src.currentTime = val("start"); src.play(); });
src.addEventListener("timeupdate", () => { if (!src.paused && src.currentTime >= val("end")) src.pause(); });

for (const b of document.querySelectorAll("[data-nudge]")) {
  b.addEventListener("click", () => {
    const side = b.dataset.nudge, input = $(side), cur = parseFloat(input.value);
    let next;
    if (b.dataset.by) next = cur + parseFloat(b.dataset.by);
    else {
      const edges = data.bounds[side === "start" ? "starts" : "ends"];
      next = b.dataset.unit === "1" ? edges.find((t) => t > cur + 0.001) : edges.findLast((t) => t < cur - 0.001);
    }
    if (next === undefined) return;
    input.value = Math.max(0, Math.round(next * 1000) / 1000);
    markDirty();
    refreshSpan();
    src.currentTime = side === "start" ? val("start") : Math.max(val("start"), val("end") - 3);
  });
}
refreshSpan();

// ---- layout ----
const mode = () => document.querySelector("input[name=mode]:checked").value;
for (const r of document.querySelectorAll("input[name=mode]")) {
  r.addEventListener("change", () => { $("crop-fields").hidden = mode() !== "crop"; });
}
const box = (name) => ["x", "y", "w", "h"].map((n) => val(`${name}-${n}`));

// ---- save ----
function body() {
  const post = (p) => ({ title: $(`${p}-title`).value, description: $(`${p}-description`).value, cta: $(`${p}-cta`).value });
  return {
    start: val("start"), end: val("end"), title: $("title").value, category: $("category").value, tags: $("tags").value,
    layout: mode() === "crop" ? { mode: "crop", crop: box("crop"), inset: $("use-inset").checked ? box("inset") : null } : { mode: "full" },
    captions: [...document.querySelectorAll("#cap-rows tr")].map((r) => ({
      start: parseFloat(r.querySelector(".c-start").value), end: parseFloat(r.querySelector(".c-end").value),
      text: r.querySelector(".c-text").value })),
    drafts: { facebook: post("facebook"), youtube: post("youtube") },
  };
}

async function api(path, payload) {
  const r = await fetch(base + path, { method: "POST", headers: { "Content-Type": "application/json" },
    body: payload === undefined ? undefined : JSON.stringify(payload) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || j.error || `HTTP ${r.status}`);
  return j;
}

function markDirty() { dirty = true; $("save-status").textContent = "Unsaved changes"; render(); }
root.addEventListener("input", (e) => { if (e.target.matches("[data-field]")) markDirty(); });
root.addEventListener("change", (e) => { if (e.target.matches("[data-field]")) { markDirty(); refreshSpan(); } });

async function withBusy(btn, fn) {
  btn.disabled = true; btn.classList.add("loading"); btn.setAttribute("aria-busy", "true");
  try { return await fn(); } finally { btn.classList.remove("loading"); btn.removeAttribute("aria-busy"); render(); }
}

async function save() {
  try {
    state = await api("", body());
    dirty = false;
    $("save-status").textContent = "Saved";
    return true;
  } catch (e) {
    $("save-status").textContent = `Not saved: ${e.message}`;
    return false;
  }
}
$("save").addEventListener("click", () => withBusy($("save"), save));

$("cap-reset").addEventListener("click", () => withBusy($("cap-reset"), async () => {
  if (!confirm("Replace all caption rows with transcript text for the current boundaries?")) return;
  if (!(await save())) return;
  const j = await api("/captions/reset");
  setCaptions(j.captions);
  state = j;
}));

// ---- preview render + polling ----
async function poll() {
  const r = await fetch(base + "/state");
  state = await r.json();
  render();
  if (state.render === "running" || state.draft === "running") setTimeout(poll, 1000);
  else if (state.draft === "done" && $("draft-run")) location.reload(); // show the new draft fields
}
$("render").addEventListener("click", () => withBusy($("render"), async () => {
  if (dirty && !(await save())) return;
  state = await api("/preview");
  setTimeout(poll, 1000);
}));
if ($("draft-run")) {
  $("draft-run").addEventListener("click", () => withBusy($("draft-run"), async () => {
    if (!confirm("Request a posting draft? This is a paid call within this class's cap.")) return;
    state = await api("/draft");
    setTimeout(poll, 1000);
  }));
}

// ---- decision ----
async function decide(decision) {
  try {
    state = await api("/decision", { decision });
    render();
  } catch (e) { render(); $("approve-hint").textContent = e.message; }
}
$("approve").addEventListener("click", () => withBusy($("approve"), () => decide("approve")));
$("reject").addEventListener("click", () => withBusy($("reject"), () => decide("reject")));

function render() {
  const rendering = state.render === "running";
  $("render").disabled = rendering;
  $("render-status").textContent = rendering ? "Rendering…" : state.render === "error" ? `Render failed: ${state.render_error}` : "";
  if ($("draft-status")) {
    $("draft-status").textContent = state.draft === "running" ? "Drafting…" : state.draft === "error" ? `Draft failed: ${state.draft_error}` : "";
  }
  const pv = $("preview");
  if (state.preview_url && !dirty) {
    if (!pv.src.endsWith(state.preview_url)) pv.src = state.preview_url;
    $("no-preview").hidden = true;
  } else { pv.removeAttribute("src"); $("no-preview").hidden = false; }
  const canApprove = state.preview_ok && !dirty && !rendering;
  $("approve").disabled = !canApprove || state.status === "approved";
  $("reject").disabled = state.status === "rejected";
  const badge = $("status-badge");
  badge.textContent = state.status;
  badge.className = `badge r-${state.status}`;
  $("approve-hint").textContent = dirty ? "Save, then render a preview to approve."
    : state.status === "approved" ? "Approved. Changing the video, title, or captions needs a new preview and approval."
    : !state.preview_ok ? "Render a phone preview of the current saved edits to approve."
    : "The preview matches the saved edits.";
}
render();
if (state.render === "running" || state.draft === "running") setTimeout(poll, 1000);

// ---- keyboard: J / K previous / next candidate ----
document.addEventListener("keydown", (e) => {
  if (e.ctrlKey || e.metaKey || e.altKey || e.target.closest("input, textarea, select, video")) return;
  const to = e.key === "j" ? root.dataset.prev : e.key === "k" ? root.dataset.next : "";
  if (!to) return;
  if (dirty && !confirm("Leave without saving?")) return;
  dirty = false;
  location.href = to;
});
window.addEventListener("beforeunload", (e) => { if (dirty) e.preventDefault(); });
