import unittest
from pathlib import Path

from hl7fhir.parser import HL7Message, HL7ParseError

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.msg = HL7Message((SAMPLES / "adt_a01.hl7").read_text())

    def test_message_type_and_control_id(self):
        self.assertEqual(self.msg.message_type, "ADT^A01")
        self.assertEqual(self.msg.control_id, "MSG00001")

    def test_msh_delimiter_fields_are_offset_correctly(self):
        self.assertEqual(self.msg.get("MSH-1"), "|")
        self.assertEqual(self.msg.get("MSH-2"), "^~\\&")
        self.assertEqual(self.msg.get("MSH-3"), "EPICADT")
        self.assertEqual(self.msg.get("MSH-12"), "2.5.1")

    def test_components(self):
        self.assertEqual(self.msg.get("PID-5.1"), "DOE")
        self.assertEqual(self.msg.get("PID-5.2"), "JANE")
        self.assertEqual(self.msg.get("PV1-3.2"), "401")

    def test_repetitions(self):
        self.assertEqual(self.msg.get("PID-3(1).1"), "MRN123456")
        self.assertEqual(self.msg.get("PID-3(2).5"), "SS")
        self.assertEqual(len(self.msg.repetitions("PID-3")), 2)

    def test_missing_values_return_default(self):
        self.assertEqual(self.msg.get("PID-30"), "")
        self.assertEqual(self.msg.get("OBX-5", default="n/a"), "n/a")
        self.assertEqual(self.msg.get("PID-3(9).1"), "")

    def test_accepts_newline_separated_messages(self):
        raw = (SAMPLES / "adt_a01.hl7").read_text().replace("\r", "\n")
        self.assertEqual(HL7Message(raw).get("PID-8"), "F")

    def test_unescapes_hl7_escape_sequences(self):
        msg = HL7Message("MSH|^~\\&|A|B|C|D|20260101||ADT^A01|1|P|2.5.1\rNTE|1||Pain 7\\S\\10 \\F\\ resting")
        self.assertEqual(msg.get("NTE-3"), "Pain 7^10 | resting")

    def test_rejects_messages_without_msh(self):
        with self.assertRaises(HL7ParseError):
            HL7Message("PID|1||123")

    def test_rejects_bad_paths(self):
        with self.assertRaises(ValueError):
            self.msg.get("pid5")


if __name__ == "__main__":
    unittest.main()
