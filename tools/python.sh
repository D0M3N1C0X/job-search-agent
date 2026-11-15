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
