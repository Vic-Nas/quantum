// 1) Tabs: the headline tiles switch between targets. Without JS every target stays visible and the tiles are plain anchors.
// 2) Proof: click a dot (or an "also published" link) to show that paper's proof.
(function () {
  var tabs = Array.prototype.slice.call(document.querySelectorAll(".hl[data-tab]"));

  function activate(panelId, focus) {
    var panel = document.getElementById(panelId);
    if (!panel) return;
    document.querySelectorAll(".target").forEach(function (t) { t.classList.toggle("is-active", t === panel); });
    tabs.forEach(function (t) {
      var on = t.getAttribute("data-tab") === panelId;
      t.classList.toggle("is-active", on);
      t.setAttribute("aria-selected", on ? "true" : "false");
      t.setAttribute("tabindex", on ? "0" : "-1");
      if (on && focus) t.focus();
    });
  }

  function select(id, scroll) {
    var art = document.getElementById(id);
    if (!art) return;
    var section = art.closest(".target");
    activate(section.id, false);
    section.querySelectorAll(".proof").forEach(function (p) { p.classList.toggle("is-sel", p === art); });
    section.querySelectorAll(".dot").forEach(function (d) { d.classList.toggle("is-sel", d.getAttribute("data-id") === id); });
    if (scroll && window.matchMedia("(max-width: 900px)").matches) art.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  document.addEventListener("click", function (ev) {
    var tab = ev.target.closest("[data-tab]");
    if (tab) {
      ev.preventDefault();
      activate(tab.getAttribute("data-tab"), false);
      if (history.replaceState) history.replaceState(null, "", "#" + tab.getAttribute("data-tab"));
      return;
    }
    var a = ev.target.closest("[data-id]");
    if (!a) return;
    ev.preventDefault();
    select(a.getAttribute("data-id"), true);
    if (history.replaceState) history.replaceState(null, "", "#" + a.getAttribute("data-id"));
  });

  document.addEventListener("keydown", function (ev) {
    var tab = ev.target.closest && ev.target.closest(".hl[data-tab]");
    if (!tab || (ev.key !== "ArrowRight" && ev.key !== "ArrowLeft")) return;
    var i = tabs.indexOf(tab) + (ev.key === "ArrowRight" ? 1 : -1);
    activate(tabs[(i + tabs.length) % tabs.length].getAttribute("data-tab"), true);
    ev.preventDefault();
  });

  document.querySelectorAll(".proof.is-sel").forEach(function (p) {
    document.querySelectorAll('.dot[data-id="' + p.id + '"]').forEach(function (d) { d.classList.add("is-sel"); });
  });
  var first = tabs[0] && tabs[0].getAttribute("data-tab");
  if (first) activate(first, false);
  var h = location.hash.slice(1);
  if (h) { if (document.querySelector('[data-tab="' + h + '"]')) activate(h, false); else select(h, false); }
})();
