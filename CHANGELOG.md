# Changelog

## 0.6.0
- Neuer Service **`ebus_bridge.write`** (circuit · message · value) – generischer
  Durchreicher zu ebusds `write`, Mehrfeld-Werte mit `;`. Liest nach dem Schreiben
  frisch zurück und gibt den aktuellen Wert als Response zurück. Grundlage für
  späteres Kalender-Schreiben (sobald ebusd eine schreibbare Timer-Nachricht bietet).

## 0.5.0
- Umbenannt in **„eBUS Bridge"** – Anzeigename **und** Domain `ebus_bridge`
  (Abgrenzung zur HACS-Integration „eBus Direct"; herstellerneutral, Vaillant &
  weitere eBUS-Geräte).
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
