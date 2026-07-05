/* Prompt Lab page-view beacon (issue #9).
 *
 * One line per site:  <script defer src="https://prompt-labs.org/beacon.js"></script>
 *
 * Sends a single anonymous pageview per load via sendBeacon (text/plain, so
 * no CORS preflight). No cookies, no identifiers — the server derives the
 * site from the Origin header and a daily-rotating visitor hash; raw IPs are
 * never stored. Automation (navigator.webdriver) is skipped client-side and
 * bot user-agents are dropped server-side.
 */
(function () {
  if (navigator.webdriver) return;
  var data = JSON.stringify({ path: location.pathname, ref: document.referrer });
  var url = 'https://prompt-labs.org/api/beacon';
  try {
    if (navigator.sendBeacon) {
      navigator.sendBeacon(url, new Blob([data], { type: 'text/plain' }));
    } else {
      fetch(url, { method: 'POST', body: data, mode: 'no-cors', keepalive: true });
    }
  } catch (e) { /* never break the host page */ }
})();
