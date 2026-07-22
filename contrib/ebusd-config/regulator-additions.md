# Zusatz-Register für Regler-Entscheidungen (feldverifiziert)

Diese Zeilen machen Entscheidungen des sensoCOMFORT (ctlv3) und der Wärmepumpe
(HMU) als HA-Entitäten sichtbar. Jede ist am echten Gerät per Roh-Lesung
(`ebusctl hex …`) gegengeprüft – keine geratenen Offsets.

Anhängen an die jeweils genannte CSV im ebusd-Config-Ordner, dann ebusd neu
starten. Die eBUS Bridge legt die Entitäten danach selbst an.

## 1) Warmwasser-Statuscode lesbar — bereits in `38.v32.csv`
Der eloBlock meldet `Statenumber` als Zahl; `StatenumberText` gibt denselben
Wert als Klartext (24 = Warmwasser feldverifiziert: 14,45 kW + Vorlauf 57 °C
zeitgleich mit Statenumber 31→24).

## 2) Zusatzheizer-Freigabe der WP → `08.hmu.HW5103.csv`
`releasebackup` ist Bit 1 von Byte 7 der SetMode-Schreibnachricht (b510/00).
Wird passiv mitgehört (`u`), kein aktiver Bus-Read. Aufbau aus `find -f`:
Byte0 hcmode · 1 flowtemp · 2 hwctemp · 3 hwcflowtemp · 4 IGN · 5 disable-Bits ·
6 IGN · 7 {remotecontrolhcpump=0, releasebackup=1, releasecooling=2}.

```csv
u,wp0,ReleaseBackup,Zusatzheizer-Freigabe vom Regler,,08,b510,00,ign,m,IGN:7,,,,value,m,BI1:1,0=off;1=on,,
```

Vorbehalt: das ist die *interne* Zusatzheizer-Freigabe der Wärmepumpe – nicht
zwingend das Signal für den externen eloBlock (Adresse 38), den der Regler
direkt über dessen FlowTempDemand ansteuert.

## 3) Legionellenschutz Zeit + Tag → `15.ctlv3.csv`
ID-Schema an `HwcTempDesired` verifiziert (`@base 0x24,0x2,RW,BLOCK,SUB` +
`@ext REG` → b524-ID `02 RW BLOCK SUB REG 00`). Roh-Lesung bestätigt Aufbau
`IGN:4` (Echo) + Wert:

- Zeit `0x2a`: Antwort `07 0300 2a00 04 00 00` → HTI `04:00:00`
- Tag  `0x2b`: Antwort `06 0300 2b00 00 00`   → daysel 0 = **off** (Schutz aus)

```csv
r,ctlv3,HwcLegionellaTime,Legionellenschutz Uhrzeit,,15,b524,020000002a00,ign,s,IGN:4,,,,value,s,HTI,,,
r,ctlv3,HwcLegionellaDay,Legionellenschutz Wochentag,,15,b524,020000002b00,ign,s,IGN:4,,,,value,s,UIN,0=off;1=Mo;2=Di;3=Mi;4=Do;5=Fr;6=Sa;7=So;8=taeglich,,
```

Tabelle daysel: 0=off, 1..7=Mo..So, 8=täglich. Stand hier: **off** – der
Legionellenschutz ist nicht aktiviert, war also nicht Ursache der elektrischen
Warmwasser-Ladung.
