#!/usr/bin/env bash
# Launcher for Debian / Ubuntu / Linux Mint.
cd "$(dirname "$0")" || exit 1

if ! python3 -c "import gi; gi.require_version('Gtk','3.0'); from gi.repository import Gtk" 2>/dev/null; then
  echo "GTK 3 Python bindings missing - installing (needs sudo)..."
  sudo apt install -y python3-gi gir1.2-gtk-3.0 || exit 1
fi

exec python3 dictionary_app.py
