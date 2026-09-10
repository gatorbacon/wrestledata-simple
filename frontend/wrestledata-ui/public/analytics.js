// Google Analytics 4 (GA4) tracking for matsavant.com.
// send_page_view is off -- header.js fires the pageview manually once the
// page's title is final (every page here has a static title except
// notes/note.html, which sets its title from a fetch and fires its own
// pageview after that completes -- see note.js).

(function () {
  const script = document.createElement("script");
  script.async = true;
  script.src = "https://www.googletagmanager.com/gtag/js?id=G-DRHRDZF2DV";
  document.head.appendChild(script);

  window.dataLayer = window.dataLayer || [];
  function gtag() {
    dataLayer.push(arguments);
  }
  window.gtag = gtag;

  gtag("js", new Date());
  gtag("config", "G-DRHRDZF2DV", {
    send_page_view: false,
  });
})();
