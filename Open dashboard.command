#!/bin/bash
# Double-click this in Finder to open the editable dashboard in your browser.
# It serves whatever is already in the database — it does not fetch anything.
cd "$(dirname "$0")" || exit 1
# shellcheck source=tools/python.sh
. tools/python.sh
python=$(find_python) || {
  echo "job-search-agent needs Python 3.10 or newer. Install it from"
  echo "https://www.python.org/downloads/macos/ , then double-click this again."
  read -r -n 1
  exit 1
}
printf '\033]0;job-search-agent — dashboard\007'
"$python" -m jsa serve || {
  status=$?
  echo
  echo "The dashboard stopped with exit code $status."
  echo "Press any key to close this window."
  read -r -n 1
  exit $status
}
