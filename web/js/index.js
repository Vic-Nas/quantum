// Smooth scroll from countdown rows to detail cards; highlight on arrival.
(function () {
  document.querySelectorAll('.cd .row').forEach(function (link) {
    link.addEventListener('click', function (ev) {
      var href = link.getAttribute('href');
      if (!href) return;
      var target = document.querySelector(href);
      if (!target) return;
      ev.preventDefault();
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      target.classList.add('hl');
      setTimeout(function () { target.classList.remove('hl'); }, 600);
      if (history.replaceState) history.replaceState(null, '', href);
    });
  });
  // If the URL has a hash pointing to a detail section, highlight it
  if (location.hash) {
    var el = document.querySelector(location.hash);
    if (el && el.classList.contains('detail')) {
      el.classList.add('hl');
      setTimeout(function () { el.classList.remove('hl'); }, 600);
    }
  }
})();
