# Managed by prompt-lab/workflow/install.sh. The helper is installed outside
# project workspaces, so Codex cannot modify it before invoking this rule.
prefix_rule(
    pattern = [
        "__GC_WRITE_PATH__",
        ["register-session", "update-session-summary", "end-session", "save-daily-summary"],
    ],
    decision = "allow",
    justification = "Allow the reviewed Prompt Lab helper to update only validated session bookkeeping",
    match = [
        "__GC_WRITE_PATH__ register-session",
        "__GC_WRITE_PATH__ update-session-summary 610 /tmp/gc-session-610-smoke.txt",
        "__GC_WRITE_PATH__ end-session 610",
        "__GC_WRITE_PATH__ save-daily-summary /tmp/gc-daily-songpath-610.json",
    ],
    not_match = [
        "__GC_WRITE_PATH__",
        "__GC_WRITE_PATH__.bak update-session-summary 610 /tmp/gc-session-610-smoke.txt",
    ],
)
