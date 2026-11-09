// Side nav + countdown bar: click to switch the visible detail panel.
(function () {
  function activate(tabId) {
    document.querySelectorAll('.d-nav .dn-item').forEach(function (btn) {
      btn.classList.toggle('active', btn.getAttribute('data-tab') === tabId);
    });
    document.querySelectorAll('.d-panels .detail').forEach(function (panel) {
      panel.classList.toggle('active', panel.id === tabId);
    });
  }
  document.addEventListener('click', function (ev) {
    var btn = ev.target.closest('[data-tab]');
    if (!btn) return;
    ev.preventDefault();
    var tabId = btn.getAttribute('data-tab');
    activate(tabId);
    var details = document.getElementById('details');
    if (details && btn.closest('.cd')) {
      details.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
})();
