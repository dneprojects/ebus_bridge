# eBUS Bridge (Home Assistant)

**Lokale eBUS-Heizungs-Integration für Home Assistant – ohne Cloud, ohne MQTT.**
Ideal für **Vaillant** (Wärmepumpe/Heizung/sensoCOMFORT) und weitere eBUS-Hersteller
(Wolf, Kromschröder/Elster, Brötje, Ferroli …).

Native HA-Integration, die **direkt an ebusd** andockt und daraus automatisch
Geräte + Entities baut – **ohne MQTT**. ebusd erledigt (mit den CSV-Definitionen)
die eigentliche eBUS-Dekodierung; diese Integration ist die HA-Schicht darüber.

- **Lesen + Definitionen:** ebusd **HTTP-JSON** (Port 8889) → exakte Einheiten,
  Enum-Optionen, Feld-Struktur.
- **Schreiben:** ebusd **TCP-Kommandoport** (Port 8888).

## Entitäten (v0.5)
- **sensor** – je (nicht schreibbarem) Feld eine Entity (Mehrfeld-Splitting, z. B.
  `Status01` → Vorlauf/Rücklauf/… getrennt), Einheit/Geräteklasse aus den Defs.
- **binary_sensor** – nicht schreibbare reine An/Aus-Felder (z. B. Pumpenstatus).
- **number** – schreibbare numerische Sollwerte (min/max/step aus dem Datentyp;
  °C-Sollwerte 0–100/0,5).
- **select** – schreibbare Enum-Felder (Betriebsarten) mit echten Optionen.
- **switch** – schreibbare reine An/Aus-Felder.
- **calendar** – Vaillant-Wochen-Zeitprogramme (`<Prefix>Timer_<Tag><Slot>`), je
  Wochenprogramm (Z1/Z2/Z3/Hwc/Cc …) ein Kalender. Fenster = `htm`–`htm_1`,
  Titel = Soll-Temperatur. **Bearbeitbar** (Anlegen/Ändern/Löschen), **sobald ebusd
  eine schreibbare Tages-Nachricht `<Prefix>Timer_<Tag>` anbietet** – sonst
  read-only. Soll-Temp im Termin-Titel; Änderungen gelten fürs ganze Wochen-Fenster.

Nach jedem Schreiben (number/select/switch) liest die Integration den Wert frisch
zurück (`read -f`), damit nicht gepollte Sollwerte nicht „nicht verfügbar" werden.

## Service
- **`ebus_bridge.write`** (`circuit`, `message`, `value`) – generischer
  Durchreicher zu ebusds `write`. Mehrfeld-Werte mit `;` trennen
  (z. B. `0;3;06:00;22:00;20.0`). Liest nach dem Schreiben frisch zurück und gibt
  den aktuellen Wert als Response zurück. Damit lässt sich **jede** schreibbare
  ebusd-Nachricht setzen – auch Timer, sobald ebusd eine Schreib-Nachricht dafür
  anbietet.

## Optionen
Integration → **Konfigurieren**:
- **Poll-Intervall** (Sekunden).
- **Ausschluss** – kommagetrennte Namensteile (Default `Timer`, damit die vielen
  Zeitprogramm-Felder nicht als Sensoren erscheinen – der Kalender nutzt sie weiter).

## Voraussetzung
Im ebusd-Add-on **beide Ports freigeben** (Configuration → **Network**):
- `8888/tcp` → `8888` (Schreiben)
- `8889/tcp` → `8889` (HTTP-JSON) — dazu **`--httpport=8889`** in `commandline_options`.

Test:
```
telnet <HA-IP> 8888          # -> info
http://<HA-IP>:8889/data     # -> JSON im Browser
```

## Installation
1. Ordner `custom_components/ebus_bridge/` nach `…/config/custom_components/` kopieren.
2. HA neu starten.
3. **Einstellungen → Geräte & Dienste → Integration hinzufügen → „eBUS Bridge"**.
4. Host = HA-IP, TCP-Port `8888`, HTTP-Port `8889`.

## Grenzen
- **number-Grenzen** werden aus dem ebusd-Datentyp abgeleitet (min/max liefert die
  JSON nicht explizit); Box-Modus = tolerante Eingabe.
- Aktualisierung alle 30 s (ein `/data`-Roundtrip pro Zyklus).
- Der Entity-Satz ist **fix** (aus den Definitionen) → keine Registry-Leichen mehr.

## Architektur
- `model.py` – JSON→Feld-Deskriptoren (parse_definitions/parse_values/parse_device_meta).
- `client.py` – HTTP-JSON (lesen/def) + TCP (schreiben + `read -f` nach write).
- `coordinator.py` – Definitionen einmalig, Werte zyklisch; Ausschluss-Filter.
- `entity.py` / `sensor.py` / `binary_sensor.py` / `number.py` / `select.py` /
  `switch.py` / `calendar.py` – die Plattformen.
- `config_flow.py` – Host + beide Ports (testet beide) + Options-Flow.
