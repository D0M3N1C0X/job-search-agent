#!/bin/bash
# Double-click this in Finder to run the whole pipeline and open the dashboard.
# It works from wherever the repository lives — nothing is hard-coded.
cd "$(dirname "$0")" || exit 1
# shellcheck source=tools/python.sh
. tools/python.sh
python=$(find_python) || {
  echo "job-search-agent needs Python 3.10 or newer. Install it from"
  echo "https://www.python.org/downloads/macos/ , then double-click this again."
  read -r -n 1
  exit 1
}
printf '\033]0;job-search-agent — run\007'
echo "Running the pipeline from $(pwd)"
echo
"$python" -m jsa run --serve || {
  status=$?
  echo
  echo "The run stopped with exit code $status."
  echo "Press any key to close this window."
  read -r -n 1
  exit $status
}
