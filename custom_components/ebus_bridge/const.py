"""Konstanten für die eBUS-Bridge-Integration."""

DOMAIN = "ebus_bridge"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_HTTP_PORT = "http_port"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_EXCLUDE = "exclude"
CONF_FAST = "fast"

DEFAULT_PORT = 8888  # TCP-Kommandoport (Schreiben)
DEFAULT_HTTP_PORT = 8889  # HTTP-JSON-Port (Lesen/Definitionen)
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_EXCLUDE = "Timer"  # Zeitprogramme standardmäßig ausblenden (viel Rauschen)
# Diese Nachrichten werden je Zyklus direkt vom Bus gelesen (required+maxage),
# statt auf ebusds Poll-Umlauf zu warten. Klein halten: jeder Eintrag kostet
# einen Bus-Read je scan_interval.
DEFAULT_FAST = ""
