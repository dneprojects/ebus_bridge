"""Konstanten für die eBUS-Bridge-Integration."""

DOMAIN = "ebus_bridge"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_HTTP_PORT = "http_port"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_EXCLUDE = "exclude"
CONF_POLL_PRIORITY = "poll_priority"

DEFAULT_PORT = 8888  # TCP-Kommandoport (Schreiben)
DEFAULT_HTTP_PORT = 8889  # HTTP-JSON-Port (Lesen/Definitionen)
DEFAULT_SCAN_INTERVAL = 30
# ebusd pollt eine Nachricht je pollinterval -> Buslast konstant, 0 = kein Polling
DEFAULT_POLL_PRIORITY = 3
DEFAULT_EXCLUDE = "Timer"  # Zeitprogramme standardmäßig ausblenden (viel Rauschen)
