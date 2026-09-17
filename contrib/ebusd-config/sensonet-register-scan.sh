#!/bin/sh
# Vaillant sensoNET VR 921 (NETX3, Adresse f6) -- b509-Registerscan.
#
# Zweck: empirisch pruefen, ob das sensoNET AN ADRESSE f6 ueberhaupt lesbare
# Register hat, bevor man blind Definitionen anderer Geraete uebernimmt. Erste
# Direktmessungen (siehe f6.netx3.csv) lieferten auf b509/b511/b504 nur leere
# Quittungen -- das sensoNET ist ein Cloud-Gateway, kein datentragendes Geraet.
# Dieses Skript falsifiziert oder bestaetigt das ueber den vollen b509-Bereich.
#
# Ausgabe je Zeile:  0d<RR><ss> = <antwort-hex oder ERR>
#   0x00 mit Laengen-Byte 00  -> Register existiert, aber LEER (kein Wert)
#   Laenge > 0 mit echten Bytes -> KANDIDAT: mir schicken, ich dekodiere
#   ERR / timeout               -> Register nicht vorhanden
#
# Aufruf (im ebusd-Add-on-Terminal, wo 'ebusctl' laeuft):
#   sh sensonet-register-scan.sh > f6scan.txt
#   ... Datei schicken ...
# Bereich eingrenzen (dezimal):  sh sensonet-register-scan.sh 0 128
#
# Hinweise:
# - Nur Lesen (0d = Lese-Kommando), ungefaehrlich.
# - f6 ist ein sehr aktiver Master; nicht existierende Register laufen in den
#   Lese-Timeout -> ein voller Lauf (0..255 x 2 Subs) dauert etliche Minuten.
#   In einer ruhigen Phase laufen lassen.
# - </dev/null je Aufruf verhindert, dass ebusctl die Schleifen-Stdin frisst.
ADDR=f6
START=${1:-0}
END=${2:-255}
SUBS=${3:-00 01}
r=$START
while [ "$r" -le "$END" ]; do
  hx=$(printf '%02x' "$r")
  for s in $SUBS; do
    printf '0d%s%s = %s\n' "$hx" "$s" \
      "$(ebusctl hex ${ADDR}b509030d${hx}${s} </dev/null 2>&1)"
  done
  r=$((r + 1))
done
