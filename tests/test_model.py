"""Unit-Tests für model.py (HA-frei, direkt per Pfad geladen)."""
import importlib.util
from pathlib import Path

_MODEL_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components" / "ebus_bridge" / "model.py"
)
_spec = importlib.util.spec_from_file_location("ebus_model", _MODEL_PATH)
model = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(model)


SAMPLE = {
    "ctlv3": {
        "messages": {
            "Hc1HeatCurve": {
                "name": "Hc1HeatCurve", "write": False, "zz": 21,
                "fields": {"value": {"value": 0.8}},
                "fielddefs": [{"name": "value", "type": "EXP", "unit": ""}],
            },
            "Hc1HeatCurve-w": {
                "name": "Hc1HeatCurve", "write": True, "zz": 21,
                "fielddefs": [{"name": "value", "type": "EXP", "unit": ""}],
            },
            "Hc1MinFlowTempDesired": {
                "name": "Hc1MinFlowTempDesired", "write": False, "zz": 21,
                "fields": {"value": {"value": 30.0, "unit": "°C"}},
                "fielddefs": [{"name": "value", "type": "UIN", "unit": "°C"}],
            },
            "PumpMode": {
                "name": "PumpMode", "write": False, "zz": 21,
                "fields": {"value": {"value": "off"}},
                "fielddefs": [
                    {"name": "value", "type": "UCH", "values": {"0": "off", "1": "on"}}
                ],
            },
            "Status01": {
                "name": "Status01", "write": False, "zz": 21,
                "fields": {"flow": {"value": 40.0}, "ret": {"value": 35.0}},
                "fielddefs": [
                    {"name": "ign", "type": "IGN"},
                    {"name": "flow", "type": "UIN", "unit": "°C"},
                    {"name": "ret", "type": "UIN", "unit": "°C"},
                ],
            },
        }
    },
    "scan.15": {
        "messages": {
            "id": {
                "name": "scan.15 id", "write": False, "zz": 21,
                "fields": {
                    "mf": {"value": "Vaillant"}, "id": {"value": "CTLV3"},
                    "sw": {"value": "1.2"}, "hw": {"value": "3.4"},
                },
                "fielddefs": [
                    {"name": "mf"}, {"name": "id"}, {"name": "sw"}, {"name": "hw"},
                ],
            }
        }
    },
    "global": {"messages": 605, "signal": True, "version": "26.1", "access": "*"},
}


def _by_key(descs):
    return {d.key: d for d in descs}


def test_parse_values_reads_only():
    values = model.parse_values(SAMPLE)
    assert values[("ctlv3", "Hc1HeatCurve", "value")] == 0.8
    assert values[("ctlv3", "Hc1MinFlowTempDesired", "value")] == 30.0
    assert values[("ctlv3", "PumpMode", "value")] == "off"
    # Ident- und Scan-Nachrichten liefern keine Werte
    assert not any(c == "scan.15" for (c, _m, _f) in values)
    assert ("ctlv3", "scan.15 id", "mf") not in values


def test_definitions_temperature_bounds_allow_negative():
    d = _by_key(model.parse_definitions(SAMPLE))[
        ("ctlv3", "Hc1MinFlowTempDesired", "value")
    ]
    # A1: °C darf negativ sein (kein Klemmen bei 0)
    assert d.min_value == -60
    assert d.max_value == 150
    assert d.step == 0.5
    assert d.unit == "°C"
    assert d.numeric is True


def test_definitions_writable_from_write_message():
    d = _by_key(model.parse_definitions(SAMPLE))[("ctlv3", "Hc1HeatCurve", "value")]
    assert d.writable is True          # aus der -w-Nachricht
    assert d.numeric is True           # EXP ohne values
    assert d.unit is None              # "" -> None


def test_definitions_skip_ign_and_ident_and_multi_label():
    descs = _by_key(model.parse_definitions(SAMPLE))
    # IGN-Feld wird übersprungen
    assert ("ctlv3", "Status01", "ign") not in descs
    # Mehrfeld -> Label "<message> <field>"
    assert descs[("ctlv3", "Status01", "flow")].label == "Status01 flow"
    # Ident/Scan erzeugt keine Entity
    assert not any(m == "scan.15 id" for (_c, m, _f) in descs)


def test_parse_device_meta_maps_scan_to_circuit():
    meta = model.parse_device_meta(SAMPLE)
    assert meta["ctlv3"] == {
        "manufacturer": "Vaillant", "model": "CTLV3", "sw": "1.2", "hw": "3.4",
    }


def test_parse_global_filters_keys():
    g = model.parse_global(SAMPLE)
    assert g == {"messages": 605, "signal": True, "version": "26.1"}
    assert "access" not in g


def test_parse_definitions_survives_global_int_messages():
    # global.messages ist ein int -> darf nicht crashen
    assert model.parse_definitions({"global": {"messages": 605}}) == []


def _fd(values):
    return model.FieldDesc(
        circuit="c", message="m", field="f", label="l", unit=None, values=values,
        numeric=False, min_value=None, max_value=None, step=None, writable=True,
    )


def test_is_binary_and_tokens():
    assert model.is_binary(_fd({"0": "off", "1": "on"})) is True
    assert model.is_binary(_fd({"0": "no", "1": "yes"})) is True
    assert model.is_binary(_fd({"0": "off", "1": "auto", "2": "day"})) is False
    assert model.is_binary(_fd(None)) is False
    assert model.bool_tokens(_fd({"0": "no", "1": "yes"})) == ("yes", "no")


def test_value_is_on():
    assert model.value_is_on("on") is True
    assert model.value_is_on("off") is False
    assert model.value_is_on(None) is None


def test_parse_ages_reads_lastup_per_message():
    """`?verbose` liefert `lastup` je Nachricht -- Grundlage der Frische-Erkennung."""
    data = {
        "ctlv3": {
            "messages": {
                "Z1RoomTemp": {
                    "name": "Z1RoomTemp",
                    "lastup": 1700000100,
                    "fields": {"0": {"name": "temp", "value": 22.0}},
                },
                "HwcTempDesired": {
                    "name": "HwcTempDesired",
                    "lastup": 1700000000,
                    "fields": {"0": {"name": "temp", "value": 50}},
                },
            }
        }
    }
    ages = model.parse_ages(data)
    assert ages == {
        ("ctlv3", "Z1RoomTemp"): 1700000100,
        ("ctlv3", "HwcTempDesired"): 1700000000,
    }


def test_parse_ages_skips_messages_without_lastup():
    """Ohne `verbose` fehlt `lastup` -- dann darf nichts gemeldet werden."""
    data = {"c": {"messages": {"M": {"name": "M", "fields": {}}}}}
    assert model.parse_ages(data) == {}


def test_parse_definitions_passive_multifield_readonly():
    """SetMode (passiv, mehrfeldrig) -> Felder read-only + passive-Flag."""
    data = {"wp0": {"messages": {"SetMode": {
        "name": "SetMode", "passive": True, "write": True,
        "fielddefs": [
            {"name": "hcmode", "type": "UCH", "values": {"0": "auto"}},
            {"name": "releasebackup", "type": "UCH", "values": {"0": "off", "1": "on"}},
        ],
    }}}}
    descs = {d.field: d for d in model.parse_definitions(data)}
    assert set(descs) == {"hcmode", "releasebackup"}
    assert all(d.passive and not d.writable for d in descs.values())


def test_parse_definitions_single_field_write_is_writable():
    """Einzelfeld-Write bleibt schreibbar; nicht passiv."""
    data = {"c": {"messages": {
        "Temp": {"name": "Temp", "write": False,
                 "fielddefs": [{"name": "value", "type": "EXP", "unit": "°C"}]},
        "Temp-w": {"name": "Temp", "write": True,
                   "fielddefs": [{"name": "value", "type": "EXP", "unit": "°C"}]},
    }}}
    d = model.parse_definitions(data)[0]
    assert d.writable is True and d.passive is False


def test_parse_values_includes_passive_command():
    """releasebackup aus der passiv mitgehörten SetMode wird sichtbar."""
    data = {"wp0": {"messages": {"SetMode": {
        "name": "SetMode", "passive": True, "write": True,
        "fields": {"releasebackup": {"name": "releasebackup", "value": 1}},
    }}}}
    assert model.parse_values(data)[("wp0", "SetMode", "releasebackup")] == 1


def test_parse_values_skips_pure_write():
    """Reine Write-Nachricht (nicht passiv) liefert keinen Wert."""
    data = {"c": {"messages": {"Cmd": {
        "name": "Cmd", "write": True,
        "fields": {"value": {"name": "value", "value": 5}},
    }}}}
    assert model.parse_values(data) == {}
