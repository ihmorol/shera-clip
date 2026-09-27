// Shared page behavior: confirm dialogs, loading state on submit, local timestamps.
document.addEventListener("submit", (e) => {
  const form = e.target;
  if (form.dataset.confirm && !confirm(form.dataset.confirm)) { e.preventDefault(); return; }
  const btn = form.querySelector("button[type=submit]");
  if (btn) { btn.classList.add("loading"); btn.setAttribute("aria-busy", "true"); }
});

for (const el of document.querySelectorAll(".local-time")) {
  el.textContent = new Date(parseFloat(el.dataset.ts) * 1000).toLocaleString();
}
