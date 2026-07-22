# Zusatz-Register für Regler-Entscheidungen (feldverifiziert)

Diese Zeilen machen Entscheidungen des sensoCOMFORT (ctlv3) und der Wärmepumpe
(HMU) als HA-Entitäten sichtbar. Jede ist am echten Gerät per Roh-Lesung
(`ebusctl hex …`) gegengeprüft – keine geratenen Offsets.

Anhängen an die jeweils genannte CSV im ebusd-Config-Ordner, dann ebusd neu
starten. Die eBUS Bridge legt die Entitäten danach selbst an.

## 1) Warmwasser-Statuscode lesbar — in `38.v32.csv`
Werte-Tabelle DIREKT an die vorhandene `Statenumber`-Zeile hängen; KEINE zweite
Nachricht aufs selbe Register 0dab00 (ebusd lehnt Duplikate ab -> lädt still
nicht). 24 = Warmwasser feldverifiziert (14,45 kW + Vorlauf 57 °C zeitgleich mit
Statenumber 31→24). Zeigt dann Klartext statt Zahl; Automationen matchen Tokens.

## 2) Zusatzheizer-Freigabe der WP → `08.hmu.HW5103.csv`
`releasebackup` ist Bit 1 von Byte 7 der SetMode-Schreibnachricht (b510/00).
Wird passiv mitgehört (`u`), kein aktiver Bus-Read. Aufbau aus `find -f`:
Byte0 hcmode · 1 flowtemp · 2 hwctemp · 3 hwcflowtemp · 4 IGN · 5 disable-Bits ·
6 IGN · 7 {remotecontrolhcpump=0, releasebackup=1, releasecooling=2}.

OFFEN: exaktes Datei-Spaltenformat der 08.hmu prüfen, bevor die Zeile steht
(nicht `find -f`-Format übernehmen). Zudem liegt sie auf b510/00 wie SetMode –
ob ebusd eine zweite Nachricht aufs selbe Register zulässt, ist zu testen
(Statenumber/StatenumberText hat gezeigt: Duplikate werden abgelehnt).
Feld-Bitlage steht fest: Bit 1 von Byte 7 (`IGN:7` + `BI1:1`).

Vorbehalt: das ist die *interne* Zusatzheizer-Freigabe der Wärmepumpe – nicht
zwingend das Signal für den externen eloBlock (Adresse 38), den der Regler
direkt über dessen FlowTempDemand ansteuert.

## 3) Legionellenschutz Zeit + Tag → `15.ctlv3.csv`
ID-Schema an `HwcTempDesired` verifiziert (`@base 0x24,0x2,RW,BLOCK,SUB` +
`@ext REG` → b524-ID `02 RW BLOCK SUB REG 00`). Roh-Lesung bestätigt Aufbau
`IGN:4` (Echo) + Wert:

- Zeit `0x2a`: Antwort `07 0300 2a00 04 00 00` → HTI `04:00:00`
- Tag  `0x2b`: Antwort `06 0300 2b00 00 00`   → daysel 0 = **off** (Schutz aus)

WICHTIG: im DATEI-Format schreiben (leere circuit- UND level-Spalte, leeres
part), NICHT im `ebusctl find -f`-Format. `find -f` lässt die level-Spalte weg
und zeigt circuit/zz explizit -> so übernommen verrutschen alle Spalten und
ebusd verwirft die Zeile still. Vorlage ist eine echte Datei-Zeile (z. B.
`ContinuousHeating` in 15.ctlv3.csv).

```csv
r,,,HwcLegionellaTime,Legionellenschutz Uhrzeit,,,b524,020000002a00,ign,,IGN:4,,,,value,,HTI,,,
r,,,HwcLegionellaDay,Legionellenschutz Wochentag,,,b524,020000002b00,ign,,IGN:4,,,,value,,UIN,0=off;1=Mo;2=Di;3=Mi;4=Do;5=Fr;6=Sa;7=So;8=taeglich,,
```

Tabelle daysel: 0=off, 1..7=Mo..So, 8=täglich. Stand hier: **off** – der
Legionellenschutz ist nicht aktiviert, war also nicht Ursache der elektrischen
Warmwasser-Ladung.
