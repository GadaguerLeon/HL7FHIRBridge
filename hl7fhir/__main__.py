from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .client import PUBLIC_TEST_SERVER, FHIRClient, FHIRError
from .mapping import adt_to_bundle
from .parser import HL7Message
from .redact import redact


def _load(path: str) -> HL7Message:
    return HL7Message(Path(path).read_text())


def cmd_inspect(args) -> int:
    msg = _load(args.file)
    print(f"{msg.message_type}  control id {msg.control_id}\n")
    for seg in msg.segments:
        for i, value in enumerate(seg.fields[1:], start=1):
            if value:
                print(f"{seg.name}-{i:<3} {value}")
        print()
    return 0


def cmd_convert(args) -> int:
    print(json.dumps(adt_to_bundle(_load(args.file), args.tz), indent=2))
    return 0


def cmd_redact(args) -> int:
    print(redact(Path(args.file).read_text()).replace("\r", "\n"))
    return 0


def cmd_send(args) -> int:
    bundle = adt_to_bundle(_load(args.file), args.tz)
    client = FHIRClient(args.server)
    try:
        result = client.transaction(bundle)
    except FHIRError as err:
        print(err, file=sys.stderr)
        return 1
    for entry in result.get("entry", []):
        resp = entry.get("response", {})
        print(f"{resp.get('status', '?'):<12} {resp.get('location', '')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hl7fhir")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, func, help_text in (
        ("inspect", cmd_inspect, "list every populated field"),
        ("convert", cmd_convert, "convert an ADT message to a FHIR Bundle"),
        ("redact", cmd_redact, "mask PHI fields"),
        ("send", cmd_send, "send the converted Bundle to a FHIR server"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("file")
        p.add_argument("--tz", default="+00:00", help="timezone for timestamps without one")
        if name == "send":
            p.add_argument("--server", default=PUBLIC_TEST_SERVER)
        p.set_defaults(func=func)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
