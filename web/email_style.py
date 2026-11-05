"""Shared look for every email and bare HTML page the lab sends (R11, R12).

One palette, the dashboard's LIGHT theme tokens (web/index.html), text-safe on
white. Emails declare `color-scheme: light` and stay light: dark rendering
differs across Mail, Gmail and iOS, so a declared light scheme is the
predictable choice (design review R11, 2026-11-04). Revisit only if a
dark-mode complaint appears.

Imported by send-review.py (repo root, with web/ on sys.path) and by
web/api/*.py (listed in web/vercel.json includeFiles). Standard library only.
"""

from html import escape

# Light-theme tokens, same values as web/index.html's light blocks.
BG = "#fafafa"
CARD = "#ffffff"
TEXT = "#111111"
TEXT_SECONDARY = "#404040"
MUTED = "#5c5c5c"
BORDER = "#e5e5e5"
LINK = "#4f46e5"
GOOD = "#14743a"   # --green
WARN = "#8a5a06"   # --yellow
BAD = "#dc2626"    # --red

FONT = "-apple-system,BlinkMacSystemFont,system-ui,sans-serif"
MONO = "ui-monospace,SFMono-Regular,Menlo,monospace"

# The machine-voice mark (CLAUDE.md "Machine-voice convention").
MACHINE_MARK = "↳ from claude"


def machine_mark_html():
    return f"<span style='color:{MUTED};font-style:italic;font-size:12px'>{MACHINE_MARK}</span>"


def machine_html(inner_html):
    """AI-authored text: italic, secondary colour, then the mark."""
    return (f"<span style='font-style:italic;color:{TEXT_SECONDARY}'>{inner_html}</span> "
            f"{machine_mark_html()}")


def document(body_html, title="", width=600):
    """A full email document: declared light scheme, page background, and a
    centred white card `width` px wide holding `body_html`."""
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta name='color-scheme' content='light'>"
        "<meta name='supported-color-schemes' content='light'>"
        f"<title>{escape(title)}</title>"
        "<style>:root{color-scheme:light;supported-color-schemes:light}</style>"
        "</head>"
        f"<body style='margin:0;padding:0;background:{BG};color:{TEXT};font-family:{FONT}'>"
        f"<div style='max-width:{width}px;margin:0 auto;padding:24px;background:{CARD};"
        f"color:{TEXT};font-family:{FONT};font-size:15px;line-height:1.5'>"
        f"{body_html}</div></body></html>"
    )


def page(message, heading=None):
    """A bare status page (pause link, sign-in failure): one message, escaped."""
    head = (f"<h1 style='font-size:20px;margin:0 0 12px'>{escape(heading)}</h1>"
            if heading else "")
    return document(f"{head}<p style='margin:0'>{escape(message)}</p>",
                    title=heading or "Prompt Lab", width=560)
