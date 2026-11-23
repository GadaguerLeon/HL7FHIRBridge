from __future__ import annotations

import re
import uuid

from .parser import HL7Message

GENDER = {"M": "male", "F": "female", "O": "other", "A": "other", "U": "unknown", "N": "unknown"}

PATIENT_CLASS = {
    "I": ("IMP", "inpatient encounter"),
    "O": ("AMB", "ambulatory"),
    "E": ("EMER", "emergency"),
    "P": ("PRENC", "pre-admission"),
    "R": ("AMB", "ambulatory"),
    "B": ("AMB", "ambulatory"),
}

EVENT_STATUS = {
    "A01": "in-progress",
    "A04": "in-progress",
    "A05": "planned",
    "A03": "finished",
    "A11": "cancelled",
}

ACT_CODE_SYSTEM = "http://terminology.hl7.org/CodeSystem/v3-ActCode"
ID_TYPE_SYSTEM = "http://terminology.hl7.org/CodeSystem/v2-0203"

SENSITIVE_ID_TYPES = {"SS", "DL", "PPN"}

_TS = re.compile(
    r"^(?P<y>\d{4})(?P<mo>\d{2})?(?P<d>\d{2})?"
    r"(?:(?P<h>\d{2})(?P<mi>\d{2})(?P<s>\d{2})?(?:\.\d+)?)?"
    r"(?P<tz>[+-]\d{4})?$"
)


class MappingError(ValueError):
    pass


def hl7_date(value: str) -> str | None:
    m = _TS.match(value or "")
    if not m:
        return None
    parts = [m["y"]] + [p for p in (m["mo"], m["d"]) if p]
    return "-".join(parts)


def hl7_datetime(value: str, default_tz: str = "+00:00") -> str | None:
    m = _TS.match(value or "")
    if not m:
        return None
    if not m["h"]:
        return hl7_date(value)
    tz = m["tz"]
    tz = f"{tz[:3]}:{tz[3:]}" if tz else default_tz
    return f"{m['y']}-{m['mo']}-{m['d']}T{m['h']}:{m['mi']}:{m['s'] or '00'}{tz}"


def _identifiers(msg: HL7Message) -> list[dict]:
    identifiers = []
    for rep in msg.repetitions("PID-3"):
        c = msg.components(rep) + [""] * 5
        value, authority, id_type = c[0], c[3], c[4]
        if not value or id_type in SENSITIVE_ID_TYPES:
            continue
        ident = {"value": value}
        if authority:
            ident["system"] = f"urn:id:{authority}"
        if id_type:
            ident["type"] = {"coding": [{"system": ID_TYPE_SYSTEM, "code": id_type}]}
        identifiers.append(ident)
    return identifiers


def _name(msg: HL7Message) -> list[dict]:
    family, given, middle = msg.get("PID-5.1"), msg.get("PID-5.2"), msg.get("PID-5.3")
    if not (family or given):
        return []
    name = {"use": "official"}
    if family:
        name["family"] = family.title()
    givens = [g.title() for g in (given, middle) if g]
    if givens:
        name["given"] = givens
    return [name]


def _address(msg: HL7Message) -> list[dict]:
    line1, line2 = msg.get("PID-11.1"), msg.get("PID-11.2")
    city, state, postal, country = (msg.get(f"PID-11.{i}") for i in (3, 4, 5, 6))
    if not any((line1, city, state, postal)):
        return []
    address = {"use": "home"}
    lines = [part for part in (line1, line2) if part]
    if lines:
        address["line"] = lines
    for key, val in (("city", city), ("state", state), ("postalCode", postal), ("country", country)):
        if val:
            address[key] = val
    return [address]


def _telecom(msg: HL7Message) -> list[dict]:
    telecoms = []
    for rep in msg.repetitions("PID-13"):
        c = msg.components(rep) + [""] * 7
        number = c[0]
        area, local = c[5], c[6]
        if not number and local:
            number = f"({area}) {local[:3]}-{local[3:]}" if area else local
        if number:
            telecoms.append({"system": "phone", "value": number, "use": "home"})
    return telecoms


def adt_to_patient(msg: HL7Message) -> dict:
    if msg.segment("PID") is None:
        raise MappingError("message has no PID segment")
    patient = {"resourceType": "Patient"}
    for key, value in (
        ("identifier", _identifiers(msg)),
        ("name", _name(msg)),
        ("telecom", _telecom(msg)),
        ("gender", GENDER.get(msg.get("PID-8").upper())),
        ("birthDate", hl7_date(msg.get("PID-7"))),
        ("address", _address(msg)),
    ):
        if value:
            patient[key] = value
    return patient


def adt_to_encounter(msg: HL7Message, patient_ref: str, default_tz: str = "+00:00") -> dict:
    if msg.segment("PV1") is None:
        raise MappingError("message has no PV1 segment")
    event = msg.get("MSH-9.2") or msg.get("EVN-1")
    code, display = PATIENT_CLASS.get(msg.get("PV1-2"), ("AMB", "ambulatory"))

    encounter = {
        "resourceType": "Encounter",
        "status": EVENT_STATUS.get(event, "unknown"),
        "class": {"system": ACT_CODE_SYSTEM, "code": code, "display": display},
        "subject": {"reference": patient_ref},
    }

    visit = msg.get("PV1-19.1")
    if visit:
        encounter["identifier"] = [{"use": "official", "value": visit}]

    period = {}
    start = hl7_datetime(msg.get("PV1-44"), default_tz)
    end = hl7_datetime(msg.get("PV1-45"), default_tz)
    if start:
        period["start"] = start
    if end:
        period["end"] = end
    if period:
        encounter["period"] = period

    unit, room, bed = msg.get("PV1-3.1"), msg.get("PV1-3.2"), msg.get("PV1-3.3")
    location = " / ".join(p for p in (unit, f"Room {room}" if room else "", f"Bed {bed}" if bed else "") if p)
    if location:
        encounter["location"] = [{"location": {"display": location}}]

    return encounter


def adt_to_bundle(msg: HL7Message, default_tz: str = "+00:00") -> dict:
    if msg.get("MSH-9.1") != "ADT":
        raise MappingError(f"only ADT messages are supported, got {msg.message_type}")

    patient = adt_to_patient(msg)
    patient_url = f"urn:uuid:{uuid.uuid4()}"
    encounter = adt_to_encounter(msg, patient_url, default_tz)

    patient_request = {"method": "POST", "url": "Patient"}
    mrn = next((i for i in patient.get("identifier", [])
                if i.get("type", {}).get("coding", [{}])[0].get("code") == "MR"), None)
    if mrn and "system" in mrn:
        patient_request["ifNoneExist"] = f"identifier={mrn['system']}|{mrn['value']}"

    return {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [
            {"fullUrl": patient_url, "resource": patient, "request": patient_request},
            {"fullUrl": f"urn:uuid:{uuid.uuid4()}", "resource": encounter,
             "request": {"method": "POST", "url": "Encounter"}},
        ],
    }
