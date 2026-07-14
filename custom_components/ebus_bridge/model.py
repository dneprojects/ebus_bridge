"""Parsen der ebusd-HTTP-JSON in Feld-Deskriptoren + Geräte-Metadaten.

JSON:  { "<circuit>": { "messages": {
           "<key>": { "name":.., "write":bool, "passive":bool,
                      "fields":    { "<field>": {"name":.., "value":..} },
                      "fielddefs": [ {"name":.., "type":.., "unit":.., "values":{..}} ] } } },
         "global": {..} }
Read-/Write-Nachricht: gleicher `name`, Write-Key hat "-w"-Suffix.
"""
from __future__ import annotations

from typing import Any, NamedTuple

# Pseudo-Kreise, die keine echten Geräte sind
_SKIP_CIRCUITS = {"global", "broadcast", "general", "memory", "scan"}
# Feldnamen, die eine Scan-/Ident-Nachricht ausmachen (-> Geräte-Metadaten statt Entity)
_IDENT_FIELDS = {"mf", "id", "sw", "hw"}

_TYPE_BOUNDS: dict[str, tuple[float, float, float]] = {
    "UCH": (0, 254, 1), "SCH": (-127, 127, 1),
    "UIN": (0, 65534, 1), "SIN": (-32767, 32767, 1),
    "ULG": (0, 4294967294, 1), "SLG": (-2147483647, 2147483647, 1),
    "BCD": (0, 99, 1),
    "D1B": (-127, 127, 1), "D1C": (0, 100, 0.5),
    "D2B": (-128, 127, 0.1), "D2C": (-2048, 2047, 0.1),
    "EXP": (-3000, 3000, 0.1), "EXP2": (-3000, 3000, 0.1),
    "FLT": (-32.767, 32.767, 0.001), "FLR": (-32.767, 32.767, 0.001),
}


class FieldDesc(NamedTuple):
    circuit: str
    message: str
    field: str
    label: str
    unit: str | None
    values: dict[str, str] | None
    numeric: bool
    min_value: float | None
    max_value: float | None
    step: float | None
    writable: bool

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.circuit, self.message, self.field)

    @property
    def uid(self) -> str:
        return f"{self.circuit}_{self.message}_{self.field}".lower()


def _basetype(type_str: str | None) -> str:
    return (type_str or "").split(":", 1)[0].strip().upper()


def _skip_circuit(circuit: str) -> bool:
    c = circuit.lower()
    return c in _SKIP_CIRCUITS or c.startswith("scan")


def _field_names(msg: dict) -> set[str]:
    return {(fd.get("name") or "").lower() for fd in msg.get("fielddefs", [])}


def _is_ident(msg: dict) -> bool:
    names = _field_names(msg)
    return "mf" in names or _IDENT_FIELDS.issubset(names)


def _messages(cdata: Any) -> dict:
    """Gibt das messages-Dict zurück (im 'global'-Block ist messages ein int!)."""
    if isinstance(cdata, dict):
        messages = cdata.get("messages")
        if isinstance(messages, dict):
            return messages
    return {}


def _iter_messages(data: dict[str, Any]):
    for circuit, cdata in data.items():
        if _skip_circuit(circuit):
            continue
        for msg in _messages(cdata).values():
            if isinstance(msg, dict):
                yield circuit, msg


def parse_definitions(data: dict[str, Any]) -> list[FieldDesc]:
    writable: set[tuple[str, str]] = set()
    for circuit, msg in _iter_messages(data):
        if not _is_ident(msg) and msg.get("write"):
            writable.add((circuit, msg.get("name")))

    seen: set[tuple[str, str, str]] = set()
    out: list[FieldDesc] = []
    for circuit, msg in _iter_messages(data):
        if _is_ident(msg):
            continue
        name = msg.get("name")
        real = [
            fd for fd in msg.get("fielddefs", [])
            if fd.get("name") and _basetype(fd.get("type")) != "IGN" and "value" not in fd
        ]
        multi = len(real) > 1
        for fd in real:
            fname = fd["name"]
            key = (circuit, name, fname)
            if key in seen:
                continue
            seen.add(key)
            btype = _basetype(fd.get("type"))
            values = fd.get("values") or None
            lo, hi, step = _TYPE_BOUNDS.get(btype, (None, None, None))
            if fd.get("unit") == "°C":
                # realistische Heizungs-Spanne; erlaubt Außen-/Sollwerte < 0 °C
                lo, hi, step = -60, 150, 0.5
            out.append(FieldDesc(
                circuit=circuit, message=name, field=fname,
                label=name if not multi else f"{name} {fname}",
                unit=fd.get("unit") or None, values=values,
                numeric=values is None and btype in _TYPE_BOUNDS,
                min_value=lo, max_value=hi, step=step,
                writable=(circuit, name) in writable,
            ))
    return out


def parse_values(data: dict[str, Any]) -> dict[tuple[str, str, str], Any]:
    values: dict[tuple[str, str, str], Any] = {}
    for circuit, msg in _iter_messages(data):
        if msg.get("write") or _is_ident(msg):
            continue
        name = msg.get("name")
        for fkey, fval in (msg.get("fields") or {}).items():
            if isinstance(fval, dict):
                fname = fval.get("name") or fkey
                values[(circuit, name, fname)] = fval.get("value")
    return values


def _extract_ident(fields: dict) -> dict[str, str]:
    def _val(target: str):
        for fkey, fval in fields.items():
            if isinstance(fval, dict) and (fval.get("name") or fkey).lower() == target:
                return fval.get("value")
        return None

    info: dict[str, str] = {}
    if _val("mf"):
        info["manufacturer"] = str(_val("mf"))
    if _val("id"):
        info["model"] = str(_val("id"))
    if _val("sw") is not None:
        info["sw"] = str(_val("sw"))
    if _val("hw") is not None:
        info["hw"] = str(_val("hw"))
    return info


def parse_device_meta(data: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Scan-Ident (MF/ID/SW/HW, unter Scan.NN-Kreisen) je Adresse -> echter Kreis.

    Zuordnung über die Zieladresse `zz`: Scan-Nachricht mit zz==N wird dem echten
    Kreis zugeordnet, dessen Nachrichten dieselbe zz haben.
    """
    # 1) Adresse -> Metadaten (Ident-Nachrichten, egal in welchem Kreis)
    by_addr: dict[int, dict[str, str]] = {}
    for cdata in data.values():
        for msg in _messages(cdata).values():
            if not isinstance(msg, dict) or not _is_ident(msg):
                continue
            addr = msg.get("zz")
            info = _extract_ident(msg.get("fields") or {})
            if addr is not None and info:
                by_addr.setdefault(addr, {}).update(info)

    # 2) echter Kreis -> Adresse (zz einer echten Nachricht)
    result: dict[str, dict[str, str]] = {}
    for circuit, cdata in data.items():
        if _skip_circuit(circuit):
            continue
        for msg in _messages(cdata).values():
            if isinstance(msg, dict) and not _is_ident(msg) and msg.get("zz") is not None:
                addr = msg["zz"]
                if addr in by_addr:
                    result[circuit] = by_addr[addr]
                break
    return result


_BOOL_ON = {"on", "yes", "true"}
_BOOL_OFF = {"off", "no", "false"}


def is_binary(desc: FieldDesc) -> bool:
    """True, wenn das Feld eine reine On/Off-Enum ist (-> binary_sensor statt sensor)."""
    if not desc.values:
        return False
    names = {str(v).lower() for v in desc.values.values()}
    return bool(names) and names <= (_BOOL_ON | _BOOL_OFF)


def value_is_on(value: object) -> bool | None:
    if value is None:
        return None
    return str(value).lower() in _BOOL_ON


def bool_tokens(desc: FieldDesc) -> tuple[str, str]:
    """(on_token, off_token) aus der values-Map einer binären Nachricht.

    Namen werden im Original geschrieben (ebusd akzeptiert den Namen beim write).
    """
    on_token, off_token = "on", "off"
    for name in (desc.values or {}).values():
        low = str(name).lower()
        if low in _BOOL_ON:
            on_token = name
        elif low in _BOOL_OFF:
            off_token = name
    return on_token, off_token


# Bus-/Adapter-Diagnose aus dem globalen ebusd-Abschnitt.
_GLOBAL_KEYS = {
    "version", "signal", "symbolrate", "maxsymbolrate", "reconnects",
    "masters", "qq", "messages",
    "minarbitrationmicros", "maxarbitrationmicros",
    "minsymbollatency", "maxsymbollatency",
}


def parse_global(data: dict[str, Any]) -> dict[str, Any]:
    """Skalare aus dem `global`-Abschnitt (Signal, Rate, Timing …)."""
    g = data.get("global")
    if not isinstance(g, dict):
        return {}
    return {k: v for k, v in g.items() if k in _GLOBAL_KEYS}
