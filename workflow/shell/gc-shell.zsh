# gc-shell.zsh — shared zsh config synced across machines via prompt-lab.
# Installed to ~/.claude/shell/gc-shell.zsh and sourced from ~/.zshrc by
# workflow/install.sh. Put machine-agnostic shell bits here so both the
# laptop and the mini stay in sync; keep machine-specific config in ~/.zshrc.

# Show the current directory in the iTerm2 tab + window title; updates on every cd.
precmd() {
    print -Pn "\e]0;%~\a"
}
