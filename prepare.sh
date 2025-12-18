#!/usr/bin/env bash

# ─────────────────────────────────────────────
# This script MUST be sourced, not executed.
# Usage:
#   source prepare.sh
# ─────────────────────────────────────────────

# Detect incorrect execution
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    echo "ERROR: This script must be sourced:"
    echo "  source prepare.sh"
    echo
    echo "Reason: activating a Python venv cannot persist from a subshell."
    exit 1
fi

set -euo pipefail

TARGET="bleachbit"
SOURCE="srcqt"

echo "Preparing BleachBit Qt environment..."

# 1) Clone repo if not already present
if [[ ! -d "$TARGET/.git" ]]; then
    git clone https://github.com/bleachbit/bleachbit.git --single-branch "$TARGET"
else
    echo "✔ Repo already exists"
fi

# 2) Copy directories
mkdir -p "$TARGET/icons" "$TARGET/share"
cp -a "$SOURCE/icons/." "$TARGET/icons/"
cp -a "$SOURCE/share/." "$TARGET/share/"

# 3) Copy modified / Qt files
cp -f "$SOURCE/bleachbit_qt.py" "$TARGET/"
cp -f "$SOURCE/__init__.py" "$TARGET/bleachbit/"
cp -f "$SOURCE/Cleaner.py" "$TARGET/bleachbit/"
cp -f "$SOURCE/Language.py" "$TARGET/bleachbit/"
cp -f "$SOURCE/QtGUI.py" "$TARGET/bleachbit/"
cp -f "$SOURCE/QtGuiCookie.py" "$TARGET/bleachbit/"
cp -f "$SOURCE/QtGuiPreferences.py" "$TARGET/bleachbit/"
cp -f "$SOURCE/QtSystemInformation.py" "$TARGET/bleachbit/"
cp -f "$SOURCE/Winapp.py" "$TARGET/bleachbit/"
cp -f "$SOURCE/Windows.py" "$TARGET/bleachbit/"

# 4) Create venv if missing
if [[ ! -d "$TARGET/venv" ]]; then
    python3 -m venv "$TARGET/venv"
    echo "✔ Virtual environment created"
else
    echo "✔ Virtual environment already exists"
fi

# 5) Activate venv (we need to source to make it persist the shell session)
# shellcheck disable=SC1091
source "$TARGET/venv/bin/activate"

echo "✔ Virtual environment activated:"
echo "  $VIRTUAL_ENV"

# 6) Install requirements
pip install --upgrade pip
pip install -r requirements_nix.txt

cd bleachbit

echo
echo "✅ Environment ready."
echo "Run:"
echo "  python bleachbit_qt.py"
