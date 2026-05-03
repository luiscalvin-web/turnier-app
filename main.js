
(function () {
  const key = "scroll:" + window.location.pathname;
  const saved = sessionStorage.getItem(key);
  if (saved !== null) {
    window.scrollTo(0, parseInt(saved, 10));
  }

  let timeoutId = null;
  window.addEventListener("scroll", function () {
    if (timeoutId) return;
    timeoutId = setTimeout(function () {
      sessionStorage.setItem(key, String(window.scrollY));
      timeoutId = null;
    }, 100);
  });

  window.addEventListener("beforeunload", function () {
    sessionStorage.setItem(key, String(window.scrollY));
  });

  document.querySelectorAll(".preserve-scroll-link").forEach(function (el) {
    el.addEventListener("click", function () {
      sessionStorage.setItem(key, String(window.scrollY));
    });
  });

  document.querySelectorAll(".preserve-scroll-form").forEach(function (form) {
    form.addEventListener("submit", function () {
      sessionStorage.setItem(key, String(window.scrollY));
    });
  });
})();
