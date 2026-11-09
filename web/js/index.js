// Click a line, a label or a dot to show its source in the panel below. Without JS the server-rendered default
// and the :target fallback in the CSS still work.
(function () {
  function select(id, scroll) {
    var art = document.getElementById(id);
    if (!art) return;
    document.querySelectorAll(".proof").forEach(function (p) { p.classList.toggle("is-sel", p === art); });
    document.querySelectorAll("[data-id]").forEach(function (d) { d.classList.toggle("is-sel", d.getAttribute("data-id") === id); });
    if (scroll) art.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
  document.addEventListener("click", function (ev) {
    var a = ev.target.closest("[data-id]");
    if (!a) return;
    ev.preventDefault();
    var id = a.getAttribute("data-id");
    select(id, window.matchMedia("(max-width: 900px)").matches);
    if (history.replaceState) history.replaceState(null, "", "#" + id);
  });
  var sel = document.querySelector(".proof.is-sel");
  if (sel) document.querySelectorAll('[data-id="' + sel.id + '"]').forEach(function (d) { d.classList.add("is-sel"); });
  if (location.hash.length > 1) select(location.hash.slice(1), false);
})();
