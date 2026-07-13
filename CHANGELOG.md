# Changelog

## 0.5.0
- Neue Plattform **switch** für schreibbare reine An/Aus-Felder (aus `select` ausgegliedert).
- `issue_tracker` in der manifest ergänzt.

## 0.4.1
- Fix: nach jedem Schreiben (number/select) erzwungener `read -f`, damit nicht
  gepollte Sollwerte nicht auf „nicht verfügbar" fallen.

## 0.4.0
- Neue Plattform **binary_sensor** für nicht schreibbare An/Aus-Felder.
- Neue Plattform **calendar**: Vaillant-Wochen-Zeitprogramme als read-only-Kalender
  (je Wochenprogramm einer, Fenster + Soll-Temperatur).
- **Options-Flow**: Poll-Intervall und Ausschluss-Filter (Default `Timer`).

## 0.3.0
- Umbau auf ebusd **HTTP-JSON** (Port 8889) für Lesen/Definitionen, **TCP** (8888)
  fürs Schreiben; feld-basiertes Entity-Modell mit fixem Entity-Satz.
- Geräte-Metadaten (Hersteller/Modell/SW/HW) aus den Scan-Definitionen.
