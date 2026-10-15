# Spritz-Rechner als Paket mit eingebautem Python bauen

Ziel: Die Person, die das Programm benutzt, muss **nichts installieren**. Dafür wird
das Python-Script mit **PyInstaller** zusammen mit Python und der PDF-Bibliothek
(reportlab) in eine einzige Programmdatei verpackt.

**Wichtig:** PyInstaller kann nur für das System bauen, auf dem es gerade läuft.
Eine Windows-`.exe` muss also auf Windows gebaut werden, die Mac-Version auf einem
Mac. Wenn du nicht alle Systeme zur Hand hast, nimm Weg A.

---

## Weg A: Automatisch auf GitHub bauen lassen (alle Systeme, ohne eigene Rechner)

1. Kostenloses Konto auf <https://github.com> anlegen (falls noch keins da ist).
2. Ein neues Repository erstellen (z. B. `spritz-rechner`, privat ist ok).
3. **Alle Dateien aus diesem Ordner hochladen.** Dazu gehört auch der versteckte
   Ordner `.github/workflows/bauen.yml`.
   - Am einfachsten geht das mit Git (`git add . && git commit && git push`).
   - Beim Hochladen über die Webseite werden versteckte Ordner oft nicht
     mitgenommen. Dann die Datei auf GitHub selbst anlegen: „Add file → Create new
     file“, als Namen `.github/workflows/bauen.yml` eintippen und den Inhalt
     hineinkopieren.
4. Auf GitHub den Reiter **Actions** öffnen, links **„SpritzRechner bauen“** wählen
   und rechts **„Run workflow“** klicken.
5. Nach ca. 3–5 Minuten den fertigen Lauf anklicken. Unten unter **Artifacts** liegen
   drei Downloads:
   - `SpritzRechner-Windows`
   - `SpritzRechner-macOS` (für Macs mit Apple-Chip M1/M2/M3/…)
   - `SpritzRechner-Linux`
6. Jeder Download ist eine ZIP-Datei, in der eine weitere ZIP-Datei steckt.
   Beide entpacken. Der Ordner `SpritzRechner` darin ist fertig zum Weitergeben.

Für ältere Macs mit Intel-Prozessor auf so einem Mac **Weg B** verwenden.

---

## Weg B: Selbst auf dem jeweiligen Rechner bauen

Dafür braucht **nur der Rechner, auf dem gebaut wird**, einmalig Python
(<https://www.python.org/downloads/>). Unter Windows bei der Installation
„Add python.exe to PATH“ anhaken. Die Person, die das Programm später benutzt,
braucht kein Python.

- **Windows:** Doppelklick auf `build_windows.bat`.
- **Mac/Linux:** Terminal im Ordner öffnen und `sh build_mac_linux.sh` eingeben.
  Unter Debian/Ubuntu vorher einmal `sudo apt install python3-venv` ausführen.

Danach liegt alles im Ordner **`fertig`**:

- das Programm
- `rezepte.csv`
- `ANLEITUNG.txt`

Diesen Ordner weitergeben, zum Beispiel als ZIP oder auf einem USB-Stick.

---

## Weg C: Direkt mit Python starten (zum Testen)

```
python3 spritz_rechner.py
```

Ohne installiertes `reportlab` wird die Einkaufsliste als `.txt` statt als PDF
gespeichert. Mit `pip install reportlab` wird ein PDF erzeugt.

---

## Hinweise

- **Warnungen beim ersten Start:** Windows (SmartScreen) und macOS (Gatekeeper)
  warnen bei Programmen ohne kostenpflichtige Entwickler-Signatur. Wie man sie
  trotzdem startet, steht in `ANLEITUNG.txt`.
- **Virenscanner:** Mit PyInstaller gebaute `.exe`-Dateien werden von
  Virenscannern gelegentlich fälschlich gemeldet. Selbst gebaute Dateien (Weg A
  oder B) sind sauber.
- **Rezepte ändern:** Dafür muss nichts neu gebaut werden. Einfach `rezepte.csv`
  bearbeiten.
