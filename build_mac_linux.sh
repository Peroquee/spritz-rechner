#!/bin/sh
# Baut das Programm SpritzRechner (mit eingebautem Python) fuer macOS oder Linux.
# Aufruf im Terminal:   sh build_mac_linux.sh
set -e
cd "$(dirname "$0")"

echo ""
echo " Baue SpritzRechner (mit eingebautem Python) ..."
echo ""

python3 -m venv .build-venv
. .build-venv/bin/activate

python -m pip install --upgrade pip pyinstaller reportlab
pyinstaller --noconfirm --clean --onefile --console --name SpritzRechner --collect-all reportlab spritz_rechner.py

mkdir -p fertig
cp dist/SpritzRechner rezepte.csv ANLEITUNG.txt fertig/
chmod +x fertig/SpritzRechner

echo ""
echo " FERTIG! Im Ordner 'fertig' liegen SpritzRechner, rezepte.csv und ANLEITUNG.txt."
echo " Diesen Ordner kannst du weitergeben."
echo ""
