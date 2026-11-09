// Click a dot (or an "also published" link) to show that paper's proof. Without JS the
// server-rendered default and the :target fallback in the CSS still work.
(function () {
  function select(id, scroll) {
    var art = document.getElementById(id);
    if (!art) return;
    var section = art.closest(".target");
    section.querySelectorAll(".proof").forEach(function (p) { p.classList.toggle("is-sel", p === art); });
    section.querySelectorAll(".dot").forEach(function (d) { d.classList.toggle("is-sel", d.getAttribute("data-id") === id); });
    if (scroll && window.matchMedia("(max-width: 900px)").matches) art.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
  document.addEventListener("click", function (ev) {
    var a = ev.target.closest("[data-id]");
    if (!a) return;
    ev.preventDefault();
    select(a.getAttribute("data-id"), true);
    if (history.replaceState) history.replaceState(null, "", "#" + a.getAttribute("data-id"));
  });
  document.querySelectorAll(".proof.is-sel").forEach(function (p) {
    document.querySelectorAll('.dot[data-id="' + p.id + '"]').forEach(function (d) { d.classList.add("is-sel"); });
  });
  if (location.hash.length > 1) select(location.hash.slice(1), false);
})();
