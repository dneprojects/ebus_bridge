"""Konstanten für die ebusd-Direct-Integration."""

DOMAIN = "ebusd_direct"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_HTTP_PORT = "http_port"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_EXCLUDE = "exclude"

DEFAULT_PORT = 8888  # TCP-Kommandoport (Schreiben)
DEFAULT_HTTP_PORT = 8889  # HTTP-JSON-Port (Lesen/Definitionen)
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_EXCLUDE = "Timer"  # Zeitprogramme standardmäßig ausblenden (viel Rauschen)
