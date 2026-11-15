#!/bin/bash
# job-search-agent — install, or update, in one line:
#
#   curl -fsSL https://raw.githubusercontent.com/D0M3N1C0X/job-search-agent/main/install.sh | bash
#
# What it does, in order, and nothing else:
#   1. finds a Python 3.10 or newer (it never installs one: it tells you where to get it);
#   2. downloads the code into ~/job-search-agent (no git needed), or, if it is
#      already there, updates it, leaving profile/ (your CV, tracks, database) alone;
#   3. runs `jsa install`: a `jsa` command in your PATH and, on macOS, a
#      "Job Pipeline" app that opens the dashboard;
#   4. the first time only, asks whether to read your CV, ask you questions, or show the demo;
#   5. opens the dashboard.
#
# No administrator password, nothing outside your home directory, and
# `jsa uninstall` removes the command and the app. Read it before running it:
# that is the point of keeping it this short.
#
# Settings, all optional:
#   JSA_DIR=~/somewhere        where the code goes (default ~/job-search-agent)
#   JSA_PYTHON=/path/python3   use this interpreter
#   JSA_NONINTERACTIVE=1       ask nothing (for scripts and CI)
#   JSA_NO_OPEN=1              do not open the dashboard at the end
#   JSA_SOURCE=url-or-file     a different tarball (tests use a local one)

# Everything is inside main, which runs on the last line: a download cut off
# halfway through defines a function and runs nothing.
set -euo pipefail

REPO="D0M3N1C0X/job-search-agent"
TARBALL="https://codeload.github.com/$REPO/tar.gz/refs/heads/main"
MARKER=".jsa-download"

say()  { printf '%s\n' "$*"; }
bold() { if [ -t 1 ]; then printf '\033[1m%s\033[0m\n' "$*"; else printf '%s\n' "$*"; fi; }
fail() { printf '\n%s\n' "$*" >&2; exit 1; }

# --- find_python (keep in step with tools/python.sh) ---
# Sourced by the launchers, and copied verbatim into install.sh (a test keeps
# the two in step): find a Python 3.10 or newer, print its path, or fail.
#
# The macOS /usr/bin/python3 is a stub until the developer tools are installed,
# and calling it then opens a dialog box instead of answering, so it is only
# asked when the tools are there. It is Python 3.9 on most Macs anyway.
find_python() {
  local candidate
  for candidate in "${JSA_PYTHON:-}" python3.14 python3.13 python3.12 python3.11 python3.10 \
      /opt/homebrew/bin/python3 /usr/local/bin/python3 \
      /Library/Frameworks/Python.framework/Versions/Current/bin/python3 python3; do
    [ -n "$candidate" ] || continue
    candidate=$(command -v "$candidate" 2>/dev/null) || continue
    if [ "$candidate" = /usr/bin/python3 ] && [ "$(uname -s)" = Darwin ] \
        && ! xcode-select -p >/dev/null 2>&1; then
      continue
    fi
    if "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}
# --- end find_python ---

no_python() {
  if [ "$(uname -s)" = Darwin ]; then
    fail "job-search-agent needs Python 3.10 or newer, and this Mac does not have one.

Install it from https://www.python.org/downloads/macos/ (the \"macOS 64-bit
universal2 installer\": open it and click through), then run this line again.
If you use Homebrew, \`brew install python\` does the same."
  fi
  fail "job-search-agent needs Python 3.10 or newer, and none was found.

Install it with your system's package manager, for example
  sudo apt install python3        (Debian, Ubuntu)
  sudo dnf install python3        (Fedora)
then run this line again. To use a Python that is not on your PATH, set
JSA_PYTHON=/path/to/python3."
}

# Where this script lives, when it is run from a file inside a copy of the
# repository (Install.command does that): then there is nothing to download.
local_checkout() {
  local here
  [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ] || return 1
  here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
  [ -f "$here/jsa/__init__.py" ] && [ -f "$here/profile.example/profile.json" ] || return 1
  printf '%s\n' "$here"
}

download() {
  local dir=$1 top
  command -v tar >/dev/null || fail "tar is needed to unpack the download and is not installed."
  tmp=$(mktemp -d "${TMPDIR:-/tmp}/jsa-install.XXXXXX")   # global: the trap runs after this returns
  trap 'rm -rf "$tmp"' EXIT
  local source=${JSA_SOURCE:-$TARBALL}
  if [ -f "$source" ]; then
    cp "$source" "$tmp/code.tar.gz"
  else
    command -v curl >/dev/null || fail "curl is needed to download the code and is not installed."
    say "Downloading the code from github.com/$REPO …"
    curl -fsSL --retry 3 -o "$tmp/code.tar.gz" "$source" \
      || fail "The download failed. Check the connection and run the line again; nothing was changed."
  fi
  mkdir "$tmp/new"
  tar -xzf "$tmp/code.tar.gz" -C "$tmp/new" || fail "The download is not a valid archive; nothing was changed."
  top=$(find "$tmp/new" -mindepth 1 -maxdepth 1 -type d | head -n 1)
  [ -n "$top" ] && [ -f "$top/jsa/__init__.py" ] \
    || fail "The download does not contain job-search-agent; nothing was changed."
  rm -rf "$top/profile"            # never shipped, but never let an archive bring one either

  if [ -d "$dir/.git" ]; then
    say "$dir is a git clone: updating it with git instead."
    git -C "$dir" pull --ff-only || fail "git could not update $dir (local changes?). Nothing else was changed."
    return 0
  fi
  if [ -e "$dir" ] && [ ! -f "$dir/$MARKER" ] && [ -n "$(ls -A "$dir" 2>/dev/null)" ]; then
    fail "$dir already exists and was not made by this installer, so it is left alone.
Move it, or choose another folder: JSA_DIR=~/elsewhere, then run the line again."
  fi
  mkdir -p "$dir"
  # jsa/ is replaced whole so a module removed upstream cannot linger; the rest
  # is copied over, file by file. profile/ is not in the archive: it is untouched.
  rm -rf "$dir/jsa"
  cp -R "$top/." "$dir/"
  printf '%s\n' "$source" > "$dir/$MARKER"
}

# A path dragged into Terminal arrives with its spaces escaped, or in quotes.
clean_path() {
  local path=$1
  path=${path%"${path##*[![:space:]]}"}
  path=${path#"${path%%[![:space:]]*}"}
  path=${path#\'}; path=${path%\'}; path=${path#\"}; path=${path%\"}
  path=${path//\\ / }
  case $path in \~/*) path="$HOME/${path#\~/}" ;; esac
  printf '%s\n' "$path"
}

first_run() {
  local python=$1 dir=$2 choice cv
  bold ""
  bold "Your profile"
  say "There is no profile yet. How would you like to start?"
  say "  1  read the CV I already have (PDF, Word or text)"
  say "  2  answer a few questions instead"
  say "  3  look at the demo first, with an invented candidate"
  say "  4  later"
  printf 'Choose 1–4 [1]: '
  read -r choice </dev/tty || choice=4
  case ${choice:-1} in
    1)
      printf 'Drag your CV file into this window, then press Enter: '
      read -r cv </dev/tty || cv=""
      cv=$(clean_path "$cv")
      if [ -n "$cv" ] && [ -f "$cv" ]; then
        (cd "$dir" && "$python" -m jsa import "$cv") </dev/tty || say "The CV could not be read; \`jsa setup\` asks the questions instead."
        say ""
        say "Next, choose the kinds of role to look for: run \`jsa setup\` and pick two or three tracks."
      else
        say "No file at \"$cv\". Run \`jsa import <file>\` when you have it."
      fi ;;
    2) (cd "$dir" && "$python" -m jsa setup) </dev/tty || true ;;
    3) DEMO=1 ;;
    *) say "Fine: \`jsa import <cv>\` or \`jsa setup\` whenever you are ready." ;;
  esac
}

open_dashboard() {
  local python=$1 dir=$2
  if [ "${DEMO:-}" = 1 ]; then
    say "Opening the demo (Ctrl-C here stops it)…"
    (cd "$dir" && "$python" -m jsa demo) </dev/tty || true
    return 0
  fi
  if [ "$(uname -s)" = Darwin ] && [ -d "$HOME/Applications/Job Pipeline.app" ]; then
    open "$HOME/Applications/Job Pipeline.app" && say "The dashboard is opening in your browser."
  else
    say "Open the dashboard with: jsa serve"
  fi
}

main() {
  local python dir fresh=1 interactive=1
  bold "job-search-agent installer"
  python=$(find_python) || no_python
  say "Python: $python ($("$python" -c 'import platform; print(platform.python_version())'))"

  if dir=$(local_checkout); then
    say "Installing from this folder: $dir"
    # A downloaded ZIP: from now on `jsa update` may refresh it the same way.
    [ -d "$dir/.git" ] || [ -f "$dir/$MARKER" ] || printf '%s\n' "$TARBALL" > "$dir/$MARKER"
  else
    dir=${JSA_DIR:-$HOME/job-search-agent}
    case $dir in \~/*) dir="$HOME/${dir#\~/}" ;; esac
    [ -d "$dir/jsa" ] && fresh=0
    download "$dir"
    if [ "$fresh" = 1 ]; then say "Installed into $dir"; else say "Updated $dir (profile/ untouched)"; fi
  fi

  bold ""
  (cd "$dir" && "$python" -m jsa install)

  if [ -n "${JSA_NONINTERACTIVE:-}" ] || ! { : </dev/tty; } 2>/dev/null; then
    interactive=0
  fi
  if [ "$interactive" = 1 ] && [ -z "${JSA_HOME:-}" ] && [ ! -f "$dir/profile/profile.json" ]; then
    first_run "$python" "$dir"
  fi

  bold ""
  bold "Done"
  say "  code       $dir"
  say "  your data  $dir/profile   (never sent anywhere, never overwritten by an update)"
  say "  update     jsa update     (or run this line again)"
  say "  remove     jsa uninstall, then delete the folder"
  if [ -z "${JSA_NO_OPEN:-}" ] && [ "$interactive" = 1 ]; then
    open_dashboard "$python" "$dir"
  fi
}

main "$@"
