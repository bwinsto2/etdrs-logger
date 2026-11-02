#!/bin/bash
# Double-click this file in Finder once to create "ETDRS Logger.app"
# (with its icon) in your Applications folder. You can then drag the app
# onto the Dock or the Desktop and start the ETDRS Logger from there.
#
# Run it again if you move or re-download the etdrs-logger folder.
cd "$(dirname "$0")" || exit 1
REPO="$(pwd)"

if [ ! -f "$REPO/etdrs_logger.py" ] || [ ! -f "$REPO/assets/ETDRSLogger.icns" ]; then
  echo "This file must stay inside the etdrs-logger folder, next to etdrs_logger.py."
  read -r -p "Press Return to close this window."
  exit 1
fi

APP_DIR="$HOME/Applications"
APP="$APP_DIR/ETDRS Logger.app"
mkdir -p "$APP_DIR" || exit 1
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" || exit 1
cp "$REPO/assets/ETDRSLogger.icns" "$APP/Contents/Resources/ETDRSLogger.icns"

cat > "$APP/Contents/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>
  <string>ETDRS Logger</string>
  <key>CFBundleDisplayName</key>
  <string>ETDRS Logger</string>
  <key>CFBundleIdentifier</key>
  <string>com.github.bwinsto2.etdrs-logger</string>
  <key>CFBundleExecutable</key>
  <string>ETDRS Logger</string>
  <key>CFBundleIconFile</key>
  <string>ETDRSLogger</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0</string>
  <key>LSMinimumSystemVersion</key>
  <string>10.13</string>
</dict>
</plist>
EOF

# The app's program: a small script that starts etdrs_logger.py from this folder.
LAUNCHER="$APP/Contents/MacOS/ETDRS Logger"
printf '#!/bin/bash\nREPO=%q\n' "$REPO" > "$LAUNCHER"
cat >> "$LAUNCHER" <<'EOF'
LOG="$HOME/Library/Logs/ETDRS Logger.log"

alert() {
  /usr/bin/osascript -e 'on run argv' -e 'display alert "ETDRS Logger" message (item 1 of argv) as critical' -e 'end run' "$1" >/dev/null
}

if [ ! -f "$REPO/etdrs_logger.py" ]; then
  alert "Could not find the ETDRS Logger files. If the etdrs-logger folder was moved or re-downloaded, open it and double-click \"Make ETDRS Logger App.command\" again."
  exit 1
fi

PY=""
for candidate in \
    /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
    /usr/local/bin/python3 \
    /opt/homebrew/bin/python3; do
  if [ -x "$candidate" ] && "$candidate" -c "import tkinter" >/dev/null 2>&1; then
    PY="$candidate"
    break
  fi
done
if [ -z "$PY" ]; then
  alert "Python 3 is not installed. Install it from python.org, then try again."
  exit 1
fi

mkdir -p "$(dirname "$LOG")"
cd "$REPO" || exit 1
if ! "$PY" etdrs_logger.py 2>"$LOG"; then
  alert "ETDRS Logger stopped with an error. Details are in Library/Logs/ETDRS Logger.log in your home folder."
  exit 1
fi
EOF
chmod +x "$LAUNCHER"
touch "$APP"  # so Finder picks up the new icon

echo
echo "Created: $APP"
echo
echo "A Finder window will now show the ETDRS Logger app."
echo "  - Drag it onto the Dock to keep it there."
echo "  - To put it on the Desktop, hold Option and Command while you drag it there."
echo
if [ "$(uname)" = "Darwin" ]; then
  open -R "$APP"
fi
read -r -p "Press Return to close this window."
