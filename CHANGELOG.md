# Changelog

## 1.0.0
- Config-Flow belegt den Host automatisch mit der HA-IP vor (überschreibbar für Remote-ebusd).
- Erste öffentliche Version (HACS).

## 0.10.0
- Eigenes Brand-Icon (`brand/`-Ordner), ab HA 2026.3 lokal mit Vorrang vor der brands-CDN.

## 0.9.0
- Fix: °C-Sollwerte nicht mehr auf 0–100 geklemmt (Spanne −60…150, negative Werte möglich).
- Bridge-Gerät heißt nur „eBUS Bridge"; Host als eigener Text-Sensor (Diagnose).
- Tests für `model.py` + CI (hassfest, HACS, ruff, pytest); `codeowners` gesetzt.

## 0.8.0
- Bridge-Diagnose aus ebusds globalem Abschnitt (Signal, Symbolrate, Reconnects, Master, QQ, Version).
- Enhanced-Timing (Arbitrierung/Latenz) als Diagnose, standardmäßig deaktiviert.

## 0.7.3
- Icon-Heuristik einheiten-first: Temperaturen immer als Thermometer-Variante.

## 0.7.2
- Passende mdi-Icons für alle Entitäten statt generischer Regler-Symbole.

## 0.7.1
- Klarnamen je Kreis (kein „ebusd"-Präfix); Bridge-Elterngerät, Kreise als Kinder (`via_device`).

## 0.7.0
- Kalender schreibbar (Anlegen/Ändern/Löschen), sobald ebusd eine Timer-Write-Nachricht bietet.

## 0.6.0
- Neuer Service `ebus_bridge.write` (generischer Durchreicher zu ebusds `write`, mit Read-back).

## 0.5.0
- Umbenannt in „eBUS Bridge" (Domain `ebus_bridge`); neue Plattform switch; `issue_tracker`.

## 0.4.1
- Fix: erzwungener Read nach dem Schreiben, damit Sollwerte nicht „nicht verfügbar" werden.

## 0.4.0
- Neue Plattformen binary_sensor + calendar (read-only); Options-Flow (Poll-Intervall, Ausschluss).

## 0.3.0
- Umbau auf ebusd HTTP-JSON (lesen) + TCP (schreiben); feld-basiertes Entity-Modell; Geräte-Metadaten.
