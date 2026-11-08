#!/usr/bin/env bash
# anticlaudity installer.
#
#   curl -fsSL https://raw.githubusercontent.com/jurek-zsl/anticlaudity/main/install.sh | bash
#
# Works from a local checkout too (./install.sh). Re-running updates in place.
#
# Env overrides:
#   ANTICLAUDITY_REPO   git URL to clone      (default: github.com/jurek-zsl/anticlaudity)
#   ANTICLAUDITY_REF    branch/tag to install (default: main)
#   ANTICLAUDITY_HOME   where the clone lives (default: ~/.local/share/anticlaudity)
#   ANTICLAUDITY_BIN    where to link the CLI (default: ~/.local/bin)
#   CLAUDE_CONFIG_DIR   Claude config dir     (default: ~/.claude)
set -euo pipefail

REPO="${ANTICLAUDITY_REPO:-https://github.com/jurek-zsl/anticlaudity.git}"
REF="${ANTICLAUDITY_REF:-main}"
DEST="${ANTICLAUDITY_HOME:-$HOME/.local/share/anticlaudity}"
BIN_DIR="${ANTICLAUDITY_BIN:-$HOME/.local/bin}"
SKILLS_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills"

say()  { printf '%s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# --- prerequisites ---------------------------------------------------------
command -v python3 >/dev/null 2>&1 || die "python3 is required (3.8+)"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' \
  || die "python3 3.8+ is required (found $(python3 -V 2>&1))"

# --- locate source: local checkout, or clone/update ------------------------
src=""
self="${BASH_SOURCE[0]:-}"
if [ -n "$self" ] && [ -f "$self" ]; then
  candidate="$(cd "$(dirname "$self")" && pwd)"
  if [ -f "$candidate/bin/anticlaudity" ] && [ -d "$candidate/skills/delegate-to-antigravity" ]; then
    src="$candidate"
  fi
fi

if [ -z "$src" ]; then
  command -v git >/dev/null 2>&1 || die "git is required to install from GitHub"
  if [ -d "$DEST/.git" ]; then
    say "Updating $DEST ($REF)..."
    git -C "$DEST" fetch --quiet --depth 1 origin "$REF"
    git -C "$DEST" checkout --quiet -B "$REF" FETCH_HEAD
  else
    [ -e "$DEST" ] && [ -n "$(ls -A "$DEST" 2>/dev/null)" ] && die "$DEST exists and is not an anticlaudity clone"
    say "Cloning $REPO ($REF) into $DEST..."
    mkdir -p "$(dirname "$DEST")"
    git clone --quiet --depth 1 --branch "$REF" "$REPO" "$DEST"
  fi
  src="$DEST"
fi

# --- link CLI and skill ----------------------------------------------------
link() {  # link <target> <linkpath>
  local target="$1" path="$2"
  if [ -e "$path" ] && [ ! -L "$path" ]; then
    die "$path exists and is not a symlink; move it away and re-run"
  fi
  ln -sfn "$target" "$path"
}

mkdir -p "$BIN_DIR" "$SKILLS_DIR"
chmod +x "$src/bin/anticlaudity"
link "$src/bin/anticlaudity" "$BIN_DIR/anticlaudity"
link "$src/skills/delegate-to-antigravity" "$SKILLS_DIR/delegate-to-antigravity"

say ""
say "Installed anticlaudity:"
say "  CLI   $BIN_DIR/anticlaudity -> $src/bin/anticlaudity"
say "  Skill $SKILLS_DIR/delegate-to-antigravity"

# --- sanity checks ---------------------------------------------------------
command -v agy >/dev/null 2>&1 || warn "'agy' (Antigravity CLI) not found on PATH; anticlaudity needs it to do any work"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) warn "$BIN_DIR is not on your PATH. Add this to your shell profile:  export PATH=\"$BIN_DIR:\$PATH\"" ;;
esac

say ""
say "Next: restart Claude Code so it picks up the skill, then try:"
say "  anticlaudity \"Summarize this file\" --path README.md"
say "  anticlaudity stats"
