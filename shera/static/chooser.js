// MP4 folder chooser: pick a recording's path for the existing import pipeline (no upload).
// The server does the reading; this only navigates folders and receives paths.
(() => {
  const dialog = document.getElementById("chooser");
  const value = document.getElementById("mp4");
  if (!dialog || !value || typeof dialog.showModal !== "function") return;

  const list = document.getElementById("chooser-list");
  const pathEl = document.getElementById("chooser-path");
  const emptyEl = document.getElementById("chooser-empty");
  const statusEl = document.getElementById("chooser-status");
  const upBtn = document.getElementById("chooser-up");
  const cancelBtn = document.getElementById("chooser-cancel");
  const openBtn = document.getElementById("mp4-choose");
  let parent = null;
  let lastFocus = null;

  function setStatus(step, text) {
    statusEl.hidden = !text;
    statusEl.textContent = text || "";
    statusEl.className = "muted" + (text ? " " + step : "");
  }

  function row(label, onClick, icon, className) {
    const li = document.createElement("li");
    const b = document.createElement("button");
    b.type = "button";
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "i");
    svg.setAttribute("aria-hidden", "true");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", icon);
    svg.appendChild(use);
    b.append(svg, label);
    if (className) b.className = className;
    b.addEventListener("click", onClick);
    li.appendChild(b);
    return li;
  }

  async function open(path) {
    list.replaceChildren();
    emptyEl.hidden = true;
    setStatus("", "");
    let data;
    try {
      const res = await fetch("/browse" + (path ? "?path=" + encodeURIComponent(path) : ""));
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || ("HTTP " + res.status));
      }
      data = await res.json();
    } catch (e) {
      setStatus("fail", "Could not list that folder: " + e.message);
      return;
    }
    pathEl.textContent = data.path || "Drives and common folders";
    parent = data.parent;
    upBtn.disabled = !parent;
    for (const d of data.dirs) list.appendChild(row(d.name, () => open(d.path), "#i-folder"));
    for (const f of data.files) list.appendChild(row(f.name, () => choose(f.path), "#i-film", "file"));
    emptyEl.hidden = !!(data.dirs.length || data.files.length);
    (list.querySelector("button") || cancelBtn).focus();
  }

  function choose(path) {
    value.value = path;
    dialog.close();
    lastFocus = value;
  }

  openBtn.addEventListener("click", () => {
    lastFocus = document.activeElement;
    dialog.showModal();
    open("");
  });
  cancelBtn.addEventListener("click", () => dialog.close());
  upBtn.addEventListener("click", () => parent && open(parent));
  // A click on the ::backdrop lands on the dialog element itself (rows sit inside <ul>).
  dialog.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); });
  dialog.addEventListener("close", () => lastFocus && lastFocus.focus());
})();
