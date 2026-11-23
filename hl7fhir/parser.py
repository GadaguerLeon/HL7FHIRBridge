from __future__ import annotations

import re
from dataclasses import dataclass, field

_PATH = re.compile(
    r"^(?P<seg>[A-Z][A-Z0-9]{2})"
    r"(?:\((?P<segrep>\d+)\))?"
    r"-(?P<field>\d+)"
    r"(?:\((?P<rep>\d+)\))?"
    r"(?:\.(?P<comp>\d+))?"
    r"(?:\.(?P<sub>\d+))?$"
)


class HL7ParseError(ValueError):
    pass


@dataclass(frozen=True)
class Delimiters:
    field: str = "|"
    component: str = "^"
    repetition: str = "~"
    escape: str = "\\"
    subcomponent: str = "&"


@dataclass
class Segment:
    name: str
    fields: list[str] = field(default_factory=list)

    def field(self, index: int) -> str:
        return self.fields[index] if 0 < index < len(self.fields) else ""


class HL7Message:
    def __init__(self, raw: str):
        text = raw.strip().replace("\r\n", "\r").replace("\n", "\r")
        lines = [line for line in text.split("\r") if line.strip()]
        if not lines or not lines[0].startswith("MSH"):
            raise HL7ParseError("message must start with an MSH segment")

        msh = lines[0]
        if len(msh) < 8:
            raise HL7ParseError("MSH segment is too short")
        encoding = msh[4:8]
        self.delimiters = Delimiters(
            field=msh[3],
            component=encoding[0],
            repetition=encoding[1],
            escape=encoding[2],
            subcomponent=encoding[3],
        )

        self.segments: list[Segment] = []
        for line in lines:
            parts = line.split(self.delimiters.field)
            if parts[0] == "MSH":
                # MSH-1 is the field separator, so shift every MSH field by one
                parts = ["MSH", self.delimiters.field] + parts[1:]
            self.segments.append(Segment(name=parts[0], fields=parts))

    def segments_named(self, name: str) -> list[Segment]:
        return [s for s in self.segments if s.name == name]

    def segment(self, name: str, occurrence: int = 1) -> Segment | None:
        found = self.segments_named(name)
        return found[occurrence - 1] if len(found) >= occurrence else None

    def get(self, path: str, default: str = "") -> str:
        match = _PATH.match(path)
        if not match:
            raise ValueError(f"invalid path: {path!r}")
        seg = self.segment(match["seg"], int(match["segrep"] or 1))
        if seg is None:
            return default

        index = int(match["field"])
        raw = seg.field(index)
        if seg.name == "MSH" and index in (1, 2):
            return raw or default

        reps = raw.split(self.delimiters.repetition)
        rep_i = int(match["rep"] or 1) - 1
        if rep_i >= len(reps):
            return default
        value = reps[rep_i]

        if match["comp"]:
            comps = value.split(self.delimiters.component)
            comp_i = int(match["comp"]) - 1
            value = comps[comp_i] if comp_i < len(comps) else ""
            if match["sub"]:
                subs = value.split(self.delimiters.subcomponent)
                sub_i = int(match["sub"]) - 1
                value = subs[sub_i] if sub_i < len(subs) else ""

        value = self.unescape(value)
        return value if value != "" else default

    def repetitions(self, path: str) -> list[str]:
        match = _PATH.match(path)
        if not match or match["comp"]:
            raise ValueError("repetitions() takes a field path such as 'PID-3'")
        seg = self.segment(match["seg"], int(match["segrep"] or 1))
        if seg is None:
            return []
        raw = seg.field(int(match["field"]))
        return [r for r in raw.split(self.delimiters.repetition) if r]

    def components(self, value: str) -> list[str]:
        return [self.unescape(c) for c in value.split(self.delimiters.component)]

    def unescape(self, value: str) -> str:
        e = self.delimiters.escape
        if e not in value:
            return value
        d = self.delimiters
        table = {"F": d.field, "S": d.component, "T": d.subcomponent,
                 "R": d.repetition, "E": d.escape}
        return re.sub(
            re.escape(e) + r"([FSTRE])" + re.escape(e),
            lambda m: table[m.group(1)],
            value,
        )

    @property
    def message_type(self) -> str:
        return f"{self.get('MSH-9.1')}^{self.get('MSH-9.2')}"

    @property
    def control_id(self) -> str:
        return self.get("MSH-10")

    def __repr__(self) -> str:
        names = ",".join(s.name for s in self.segments)
        return f"<HL7Message {self.message_type} [{names}]>"


def parse(raw: str) -> HL7Message:
    return HL7Message(raw)
