// Clip review: source span playback, boundaries, captions, save, preview render, decision.
const $ = (id) => document.getElementById(id);
const root = $("review");
const base = root.dataset.base;
const data = JSON.parse($("data").textContent);
const src = $("source");
let dirty = false;
let draftsDirty = false; // posting text is sent only when the operator edited it
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

// ---- waveform: loudness strip under the source, the clip's span tinted violet, click/drag to seek ----
const wave = $("waveform"), wctx = wave.getContext("2d");
let peaks = null, bars = null; // bars: offscreen render of the peaks and span, replayed with the playhead
const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

function paintWave() {
  if (!peaks) return;
  const dpr = devicePixelRatio || 1;
  const w = wave.width = Math.round(wave.clientWidth * dpr), h = wave.height = Math.round(wave.clientHeight * dpr);
  bars = document.createElement("canvas");
  bars.width = w; bars.height = h;
  const c = bars.getContext("2d"), dur = src.duration || 1, t = (s) => Math.max(0, Math.min(w, s / dur * w));
  const bw = w / peaks.length;
  c.fillStyle = cssVar("--ink-3");
  for (let i = 0; i < peaks.length; i++) {
    const bh = Math.max(dpr, peaks[i] / 32768 * (h - 4)); // centred mirrored bars, one per bucket
    c.fillRect(Math.floor(i * bw), (h - bh) / 2, Math.max(1, Math.ceil(bw)), bh);
  }
  c.globalAlpha = .35; c.fillStyle = cssVar("--mask");  // the clip's own [start, end] window
  c.fillRect(t(val("start")), 0, t(val("end")) - t(val("start")), h);
  drawWaveHead();
}
function drawWaveHead() {
  if (!bars) return;
  wctx.clearRect(0, 0, wave.width, wave.height);
  wctx.drawImage(bars, 0, 0);
  const x = Math.round(src.currentTime / (src.duration || 1) * wave.width);
  wctx.fillStyle = cssVar("--mask-hi");
  wctx.fillRect(x, 0, Math.max(1, Math.round(devicePixelRatio || 1)), wave.height);
  announcePos();
}
function announcePos() {
  // keep the slider's value in step with the playhead, so the position is spoken, not just seen
  wave.setAttribute("aria-valuenow", src.currentTime.toFixed(1));
  wave.setAttribute("aria-valuemax", (src.duration || 0).toFixed(1));
  wave.setAttribute("aria-valuetext", fmt(src.currentTime || 0));
}
fetch(root.dataset.peaks).then((r) => { if (!r.ok) throw 0; return r.json(); }).then((p) => {
  peaks = p;
  wave.hidden = false;
  paintWave();
}).catch(() => {});  // no peaks file (no audio stream): the strip simply stays hidden
src.addEventListener("loadedmetadata", paintWave);  // duration arrives after the first paint
src.addEventListener("timeupdate", drawWaveHead);
window.addEventListener("resize", paintWave);
const seekAt = (e) => {
  const r = wave.getBoundingClientRect();
  src.currentTime = (e.clientX - r.left) / r.width * (src.duration || 0);
};
let seeking = false;
wave.addEventListener("pointerdown", (e) => { seeking = true; wave.setPointerCapture(e.pointerId); seekAt(e); });
wave.addEventListener("pointermove", (e) => { if (seeking) seekAt(e); });
wave.addEventListener("pointerup", () => { seeking = false; });

// keyboard: the strip is a seek control, so it must work without a mouse.
// arrows nudge, shift jumps a whole clip, Home/End go to the ends of the class.
wave.addEventListener("keydown", (e) => {
  const dur = src.duration || 0, span = Math.max(5, val("end") - val("start"));
  const step = e.shiftKey ? span : 5;
  const go = (t) => { src.currentTime = Math.max(0, Math.min(dur, t)); drawWaveHead(); };
  const at = src.currentTime || 0;
  const keys = {
    ArrowRight: () => go(at + step), ArrowUp: () => go(at + step),
    ArrowLeft: () => go(at - step), ArrowDown: () => go(at - step),
    PageUp: () => go(at + span), PageDown: () => go(at - span),
    Home: () => go(0), End: () => go(dur),
  };
  if (!keys[e.key]) return;
  e.preventDefault();
  keys[e.key]();
});

// ---- span, transcript, duration ----
function refreshSpan() {
  const s = val("start"), e = val("end"), d = e - s;
  $("duration").textContent = isFinite(d) ? `${d.toFixed(1)} s` : "–";
  $("duration-sum").textContent = isFinite(d) ? `— ${d.toFixed(1)} s` : "";
  $("span-label").textContent = isFinite(d) ? `${fmt(s)} – ${fmt(e)}` : "";
  const warn = $("dur-warn");
  warn.hidden = !(d < 60 || d > 90);
  warn.textContent = d > 90 ? "over 90 s: fine if the point needs it — your choice" : "under 60 s: check the point is complete";
  for (const b of document.querySelectorAll(".unit")) {
    b.classList.toggle("in", parseFloat(b.dataset.end) > s && parseFloat(b.dataset.start) < e);
  }
  paintWave();
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
    ...(draftsDirty ? { drafts: { facebook: post("facebook"), youtube: post("youtube") } } : {}),
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
root.addEventListener("input", (e) => {
  if (!e.target.matches("[data-field]")) return;
  if (e.target.closest("fieldset.post")) draftsDirty = true;
  markDirty();
});
root.addEventListener("change", (e) => { if (e.target.matches("[data-field]")) { markDirty(); refreshSpan(); } });

async function withBusy(btn, fn) {
  btn.disabled = true; btn.classList.add("loading"); btn.setAttribute("aria-busy", "true");
  try { return await fn(); } catch (e) { $("save-status").textContent = e.message; } finally {
    btn.disabled = false; btn.classList.remove("loading"); btn.removeAttribute("aria-busy"); render();
  }
}

async function save() {
  try {
    const j = await api("", body());
    state = j;
    dirty = draftsDirty = false;
    $("start").value = j.start; $("end").value = j.end;
    setCaptions(j.captions || []); // the server re-times captions when the start moves
    refreshSpan();
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
  state = await api("/decision", { decision }); // an error lands in save-status via withBusy
}
$("approve").addEventListener("click", () => withBusy($("approve"), () => decide("approve")));
$("reject").addEventListener("click", () => withBusy($("reject"), () => decide("reject")));

function render() {
  const rendering = state.render === "running";
  $("render").disabled = rendering;
  $("render-status").textContent = state.render === "error" ? `Render failed: ${state.render_error}` : "";
  $("render").textContent = rendering ? "Rendering…" : dirty ? "Save and render previews" : state.preview_ok ? "Render again" : "Render previews";
  $("render").classList.toggle("loading", rendering);
  if ($("draft-status")) {
    $("draft-status").textContent = state.draft === "running" ? "Drafting…" : state.draft === "error" ? `Draft failed: ${state.draft_error}` : "";
  }
  for (const [video, empty, url] of [["preview", "no-preview", state.preview_url], ["preview-land", "no-preview-land", state.landscape_url]]) {
    const v = $(video);
    if (url && !dirty) {
      if (!v.src.endsWith(url)) v.src = url;
      $(empty).hidden = true;
    } else if (v.hasAttribute("src")) { v.removeAttribute("src"); v.load(); $(empty).hidden = false; }
    else $(empty).hidden = false;
  }
  const canApprove = state.preview_ok && !dirty && !rendering;
  $("approve").disabled = !canApprove || state.status === "approved";
  $("reject").disabled = state.status === "rejected";
  const badge = $("status-badge");
  badge.textContent = data.labels[state.status] || state.status;
  badge.className = `badge r-${state.status}`;
  $("approve-hint").textContent = rendering ? "Rendering both versions… this takes a few seconds."
    : dirty ? "You have unsaved changes. Save and render the previews, then watch both before approving."
    : state.status === "approved" ? "Approved. It will be in the export. Changing the clip, title, or captions needs a new preview and approval."
    : state.status === "rejected" ? "Rejected. It will not be exported. Render previews to reconsider."
    : !state.preview_ok ? "Render the previews, watch both versions, then approve or reject."
    : "Both previews match your saved edits. Watch them, then approve or reject.";
}
render();
if (state.render === "running" || state.draft === "running") setTimeout(poll, 1000);

// open where the clip begins: bring the first in-clip transcript line into view,
// without scrolling the page itself
const lines = document.querySelector(".transcript");
const firstIn = lines && lines.querySelector(".unit.in");
if (firstIn) {
  lines.scrollTop = firstIn.getBoundingClientRect().top
    - lines.getBoundingClientRect().top + lines.scrollTop - 8;
}

// ---- keyboard: J / K previous / next candidate ----
document.addEventListener("keydown", (e) => {
  // the waveform strip handles its own arrows, so J/K must not fire while it has focus
  if (e.ctrlKey || e.metaKey || e.altKey || e.target.closest("input, textarea, select, video, #waveform")) return;
  const to = e.key === "j" ? root.dataset.prev : e.key === "k" ? root.dataset.next : "";
  if (!to) return;
  if (dirty && !confirm("Leave without saving?")) return;
  dirty = false;
  location.href = to;
});
window.addEventListener("beforeunload", (e) => { if (dirty) e.preventDefault(); });
