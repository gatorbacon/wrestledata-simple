// Google Analytics 4 (GA4) tracking
(function() {
  // Load the gtag.js library asynchronously
  const script = document.createElement('script');
  script.async = true;
  script.src = 'https://www.googletagmanager.com/gtag/js?id=G-LF2J4B0JKW';
  document.head.appendChild(script);

  // Initialize dataLayer and gtag function
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  window.gtag = gtag;
  
  // Configure GA4
  gtag('js', new Date());
  gtag('config', 'G-LF2J4B0JKW', {
    anonymize_ip: true,
    send_page_view: false
  });
})();

