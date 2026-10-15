#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spritz-Rechner
==============

Rechnet aus, wie viele Grundzutaten man fuer eine bestimmte Anzahl
verschiedener Spritz-Getraenke einkaufen muss.

* Die Drinks und ihre Zutaten stehen in einer CSV-Datei (Standard: rezepte.csv
  im selben Ordner wie das Programm). Eine andere CSV kann man per Drag & Drop
  auf das Programm ziehen oder als Parameter angeben.
* Das Programm fragt fuer jeden Drink nach, wie viele Portionen gemacht werden.
* Standardeinheiten (ml, cl, dl, l, mg, g, kg) werden zusammengezaehlt und auf
  sinnvolle Einheiten umgerechnet (z. B. 288 cl -> 2,88 l).
* Zutaten mit "Einkaufseinheit" werden auf ganze Einkaufseinheiten AUFGERUNDET
  (z. B. 20 Orangenscheiben bei 8 Scheiben pro Orange -> 3 Orangen).
* Das Ergebnis wird angezeigt und als PDF gespeichert (falls die PDF-Bibliothek
  "reportlab" fehlt, als TXT-Datei).

CSV-Spalten (Trennzeichen ; oder , - wird automatisch erkannt):
    Drink                       (Pflicht)  Name des Getraenks
    Zutat                       (Pflicht)  Name der Zutat
    Menge pro Portion           (Pflicht)  Zahl, Komma oder Punkt erlaubt
    Einheit                     (Pflicht)  z. B. cl, ml, g, Stueck
    Einkaufseinheit             (optional) z. B. Orange, Eiswuerfel-Tuete (2 kg)
    Anzahl pro Einkaufseinheit  (optional) z. B. 8 (Scheiben pro Orange)
    Farbe                       (optional) Farbe des Eingabefensters, z. B. #FFCC99
"""

import csv
import datetime
import io
import os
import re
import shutil
import subprocess
import sys
from decimal import Decimal, InvalidOperation, ROUND_CEILING

PROGRAMM_NAME = "Spritz-Rechner"
CSV_DATEINAME = "rezepte.csv"
MAX_PORTIONEN = 100000

# Wird nur benutzt, wenn neben dem Programm noch keine rezepte.csv liegt.
# Dann wird diese Datei automatisch angelegt, damit man sie bearbeiten kann.
STANDARD_REZEPTE = """\
Drink;Zutat;Menge pro Portion;Einheit;Einkaufseinheit;Anzahl pro Einkaufseinheit;Farbe
Aperol Spritz;Aperol;6;cl;;;#FFCC99
Aperol Spritz;Prosecco;9;cl;;;#FFCC99
Aperol Spritz;Orangenscheibe;1;Stück;Orange;8;#FFCC99
Aperol Spritz;Eiswürfel;2;Stück;Eiswürfel-Tüte (2 kg);66;#FFCC99
Limoncello Spritz;Limoncello;6;cl;;;#FFF2A8
Limoncello Spritz;Prosecco;9;cl;;;#FFF2A8
Limoncello Spritz;Zitronenscheibe;1;Stück;Zitrone;7;#FFF2A8
Limoncello Spritz;Eiswürfel;2;Stück;Eiswürfel-Tüte (2 kg);66;#FFF2A8
Lavendel Spritz;Lavendellikör / Lavendelsirup;6;cl;;;#DCCCF2
Lavendel Spritz;Prosecco;9;cl;;;#DCCCF2
Lavendel Spritz;Lavendelzweig;1;Stück;;;#DCCCF2
Lavendel Spritz;Eiswürfel;2;Stück;Eiswürfel-Tüte (2 kg);66;#DCCCF2
Sarti Spritz;Sarti Rosa;6;cl;;;#D9A0A4
Sarti Spritz;Prosecco;9;cl;;;#D9A0A4
Sarti Spritz;Blutorangenscheibe;1;Stück;Blutorange;7;#D9A0A4
Sarti Spritz;Eiswürfel;2;Stück;Eiswürfel-Tüte (2 kg);66;#D9A0A4
Rosmarin Grapefruit Spritz;Prosecco;15;cl;;;#FFC2B4
Rosmarin Grapefruit Spritz;Grapefruitscheibe;1;Stück;Grapefruit;8;#FFC2B4
Rosmarin Grapefruit Spritz;Rosmarinzweig;1;Stück;;;#FFC2B4
Rosmarin Grapefruit Spritz;Eiswürfel;2;Stück;Eiswürfel-Tüte (2 kg);66;#FFC2B4
Rosmarin Grapefruit Spritz;Rohrzucker;1;EL;;;#FFC2B4
"""

# Pastellfarben fuer Drinks, bei denen in der CSV keine Farbe steht.
ERSATZ_FARBEN = [
    (204, 228, 247), (208, 240, 208), (247, 214, 230),
    (230, 230, 200), (210, 235, 235), (235, 220, 205),
]

# Standardeinheiten: Name -> (Art, Faktor zur Basiseinheit ml bzw. g)
EINHEITEN = {
    "ml": ("volumen", Decimal("1")),
    "milliliter": ("volumen", Decimal("1")),
    "cl": ("volumen", Decimal("10")),
    "zentiliter": ("volumen", Decimal("10")),
    "dl": ("volumen", Decimal("100")),
    "deziliter": ("volumen", Decimal("100")),
    "l": ("volumen", Decimal("1000")),
    "liter": ("volumen", Decimal("1000")),
    "mg": ("masse", Decimal("0.001")),
    "milligramm": ("masse", Decimal("0.001")),
    "g": ("masse", Decimal("1")),
    "gr": ("masse", Decimal("1")),
    "gramm": ("masse", Decimal("1")),
    "kg": ("masse", Decimal("1000")),
    "kilogramm": ("masse", Decimal("1000")),
}


class CsvFehler(Exception):
    """Fehler in der Rezept-Datei. Enthaelt eine Liste verstaendlicher Meldungen."""

    def __init__(self, meldungen):
        super().__init__("\n".join(meldungen))
        self.meldungen = meldungen


class Zutat(object):
    def __init__(self, name, menge, einheit, einkaufseinheit, anzahl_pro_einkauf):
        self.name = name
        self.menge = menge
        self.einheit = einheit
        self.einkaufseinheit = einkaufseinheit
        self.anzahl_pro_einkauf = anzahl_pro_einkauf


class Drink(object):
    def __init__(self, name, farbe):
        self.name = name
        self.farbe = farbe
        self.zutaten = []


# ---------------------------------------------------------------------------
# Hilfsfunktionen: Pfade, Zahlen, Einheiten
# ---------------------------------------------------------------------------

def programm_ordner():
    """Ordner, in dem das Programm (oder die .exe) liegt."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def zahl_lesen(text):
    """Liest '6', '1,5' oder '1.5' als Decimal. Gibt None zurueck, wenn ungueltig."""
    text = (text or "").strip().replace(" ", "").replace(",", ".")
    if not re.match(r"^[0-9]+(\.[0-9]+)?$", text):
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def aufrunden(wert, schritt):
    """Rundet 'wert' auf ein Vielfaches von 'schritt' AUF."""
    return (wert / schritt).to_integral_value(rounding=ROUND_CEILING) * schritt


def zahl_formatieren(wert):
    """Decimal -> deutscher Text, z. B. 2.50 -> '2,5', 3.00 -> '3'."""
    text = "{:f}".format(wert)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


def einheit_finden(einheit):
    """Gibt (Art, Faktor) fuer Standardeinheiten zurueck, sonst (None, 1)."""
    schluessel = einheit.strip().lower().rstrip(".")
    if schluessel in EINHEITEN:
        return EINHEITEN[schluessel]
    return None, Decimal("1")


def menge_formatieren(basis_menge, art, einheit):
    """
    Formatiert eine Gesamtmenge sinnvoll. Es wird immer AUFgerundet, damit
    niemals zu wenig angezeigt wird.
      Volumen (Basis ml): ab 1 l in Liter, ab 1 cl in cl, sonst ml
      Masse   (Basis g) : ab 1 kg in kg, sonst g
      sonst             : Zahl + Einheit aus der CSV
    """
    if art == "volumen":
        if basis_menge >= 1000:
            return zahl_formatieren(aufrunden(basis_menge / 1000, Decimal("0.01"))) + " l"
        if basis_menge >= 10:
            return zahl_formatieren(aufrunden(basis_menge / 10, Decimal("0.1"))) + " cl"
        return zahl_formatieren(aufrunden(basis_menge, Decimal("1"))) + " ml"
    if art == "masse":
        if basis_menge >= 1000:
            return zahl_formatieren(aufrunden(basis_menge / 1000, Decimal("0.01"))) + " kg"
        return zahl_formatieren(aufrunden(basis_menge, Decimal("1"))) + " g"
    return zahl_formatieren(aufrunden(basis_menge, Decimal("0.01"))) + " " + einheit


def farbe_lesen(text):
    """'#FFCC99' oder 'FFCC99' -> (255, 204, 153). Ungueltig -> None."""
    text = (text or "").strip().lstrip("#")
    if not re.match(r"^[0-9a-fA-F]{6}$", text):
        return None
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


# ---------------------------------------------------------------------------
# CSV einlesen
# ---------------------------------------------------------------------------

def _spaltenname_normalisieren(name):
    name = (name or "").strip().lower()
    for alt, neu in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        name = name.replace(alt, neu)
    return re.sub(r"[^a-z0-9]", "", name)


def _spalte_erkennen(name):
    """Ordnet eine Spaltenueberschrift einer bekannten Spalte zu."""
    n = _spaltenname_normalisieren(name)
    if not n:
        return None
    if "anzahl" in n:
        return "anzahl"
    if "menge" in n:
        return "menge"
    if n.startswith("einkauf"):
        return "einkaufseinheit"
    if "einheit" in n:
        return "einheit"
    if "farb" in n or "color" in n or "colour" in n:
        return "farbe"
    if n.startswith("drink") or n.startswith("getraenk") or n.startswith("cocktail"):
        return "drink"
    if n.startswith("zutat") or n == "name":
        return "zutat"
    return None


def csv_laden(pfad):
    """Liest die Rezept-CSV und gibt eine Liste von Drink-Objekten zurueck."""
    try:
        with open(pfad, "rb") as datei:
            roh = datei.read()
    except OSError as fehler:
        raise CsvFehler(["Die Datei konnte nicht geöffnet werden: %s" % fehler])

    # Excel speichert je nach Einstellung als UTF-8 oder Windows-1252.
    try:
        text = roh.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = roh.decode("cp1252", errors="replace")

    erste_zeile = next((z for z in text.splitlines() if z.strip()), None)
    if erste_zeile is None:
        raise CsvFehler(["Die Datei ist leer."])
    trenner = max([";", ",", "\t"], key=erste_zeile.count)
    if erste_zeile.count(trenner) == 0:
        raise CsvFehler([
            "In der ersten Zeile wurden keine Spalten gefunden.",
            "Die Spalten müssen mit Semikolon (;) oder Komma (,) getrennt sein.",
        ])

    leser = csv.reader(io.StringIO(text), delimiter=trenner)
    fehler = []
    spalten = None
    drinks = []
    drinks_nach_name = {}

    for zeile in leser:
        nr = leser.line_num
        if not any(zelle.strip() for zelle in zeile):
            continue  # leere Zeile

        if spalten is None:
            # Kopfzeile auswerten
            spalten = {}
            for index, ueberschrift in enumerate(zeile):
                art = _spalte_erkennen(ueberschrift)
                if art is None:
                    continue
                if art in spalten:
                    fehler.append("Zeile %d: Die Spalte '%s' kommt doppelt vor." % (nr, ueberschrift.strip()))
                spalten[art] = index
            namen = {"drink": "Drink", "zutat": "Zutat", "menge": "Menge pro Portion", "einheit": "Einheit"}
            fehlend = [namen[s] for s in ("drink", "zutat", "menge", "einheit") if s not in spalten]
            if fehlend:
                fehler.append("In der ersten Zeile fehlen diese Spalten: " + ", ".join(fehlend))
                fehler.append("Erwartet werden mindestens: Drink; Zutat; Menge pro Portion; Einheit")
            if fehler:
                raise CsvFehler(fehler)
            continue

        def wert(art):
            index = spalten.get(art)
            if index is None or index >= len(zeile):
                return ""
            return zeile[index].strip()

        drink_name = wert("drink")
        if drink_name.startswith("#"):
            continue  # Kommentarzeile
        zutat_name = wert("zutat")
        menge_text = wert("menge")
        einheit = wert("einheit")
        einkauf = wert("einkaufseinheit")
        anzahl_text = wert("anzahl")
        farbe_text = wert("farbe")

        zeilen_fehler = []
        if not drink_name:
            zeilen_fehler.append("Zeile %d: Der Name des Drinks fehlt." % nr)
        if not zutat_name:
            zeilen_fehler.append("Zeile %d: Der Name der Zutat fehlt." % nr)
        menge = zahl_lesen(menge_text)
        if menge is None:
            zeilen_fehler.append("Zeile %d: Die Menge '%s' ist keine gültige Zahl (Beispiel: 6 oder 1,5)." % (nr, menge_text))
        if not einheit:
            zeilen_fehler.append("Zeile %d: Die Einheit fehlt (Beispiel: cl, g oder Stück)." % nr)

        anzahl = None
        if einkauf or anzahl_text:
            if not einkauf:
                zeilen_fehler.append("Zeile %d: 'Anzahl pro Einkaufseinheit' ist angegeben, aber die Einkaufseinheit fehlt." % nr)
            if not anzahl_text:
                zeilen_fehler.append("Zeile %d: Die Einkaufseinheit '%s' ist angegeben, aber 'Anzahl pro Einkaufseinheit' fehlt." % (nr, einkauf))
            else:
                anzahl = zahl_lesen(anzahl_text)
                if anzahl is None or anzahl <= 0:
                    zeilen_fehler.append("Zeile %d: 'Anzahl pro Einkaufseinheit' muss eine Zahl größer als 0 sein (steht dort: '%s')." % (nr, anzahl_text))

        farbe = None
        if farbe_text:
            farbe = farbe_lesen(farbe_text)
            if farbe is None:
                zeilen_fehler.append("Zeile %d: Die Farbe '%s' ist ungültig. Format: #RRGGBB, z. B. #FFCC99." % (nr, farbe_text))

        if zeilen_fehler:
            fehler.extend(zeilen_fehler)
            continue

        schluessel = drink_name.casefold()
        drink = drinks_nach_name.get(schluessel)
        if drink is None:
            drink = Drink(drink_name, farbe)
            drinks_nach_name[schluessel] = drink
            drinks.append(drink)
        elif drink.farbe is None and farbe is not None:
            drink.farbe = farbe
        drink.zutaten.append(Zutat(zutat_name, menge, einheit, einkauf or None, anzahl))

    if spalten is None:
        fehler.append("Die Datei enthält keine Kopfzeile.")
    elif not drinks and not fehler:
        fehler.append("In der Datei steht kein einziger Drink.")
    if fehler:
        raise CsvFehler(fehler)

    for index, drink in enumerate([d for d in drinks if d.farbe is None]):
        drink.farbe = ERSATZ_FARBEN[index % len(ERSATZ_FARBEN)]
    return drinks


# ---------------------------------------------------------------------------
# Berechnung
# ---------------------------------------------------------------------------

def berechnen(drinks, portionen):
    """
    portionen: Liste mit der Anzahl je Drink (gleiche Reihenfolge wie drinks).
    Gibt (einkaufsliste, aufteilung) zurueck.
      einkaufsliste: Liste von (Einkaufen, Menge, Hinweis)
      aufteilung:    Liste von (Drink, Anzahl, [(Zutat, Menge), ...])
    """
    posten = {}
    reihenfolge = []
    aufteilung = []

    for drink, anzahl in zip(drinks, portionen):
        if anzahl <= 0:
            continue
        zeilen = []
        for z in drink.zutaten:
            art, faktor = einheit_finden(z.einheit)
            gesamt = z.menge * faktor * anzahl  # in ml, g oder Einheit aus der CSV
            zeilen.append((z.name, menge_formatieren(gesamt, art, z.einheit)))

            if z.einkaufseinheit:
                anzahl_basis = z.anzahl_pro_einkauf * faktor
                einkauf_schluessel = (z.einkaufseinheit.casefold(), anzahl_basis)
            else:
                anzahl_basis = None
                einkauf_schluessel = None
            schluessel = (z.name.casefold(), art or z.einheit.strip().casefold(), einkauf_schluessel)
            if schluessel not in posten:
                posten[schluessel] = {
                    "name": z.name, "art": art, "einheit": z.einheit,
                    "einkauf": z.einkaufseinheit, "anzahl_basis": anzahl_basis,
                    "anzahl_text": ("%s %s" % (zahl_formatieren(z.anzahl_pro_einkauf), z.einheit)
                                    if z.einkaufseinheit else ""),
                    "gesamt": Decimal("0"),
                }
                reihenfolge.append(schluessel)
            posten[schluessel]["gesamt"] += gesamt
        aufteilung.append((drink, anzahl, zeilen))

    # Sortierung: Fluessigkeiten, dann Gewichte, dann Einkaufseinheiten, dann Rest.
    def gruppe(schluessel):
        p = posten[schluessel]
        if p["einkauf"]:
            return 2
        if p["art"] == "volumen":
            return 0
        if p["art"] == "masse":
            return 1
        return 3

    liste = []
    for schluessel in sorted(reihenfolge, key=lambda s: (gruppe(s), reihenfolge.index(s))):
        p = posten[schluessel]
        if p["gesamt"] <= 0:
            continue
        bedarf = menge_formatieren(p["gesamt"], p["art"], p["einheit"])
        if p["einkauf"]:
            stueck = int((p["gesamt"] / p["anzahl_basis"]).to_integral_value(rounding=ROUND_CEILING))
            # z. B. "Zitronenscheibe: 5 Stück, bei 7 Stück pro Zitrone"
            hinweis = "%s: %s, bei %s pro %s" % (p["name"], bedarf, p["anzahl_text"], p["einkauf"])
            liste.append((p["einkauf"], "%d Stück" % stueck, hinweis))
        else:
            liste.append((p["name"], bedarf, ""))
    return liste, aufteilung


# ---------------------------------------------------------------------------
# Bildschirm und Farben
# ---------------------------------------------------------------------------

class Bildschirm(object):
    def __init__(self):
        self.farbe_an = False
        self.truecolor = True
        try:
            # Umlaute auch in alten Konsolen anzeigen
            sys.stdout.reconfigure(errors="replace")
        except Exception:
            pass
        if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
            return
        if os.name == "nt":
            self.farbe_an = self._windows_farben_einschalten()
        else:
            self.farbe_an = os.environ.get("TERM", "") != "dumb"
        # Das Terminal von macOS kann nicht immer 16 Mio. Farben -> 256 Farben nutzen
        if os.environ.get("TERM_PROGRAM") == "Apple_Terminal" and \
                os.environ.get("COLORTERM", "").lower() not in ("truecolor", "24bit"):
            self.truecolor = False

    @staticmethod
    def _windows_farben_einschalten():
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            modus = ctypes.c_uint32()
            if not kernel32.GetConsoleMode(handle, ctypes.byref(modus)):
                return False
            return kernel32.SetConsoleMode(handle, modus.value | 0x0004) != 0
        except Exception:
            return False

    @staticmethod
    def _rgb_zu_256(r, g, b):
        def stufe(v):
            return 0 if v < 48 else (1 if v < 115 else (v - 35) // 40)
        werte = [0, 95, 135, 175, 215, 255]
        ri, gi, bi = stufe(r), stufe(g), stufe(b)
        wuerfel = (16 + 36 * ri + 6 * gi + bi, (werte[ri], werte[gi], werte[bi]))
        grau_index = min(23, max(0, (((r + g + b) // 3) - 3) // 10))
        grau_wert = 8 + 10 * grau_index
        grau = (232 + grau_index, (grau_wert, grau_wert, grau_wert))

        def abstand(farbe):
            return sum((a - b) ** 2 for a, b in zip(farbe, (r, g, b)))
        return min(wuerfel, grau, key=lambda k: abstand(k[1]))[0]

    def _farbcode(self, hintergrund, vordergrund=(45, 35, 40)):
        if self.truecolor:
            return "\033[48;2;%d;%d;%dm\033[38;2;%d;%d;%dm" % (hintergrund + vordergrund)
        return "\033[48;5;%dm\033[38;5;%dm" % (self._rgb_zu_256(*hintergrund), self._rgb_zu_256(*vordergrund))

    def leeren(self, farbe=None):
        """Bildschirm leeren, auf Wunsch komplett in einer Farbe."""
        if self.farbe_an:
            code = "\033[0m" + (self._farbcode(farbe) if farbe else "")
            sys.stdout.write(code + "\033[2J\033[3J\033[H")
            sys.stdout.flush()
        else:
            print("\n" + "=" * 70 + "\n")

    def zuruecksetzen(self):
        if self.farbe_an:
            sys.stdout.write("\033[0m")
            sys.stdout.flush()

    def zeile(self, text=""):
        """Gibt eine Zeile aus. \033[K faerbt den Rest der Zeile mit."""
        if self.farbe_an:
            print(text + "\033[K")
        else:
            print(text)

    def farbfeld(self, farbe, text):
        """Kurzer farbig hinterlegter Text (fuer die Zusammenfassung)."""
        if self.farbe_an:
            return self._farbcode(farbe) + text + "\033[0m"
        return text

    def eingabe(self, text):
        try:
            return input(text)
        except EOFError:
            raise KeyboardInterrupt


def ja_nein(bild, frage):
    while True:
        antwort = bild.eingabe(frage).strip().lower()
        if antwort in ("j", "ja", "y", "yes"):
            return True
        if antwort in ("n", "nein", "no"):
            return False
        bild.zeile("   Bitte nur  j  (für Ja)  oder  n  (für Nein)  eintippen und Enter drücken.")


def portionen_abfragen(bild, drinks):
    anzahlen = []
    gesamt = len(drinks)
    for nummer, drink in enumerate(drinks, start=1):
        bild.leeren(drink.farbe)
        bild.zeile()
        bild.zeile("   Drink %d von %d" % (nummer, gesamt))
        bild.zeile()
        bild.zeile("   " + drink.name.upper())
        bild.zeile("   " + "-" * len(drink.name))
        bild.zeile()
        bild.zeile("   Wie viele %s sollen gemacht werden?" % drink.name)
        bild.zeile()
        bild.zeile("   So geht's:")
        bild.zeile("     - Tippe eine ganze Zahl ein, zum Beispiel  12")
        bild.zeile("     - Drücke danach die Enter-Taste (die große Taste rechts, oft mit Pfeil)")
        bild.zeile("     - Keine %s? Dann einfach nur Enter drücken (zählt als 0)." % drink.name)
        bild.zeile()
        while True:
            text = bild.eingabe("   Anzahl %s: " % drink.name).strip().replace(" ", "")
            if text == "":
                anzahl = 0
                break
            if re.match(r"^[0-9]+$", text):
                anzahl = int(text)
                if anzahl <= MAX_PORTIONEN:
                    break
                bild.zeile("   Das sind sehr viele. Bitte eine Zahl bis %d eintippen." % MAX_PORTIONEN)
                continue
            bild.zeile()
            bild.zeile("   '%s' ist leider keine gültige Eingabe." % text)
            bild.zeile("   Bitte NUR eine ganze Zahl eintippen, z. B. 0, 5 oder 20")
            bild.zeile("   (ohne Buchstaben, ohne Komma, ohne Minus) und Enter drücken.")
            bild.zeile()
        anzahlen.append(anzahl)
    bild.zuruecksetzen()
    return anzahlen


def tabelle_als_text(liste):
    kopf = ("Einkaufen", "Menge", "Hinweis")
    breiten = [max(len(kopf[i]), *(len(z[i]) for z in liste)) for i in range(3)]
    zeilen = ["   " + "  ".join(kopf[i].ljust(breiten[i]) for i in range(3)).rstrip(),
              "   " + "  ".join("-" * breiten[i] for i in range(3))]
    for z in liste:
        zeilen.append("   " + "  ".join(z[i].ljust(breiten[i]) for i in range(3)).rstrip())
    return zeilen


# ---------------------------------------------------------------------------
# Speichern (PDF, sonst TXT)
# ---------------------------------------------------------------------------

def speicherort_finden(dateiname):
    """Programmordner, sonst Desktop, sonst Benutzerordner - je nachdem, wo man schreiben darf."""
    home = os.path.expanduser("~")
    for ordner in (programm_ordner(), os.path.join(home, "Desktop"),
                   os.path.join(home, "Schreibtisch"), home):
        if os.path.isdir(ordner) and os.access(ordner, os.W_OK):
            basis, endung = os.path.splitext(dateiname)
            pfad = os.path.join(ordner, dateiname)
            zaehler = 2
            while os.path.exists(pfad):
                pfad = os.path.join(ordner, "%s_%d%s" % (basis, zaehler, endung))
                zaehler += 1
            return pfad
    raise OSError("Kein Ordner gefunden, in dem gespeichert werden darf.")


def txt_speichern(pfad, zeitpunkt, csv_name, drinks, portionen, liste, aufteilung):
    zeilen = ["EINKAUFSLISTE SPRITZ", "Erstellt am %s" % zeitpunkt.strftime("%d.%m.%Y um %H:%M Uhr"),
              "Rezeptdatei: %s" % csv_name, "", "BESTELLTE DRINKS"]
    for drink, anzahl in zip(drinks, portionen):
        zeilen.append("   %-30s %d" % (drink.name, anzahl))
    zeilen += ["", "EINKAUFSLISTE"] + tabelle_als_text(liste) + ["", "AUFTEILUNG NACH DRINK"]
    for drink, anzahl, posten in aufteilung:
        zeilen.append("")
        zeilen.append("   %s (%d Stück)" % (drink.name, anzahl))
        for name, menge in posten:
            zeilen.append("      %-34s %s" % (name, menge))
    zeilen += ["", "Fruchtscheiben und Eis sind auf ganze Früchte bzw. Tüten aufgerundet."]
    with open(pfad, "w", encoding="utf-8-sig", newline="") as datei:
        datei.write("\r\n".join(zeilen) + "\r\n")


def pdf_speichern(pfad, zeitpunkt, csv_name, drinks, portionen, liste, aufteilung):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (Flowable, KeepTogether, Paragraph,
                                    SimpleDocTemplate, Spacer, Table, TableStyle)
    from xml.sax.saxutils import escape

    def farbe(rgb):
        return colors.Color(rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0)

    dunkel = colors.Color(0.18, 0.14, 0.16)
    grau = colors.Color(0.45, 0.42, 0.44)
    linie = colors.Color(0.82, 0.80, 0.81)
    kopf_hg = colors.Color(0.95, 0.94, 0.94)

    titel = ParagraphStyle("titel", fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=dunkel)
    unter = ParagraphStyle("unter", fontName="Helvetica", fontSize=9.5, leading=13, textColor=grau)
    abschnitt = ParagraphStyle("abschnitt", fontName="Helvetica-Bold", fontSize=13, leading=16,
                               textColor=dunkel, spaceBefore=12, spaceAfter=6)
    normal = ParagraphStyle("normal", fontName="Helvetica", fontSize=10.5, leading=13, textColor=dunkel)
    fett = ParagraphStyle("fett", parent=normal, fontName="Helvetica-Bold")
    klein = ParagraphStyle("klein", parent=normal, fontSize=9, leading=11, textColor=grau)
    rechts = ParagraphStyle("rechts", parent=fett, alignment=2)

    def p(text, stil=normal):
        return Paragraph(escape(text), stil)

    class Kaestchen(Flowable):
        def __init__(self, groesse=4 * mm):
            Flowable.__init__(self)
            self.groesse = groesse
            self.width = self.height = groesse

        def draw(self):
            self.canv.setStrokeColor(grau)
            self.canv.setLineWidth(0.8)
            self.canv.rect(0, 0, self.groesse, self.groesse)

    breite = A4[0] - 36 * mm
    inhalt = [
        p("Einkaufsliste Spritz", titel),
        Spacer(1, 2 * mm),
        p("Erstellt am %s  ·  Rezeptdatei: %s"
          % (zeitpunkt.strftime("%d.%m.%Y um %H:%M Uhr"), csv_name), unter),
        p("Bestellte Drinks", abschnitt),
    ]

    # Tabelle: bestellte Drinks, farbig hinterlegt
    daten = [[p(d.name, fett), p(str(a), rechts)] for d, a in zip(drinks, portionen)]
    daten.append([p("Drinks insgesamt", fett), p(str(sum(portionen)), rechts)])
    stil = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("LINEABOVE", (0, -1), (-1, -1), 1, dunkel)]
    for i, d in enumerate(drinks):
        stil.append(("BACKGROUND", (0, i), (-1, i), farbe(d.farbe)))
        stil.append(("LINEBELOW", (0, i), (-1, i), 1.5, colors.white))
    t = Table(daten, colWidths=[breite * 0.75, breite * 0.25])
    t.setStyle(TableStyle(stil))
    inhalt.append(t)

    # Tabelle: Einkaufsliste mit Abhak-Kaestchen
    inhalt.append(p("Einkaufsliste", abschnitt))
    daten = [["", p("Einkaufen", fett), p("Menge", fett), p("Hinweis", fett)]]
    for name, menge, hinweis in liste:
        daten.append([Kaestchen(), p(name), p(menge, fett), p(hinweis, klein)])
    t = Table(daten, colWidths=[10 * mm, breite * 0.38, breite * 0.2, breite * 0.42 - 10 * mm],
              repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), kopf_hg),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, linie),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    inhalt.append(t)
    inhalt.append(Spacer(1, 2 * mm))
    inhalt.append(p("Fruchtscheiben und Eis sind großzügig auf ganze Früchte bzw. ganze Tüten aufgerundet.", klein))

    # Aufteilung nach Drink
    for nummer, (drink, anzahl, posten) in enumerate(aufteilung):
        daten = [[p("%s  –  %d Stück" % (drink.name, anzahl), fett), ""]]
        daten += [[p(name), p(menge)] for name, menge in posten]
        t = Table(daten, colWidths=[breite * 0.62, breite * 0.38])
        t.setStyle(TableStyle([
            ("SPAN", (0, 0), (-1, 0)),
            ("BACKGROUND", (0, 0), (-1, 0), farbe(drink.farbe)),
            ("LINEBELOW", (0, 1), (-1, -1), 0.5, linie),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        block = [t, Spacer(1, 4 * mm)]
        if nummer == 0:
            # Ueberschrift nie allein am Seitenende stehen lassen
            block.insert(0, p("Aufteilung nach Drink", abschnitt))
        inhalt.append(KeepTogether(block))

    def seitenfuss(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(grau)
        canvas.drawCentredString(A4[0] / 2.0, 10 * mm, "Seite %d" % doc.page)
        canvas.restoreState()

    dokument = SimpleDocTemplate(pfad, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                                 topMargin=16 * mm, bottomMargin=18 * mm,
                                 title="Einkaufsliste Spritz", author=PROGRAMM_NAME)
    dokument.build(inhalt, onFirstPage=seitenfuss, onLaterPages=seitenfuss)


def datei_oeffnen(pfad):
    """Oeffnet die gespeicherte Datei mit dem Standardprogramm. Fehler sind egal."""
    try:
        if os.name == "nt":
            os.startfile(pfad)
            return
        befehl = ["open", pfad] if sys.platform == "darwin" else ["xdg-open", pfad]
        if shutil.which(befehl[0]) is None:
            return
        umgebung = dict(os.environ)
        # PyInstaller verbiegt unter Linux die Bibliothekspfade - fuer fremde Programme zuruecksetzen
        if "LD_LIBRARY_PATH_ORIG" in umgebung:
            umgebung["LD_LIBRARY_PATH"] = umgebung["LD_LIBRARY_PATH_ORIG"]
        else:
            umgebung.pop("LD_LIBRARY_PATH", None)
        subprocess.Popen(befehl, env=umgebung, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def ergebnis_speichern(bild, csv_name, drinks, portionen, liste, aufteilung):
    zeitpunkt = datetime.datetime.now()
    basis = "Einkaufsliste_Spritz_%s" % zeitpunkt.strftime("%Y-%m-%d_%H-%M")
    try:
        import reportlab  # noqa: F401
        pdf_moeglich = True
    except ImportError:
        pdf_moeglich = False

    if pdf_moeglich:
        try:
            pfad = speicherort_finden(basis + ".pdf")
            pdf_speichern(pfad, zeitpunkt, csv_name, drinks, portionen, liste, aufteilung)
            return pfad
        except Exception as fehler:
            bild.zeile("   (PDF konnte nicht erstellt werden: %s - speichere stattdessen als Text.)" % fehler)
    pfad = speicherort_finden(basis + ".txt")
    txt_speichern(pfad, zeitpunkt, csv_name, drinks, portionen, liste, aufteilung)
    return pfad


# ---------------------------------------------------------------------------
# Programmablauf
# ---------------------------------------------------------------------------

def csv_pfad_bestimmen(bild):
    if len(sys.argv) > 1:
        return os.path.abspath(sys.argv[1])
    pfad = os.path.join(programm_ordner(), CSV_DATEINAME)
    if not os.path.exists(pfad):
        with open(pfad, "w", encoding="utf-8-sig", newline="") as datei:
            datei.write(STANDARD_REZEPTE.replace("\n", "\r\n"))
        bild.zeile("   Hinweis: Es gab noch keine Rezeptdatei. Sie wurde neu angelegt:")
        bild.zeile("   " + pfad)
        bild.zeile()
    return pfad


def eine_runde(bild, drinks, csv_name):
    while True:
        portionen = portionen_abfragen(bild, drinks)
        bild.leeren()
        bild.zeile()
        bild.zeile("   ZUSAMMENFASSUNG - bitte prüfen")
        bild.zeile("   ------------------------------")
        bild.zeile()
        breite = max(len(d.name) for d in drinks)
        for drink, anzahl in zip(drinks, portionen):
            bild.zeile("   " + bild.farbfeld(drink.farbe, "  " + drink.name.ljust(breite) + "  ")
                       + "   %d Stück" % anzahl)
        bild.zeile()
        if sum(portionen) == 0:
            bild.zeile("   Es wurde bei allen Drinks 0 eingegeben - da gibt es nichts zu rechnen.")
            bild.eingabe("   Drücke Enter, um die Zahlen neu einzugeben. ")
            continue
        if ja_nein(bild, "   Stimmt das so?  Tippe  j  für Ja  oder  n  für Nein  und drücke Enter: "):
            break

    liste, aufteilung = berechnen(drinks, portionen)
    bild.leeren()
    bild.zeile()
    bild.zeile("   EINKAUFSLISTE")
    bild.zeile()
    for text in tabelle_als_text(liste):
        bild.zeile(text)
    bild.zeile()
    bild.zeile("   Fruchtscheiben und Eis sind auf ganze Früchte bzw. Tüten aufgerundet.")
    bild.zeile()
    pfad = ergebnis_speichern(bild, csv_name, drinks, portionen, liste, aufteilung)
    bild.zeile("   Die Einkaufsliste wurde gespeichert unter:")
    bild.zeile("   " + pfad)
    bild.zeile("   (Sie wird jetzt automatisch geöffnet. Dort steht auch, wie viel in jeden Drink kommt.)")
    datei_oeffnen(pfad)
    bild.zeile()


def hauptprogramm():
    bild = Bildschirm()
    bild.leeren()
    bild.zeile()
    bild.zeile("   " + PROGRAMM_NAME.upper())
    bild.zeile("   Rechnet aus, was du für deine Spritz-Getränke einkaufen musst.")
    bild.zeile()
    csv_pfad = csv_pfad_bestimmen(bild)
    try:
        drinks = csv_laden(csv_pfad)
    except CsvFehler as fehler:
        bild.zeile("   In der Rezeptdatei stimmt etwas nicht:")
        bild.zeile("   " + csv_pfad)
        bild.zeile()
        for meldung in fehler.meldungen:
            bild.zeile("   - " + meldung)
        bild.zeile()
        bild.zeile("   Bitte die Datei korrigieren und das Programm danach neu starten.")
        bild.eingabe("   Drücke Enter, um das Programm zu schließen. ")
        return 1

    bild.zeile("   Rezepte gelesen aus: " + csv_pfad)
    bild.zeile("   Gefundene Drinks: " + ", ".join(d.name for d in drinks))
    bild.zeile()
    bild.zeile("   Gleich wird für jeden Drink einzeln gefragt, wie viele du machen möchtest.")
    bild.eingabe("   Drücke Enter, um zu starten. ")

    while True:
        eine_runde(bild, drinks, os.path.basename(csv_pfad))
        if not ja_nein(bild, "   Noch eine Berechnung machen?  j = Ja,  n = Nein (Programm beenden): "):
            break
    return 0


def main():
    try:
        code = hauptprogramm()
    except KeyboardInterrupt:
        sys.stdout.write("\033[0m\n" if sys.stdout.isatty() else "\n")
        print("   Programm abgebrochen.")
        code = 1
    except Exception as fehler:
        if sys.stdout.isatty():
            sys.stdout.write("\033[0m")
        print()
        print("   Es ist ein unerwarteter Fehler aufgetreten:")
        print("   %s: %s" % (type(fehler).__name__, fehler))
        try:
            input("   Drücke Enter, um das Programm zu schließen. ")
        except Exception:
            pass
        code = 1
    sys.exit(code)


if __name__ == "__main__":
    main()
