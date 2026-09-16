#!/bin/sh
# eloBlock (VE24, Adresse 38 hinter V32-Koppler) -- b509-Registerscan.
#
# Liest 0d<RR>00 fuer RR = START..END roh via 'ebusctl hex' und gibt je Zeile
#   0d<RR>00 = <antwort-hex oder ERR>
# aus. Zweck: die echten Betriebszaehler des eloBlock finden. Die aus der
# Community-Liste uebernommenen d.80..d.83 (0d2800/2900/2200/2300) liefern auf
# diesem VE24 konstant 0 und wurden in 38.v32.csv auskommentiert.
#
# Methode -- Vorher/Nachher-Diff:
#   sh eloblock-register-scan.sh > scanA.txt          # jetzt (Ruhezustand)
#   ... eloBlock einen Warmwasser-/Heizlauf machen lassen ...
#   sh eloblock-register-scan.sh > scanB.txt          # danach
#   diff scanA.txt scanB.txt
# Register, deren Wert in B groesser ist als in A, sind die Zaehler
# (Stunden: +1..2, Starts: +1). Beide Dateien schicken -- ich dekodiere sie.
#
# Optional Bereich eingrenzen (dezimal): sh eloblock-register-scan.sh 0 128
#
# Hinweise:
# - Dort ausfuehren, wo 'ebusctl' laeuft (ebusd-Add-on-Terminal).
# - Nur Lesen (0d = Lese-Kommando), ungefaehrlich.
# - Nicht existierende Register laufen in den Lese-Timeout -> ein voller Lauf
#   (0..255) kann etliche Minuten dauern. Am besten in einer ruhigen Phase.
# - </dev/null je Aufruf verhindert, dass ebusctl die Schleifen-Stdin frisst.
START=${1:-0}
END=${2:-255}
r=$START
while [ "$r" -le "$END" ]; do
  hx=$(printf '%02x' "$r")
  printf '0d%s00 = %s\n' "$hx" "$(ebusctl hex 38b509030d${hx}00 </dev/null 2>&1)"
  r=$((r + 1))
done
