from __future__ import annotations

from .parser import HL7Message

MASK = "***"

PHI_FIELDS = {
    "PID": {3, 4, 5, 6, 7, 9, 11, 13, 14, 18, 19, 20},
    "NK1": {2, 4, 5, 6},
    "GT1": {3, 5, 6, 7, 12},
    "IN1": {16, 19, 36},
}


def redact(raw: str) -> str:
    msg = HL7Message(raw)
    d = msg.delimiters
    out = []
    for seg in msg.segments:
        fields = list(seg.fields)
        for i in PHI_FIELDS.get(seg.name, ()):
            if i < len(fields) and fields[i]:
                fields[i] = d.repetition.join(
                    d.component.join(MASK if comp else "" for comp in rep.split(d.component))
                    for rep in fields[i].split(d.repetition)
                )
        if seg.name == "MSH":
            fields = ["MSH"] + fields[2:]
        out.append(d.field.join(fields))
    return "\r".join(out)
