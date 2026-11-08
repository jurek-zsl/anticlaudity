#!/usr/bin/env bash
# anticlaudity uninstaller.
#
#   curl -fsSL https://raw.githubusercontent.com/jurek-zsl/anticlaudity/main/uninstall.sh | bash
#
# Removes the CLI and skill symlinks (only if they point at anticlaudity) and the
# managed clone. Your ledger (~/.anticlaudity/) is kept; delete it yourself if unwanted.
set -euo pipefail

DEST="${ANTICLAUDITY_HOME:-$HOME/.local/share/anticlaudity}"
BIN_DIR="${ANTICLAUDITY_BIN:-$HOME/.local/bin}"
SKILLS_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills"

unlink_if_ours() {  # unlink_if_ours <path>
  local path="$1"
  if [ -L "$path" ]; then
    case "$(readlink "$path")" in
      */anticlaudity|*/anticlaudity/*) rm "$path"; echo "Removed $path" ;;
      *) echo "Skipped $path (does not point at anticlaudity)" ;;
    esac
  fi
}

unlink_if_ours "$BIN_DIR/anticlaudity"
unlink_if_ours "$SKILLS_DIR/delegate-to-antigravity"

if [ -d "$DEST/.git" ]; then
  rm -rf "$DEST"
  echo "Removed $DEST"
fi

echo "Done. Ledger kept at ~/.anticlaudity/ (delete manually if you want)."
