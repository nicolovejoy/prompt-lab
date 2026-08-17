/* Prompt Lab page-view beacon (issue #9).
 *
 * One line per site:  <script defer src="https://prompt-labs.org/beacon.js"></script>
 *
 * Sends a single anonymous pageview per load via sendBeacon (text/plain, so
 * no CORS preflight). No cookies, no identifiers — the server derives the
 * site from the Origin header and a daily-rotating visitor hash; raw IPs are
 * never stored.
 *
 * Automation (issue #52): this used to `return` early on navigator.webdriver,
 * which made test traffic invisible rather than excluded — and covered none of
 * the automation that drives a real, non-webdriver Chrome. It now REPORTS the
 * signal instead (`wd`), the server writes the row with `agent = 1`, and every
 * visitor-facing read filters those out. Labelled beats discarded: the volume
 * stays measurable and misclassification is recoverable.
 *
 * Harness kill-switch, for automation that sets no webdriver flag: load any
 * page once with `?pl_agent=1`, or set `localStorage.pl_agent = '1'` before
 * navigating. It sticks for that origin until cleared with
 * `localStorage.removeItem('pl_agent')`.
 *
 * Declared bot user-agents are still DROPPED server-side (never stored).
 */
(function () {
  var agent = 0;
  try {
    if (navigator.webdriver) agent = 1;
  } catch (e) { /* nothing */ }
  try {
    if (/[?&]pl_agent=1(&|$)/.test(location.search)) {
      localStorage.setItem('pl_agent', '1');
    }
    if (localStorage.getItem('pl_agent') === '1') agent = 1;
  } catch (e) { /* storage throws in sandboxed frames / blocked cookies */ }

  var data = JSON.stringify({
    path: location.pathname,
    ref: document.referrer,
    wd: agent
  });
  var url = 'https://prompt-labs.org/api/beacon';
  try {
    if (navigator.sendBeacon) {
      navigator.sendBeacon(url, new Blob([data], { type: 'text/plain' }));
    } else {
      fetch(url, { method: 'POST', body: data, mode: 'no-cors', keepalive: true });
    }
  } catch (e) { /* never break the host page */ }
})();
