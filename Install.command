#!/bin/bash
# Double-click this in Finder to install job-search-agent from this folder:
# a `jsa` command, a "Job Pipeline" app, and your profile, step by step.
# It runs install.sh, which you can read first; nothing is downloaded.
cd "$(dirname "$0")" || exit 1
printf '\033]0;job-search-agent — install\007'
bash ./install.sh
status=$?
echo
if [ $status -eq 0 ]; then
  echo "Installed. You can close this window."
else
  echo "The installer stopped with exit code $status (the reason is above)."
fi
echo "Press any key to close this window."
read -r -n 1
exit $status
