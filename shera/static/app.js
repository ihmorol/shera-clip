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



const librarySearch = document.querySelector("[data-library-search]");

const libraryStatus = document.querySelector("[data-library-status]");

if (librarySearch && libraryStatus) {

  const videos = [...document.querySelectorAll("[data-library-item]")];

  const empty = document.querySelector("[data-library-empty]");

  const filterLibrary = () => {

    const query = librarySearch.value.trim().toLocaleLowerCase();

    let visible = 0;

    for (const video of videos) {

      video.hidden = !video.dataset.title.toLocaleLowerCase().includes(query) ||

        Boolean(libraryStatus.value && video.dataset.status !== libraryStatus.value);

      if (!video.hidden) visible++;

    }

    if (empty) empty.hidden = visible > 0;

  };

  librarySearch.addEventListener("input", filterLibrary);

  libraryStatus.addEventListener("change", filterLibrary);

}


const candidateSearch = document.querySelector("[data-candidate-search]");
const candidateStatus = document.querySelector("[data-candidate-status]");
if (candidateSearch && candidateStatus) {
  const candidates = [...document.querySelectorAll(".shot[data-search][data-status], .others tr[data-search][data-status]")];
  const count = document.querySelector("[data-filter-count]");
  const filterCandidates = () => {
    const query = candidateSearch.value.trim().toLocaleLowerCase();
    const status = candidateStatus.value;
    let visible = 0;
    for (const candidate of candidates) {
      candidate.hidden = !candidate.dataset.search.toLocaleLowerCase().includes(query) ||
        Boolean(status && status !== "all" && candidate.dataset.status !== status);
      if (!candidate.hidden) visible++;
    }
    if (count) count.textContent = `${visible} of ${candidates.length} candidates match`;
  };
  candidateSearch.addEventListener("input", filterCandidates);
  candidateStatus.addEventListener("change", filterCandidates);
}

for (const link of document.querySelectorAll(".primary-nav a")) {
  const destination = new URL(link.href);
  if (destination.pathname === location.pathname &&
      (destination.hash ? destination.hash === (location.hash || "#jobs-h") : true)) {
    link.setAttribute("aria-current", "page");
  }
}
