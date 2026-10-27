#!/bin/bash
# Double-click this file in Finder to start the ETDRS Logger.
cd "$(dirname "$0")" || exit 1

# Prefer the python.org install (it includes Tk); fall back to whatever python3 is on the PATH.
PY=""
for candidate in \
    /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
    /usr/local/bin/python3 \
    python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import tkinter" >/dev/null 2>&1; then
    PY="$candidate"
    break
  fi
done

if [ -z "$PY" ]; then
  echo "Could not find Python 3 with tkinter."
  echo "Install Python 3 from https://www.python.org/downloads/ and try again."
  read -r -p "Press Return to close this window."
  exit 1
fi

"$PY" etdrs_logger.py
status=$?
if [ $status -ne 0 ]; then
  echo
  echo "ETDRS Logger stopped with an error (see the message above)."
  read -r -p "Press Return to close this window."
fi
exit $status
