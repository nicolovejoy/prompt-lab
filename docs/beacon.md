# Beacon interface

How a site reports page views to Prompt Lab. Read this if you own a site that
sends (or will send) hits to `https://prompt-labs.org/api/beacon`.

No cookies, no stored IPs. The site name comes from the request's `Origin`
header. The measurement rules are in [measurement-policy.md](measurement-policy.md).

## The interface

Endpoint: `POST https://prompt-labs.org/api/beacon`

The body is JSON. The request content type does not matter, and `text/plain` is
the normal choice because it avoids a CORS preflight. Fields:

- `path` (required): the page path. Must start with `/`. Query string and
  `#hash` are cut off.
- `ref`: `document.referrer`. Only the hostname is kept. A referrer from the
  same site is stored as empty.
- `wd` or `agent`: set to `1`/`true` when the page is driven by browser
  automation. The hit is stored but labelled, and the dashboard leaves it out.
- `event`: `pageview` (default) or `nav`. Nothing else is accepted.

The whole body must fit in 2 KB. A longer body is cut at 2 KB, which leaves
JSON that does not parse, so the hit is dropped.

The site is taken from the `Origin` header (falling back to `Referer`), with a
leading `www.` removed. Browsers set `Origin` on `POST`; do not try to send it
yourself. A page served with `Referrer-Policy: no-referrer` sends
`Origin: null` on a `POST`, and every hit from it is dropped as a bad origin.
Use a policy that keeps the origin: `strict-origin-when-cross-origin` (the
browser default) or `origin`.

A caller that can set headers can also mark a hit as automation with an
`X-Test-Agent: 1` header. It has the same effect as `wd` or `agent` in the
body. `sendBeacon` cannot set headers, which is why the body fields exist.

### Events

- `pageview`: one full page load. Stored with a daily-rotating visitor hash,
  country and device class.
- `nav`: an in-app route change in a single-page app, after the first load. It
  is coarsened before it is stored: no visitor hash, no country, no device, no
  referrer, and the time is cut to the UTC date. Only site, scrubbed path,
  event and the automation label are kept. This is deliberate: a per-visitor
  timestamped trail of navigations would be a session path. A `nav` hit does
  not need a visitor hash, so it is recorded even when the server has no salt.
  Each `nav` row is also stored under a random id rather than the next number
  in sequence, so the table holds no record of the order `nav` rows were
  written in. One caveat: the database host's point-in-time recovery keeps
  the order of writes for as long as it retains its backups.

Sign-ins (`login`) are recorded by Prompt Lab's own server when someone signs
in to the dashboard. They are not a beacon event: a `login` hit sent to this
endpoint is dropped.

### ID scrubbing

Before storage, each `/`-separated segment of `path` is replaced with `:id` if
it is any of:

- a UUID
- all digits (`/orders/48213` becomes `/orders/:id`)
- a token of 16 or more letters, digits or `_` that mixes at least two of
  lowercase, uppercase and digits

Empty segments are kept, so `/` stays `/` and a trailing slash survives. This
applies to every event.

It is a safety net, not a reason to put identifiers in URLs. It does not
catch:

- IDs that contain `-`, such as nanoid or base64url IDs and Firebase push IDs
- letter-and-digit IDs shorter than 16 characters (all-digit IDs are caught
  at any length)
- an email address used as a segment
- an ID inside a longer segment, such as a slug that ends in an ID

So do not send paths that carry identifiers in the first place. Skip admin and
other private pages, and where you can, send the route pattern rather than the
filled-in path.

### What gets dropped

A dropped hit gets no error that you can use; do not retry. Dropped:

- user agents that look like bots, crawlers, monitors or HTTP libraries
- an `Origin` that is missing, malformed, `localhost`, `127.*` or `*.local`
- a body that is not a JSON object, including one cut short at 2 KB
- an `Origin` of `null`, which a `no-referrer` policy produces
- any `event` other than `pageview` or `nav`, including `login`
- a `path` that is not a string starting with `/`
- a `pageview` when the server has no salt configured (a `nav` is not affected)

## The change promise

The body fields and events above are a fixed interface. Before prompt-lab
changes anything about them, it posts in the site's handoff channel first. A
contract test in `scripts/test_web_api.py` guards the behaviour, and
`web/beacon-v1.js` is frozen by a hash test: a change would be published as
`beacon-v2.js`, never as an edit to v1.

## Install

### Option A: copy-in snippet (recommended)

Use this where you own the site's code, or where some pages are sensitive and
you want to choose exactly what is sent. Plain JS, never throws. Save it as a
module (the Next.js example below imports it from `@/lib/pl-beacon`). To use
it from a plain `<script>` tag instead, remove the `export` keyword and call
`plBeacon('pageview')` once the page has loaded.

```js
export function plBeacon(event) {
  try {
    var agent = 0;
    try {
      if (navigator.webdriver) agent = 1;
      if (/[?&]pl_agent=1(&|$)/.test(location.search)) localStorage.setItem('pl_agent', '1');
      if (localStorage.getItem('pl_agent') === '1') agent = 1;
    } catch (e) {}
    var data = JSON.stringify({
      event: event,
      path: location.pathname,
      ref: document.referrer,
      wd: agent
    });
    var url = 'https://prompt-labs.org/api/beacon';
    if (navigator.sendBeacon) {
      navigator.sendBeacon(url, new Blob([data], { type: 'text/plain' }));
    } else {
      fetch(url, { method: 'POST', body: data, mode: 'no-cors', keepalive: true });
    }
  } catch (e) {}
}
```

Next.js App Router: a client component that sends `pageview` on the first
render and `nav` on each later path change. Mount it once in the root layout.

```tsx
'use client';
import { useEffect, useRef } from 'react';
import { usePathname } from 'next/navigation';
import { plBeacon } from '@/lib/pl-beacon';

export function Beacon() {
  const pathname = usePathname();
  const first = useRef(true);
  useEffect(() => {
    if (pathname.startsWith('/admin')) return;
    plBeacon(first.current ? 'pageview' : 'nav');
    first.current = false;
  }, [pathname]);
  return null;
}
```

Skip admin and other private paths, as above. The server scrubs ID-like
segments, but not sending is safer than scrubbing. Because the early return
leaves `first` alone, a visit that starts on an admin page sends its
`pageview` on the first public page.

### Option B: versioned script tag

For sites that want a one-line install. The file never changes, and the
integrity attribute makes the browser refuse it if it ever did:

```html
<script defer src="https://prompt-labs.org/beacon-v1.js" integrity="sha384-ONhBQw+nUkm9sHSzjh0NB2eoYzwhlmsVfP8Lyw1f2/ViSNHr+lwr82DK7p2W4pOI" crossorigin="anonymous"></script>
```

### Option C: legacy unversioned tag

```html
<script defer src="https://prompt-labs.org/beacon.js"></script>
```

Existing sites load this and it keeps working. Not recommended for new installs:
the file can change under the site.

### What the scripts send

`beacon.js` and `beacon-v1.js` send `pageview` only, once per load. They never
send `nav`, so a single-page app that wants in-app views needs Option A.
