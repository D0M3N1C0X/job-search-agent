#!/bin/bash
# Double-click this in Finder to open the editable dashboard in your browser.
# It serves whatever is already in the database — it does not fetch anything.
cd "$(dirname "$0")" || exit 1
printf '\033]0;job-search-agent — dashboard\007'
python3 -m jsa serve || {
  status=$?
  echo
  echo "The dashboard stopped with exit code $status."
  echo "Press any key to close this window."
  read -r -n 1
  exit $status
}
