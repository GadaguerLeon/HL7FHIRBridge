import io
import json
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from hl7fhir.client import FHIRClient, FHIRError
from hl7fhir.parser import HL7Message
from hl7fhir.redact import redact

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


class RedactTests(unittest.TestCase):
    def setUp(self):
        self.raw = (SAMPLES / "adt_a01.hl7").read_text()
        self.clean = redact(self.raw)

    def test_phi_is_removed(self):
        for secret in ("DOE", "JANE", "19850214", "MAIN ST", "5550123", "999999999", "MRN123456"):
            self.assertNotIn(secret, self.clean)

    def test_non_phi_and_structure_survive(self):
        msg = HL7Message(self.clean)
        self.assertEqual(msg.message_type, "ADT^A01")
        self.assertEqual(msg.get("PID-8"), "F")
        self.assertEqual(msg.get("PV1-19"), "V0001234")
        self.assertEqual(msg.get("PID-5.2"), "***")


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class ClientTests(unittest.TestCase):
    def test_search_builds_url_and_headers(self):
        client = FHIRClient("https://example.org/fhir", token="abc")
        body = json.dumps({"resourceType": "Bundle", "entry": [{"resource": {"resourceType": "Patient"}}]})
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(body.encode())) as urlopen:
            bundle = client.search("Patient", family="doe", _count="5")
        req = urlopen.call_args[0][0]
        self.assertEqual(req.full_url, "https://example.org/fhir/Patient?family=doe&_count=5")
        self.assertEqual(req.get_header("Authorization"), "Bearer abc")
        self.assertEqual(len(FHIRClient.entries(bundle)), 1)

    def test_errors_surface_operation_outcome(self):
        outcome = {"resourceType": "OperationOutcome", "issue": [{"diagnostics": "Unknown resource"}]}
        err = urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO(json.dumps(outcome).encode()))
        with mock.patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaises(FHIRError) as ctx:
                FHIRClient("https://example.org/fhir").read("Patient", "nope")
        self.assertEqual(ctx.exception.status, 404)
        self.assertIn("Unknown resource", str(ctx.exception))

    def test_transaction_requires_transaction_bundle(self):
        with self.assertRaises(ValueError):
            FHIRClient().transaction({"resourceType": "Bundle", "type": "searchset"})


if __name__ == "__main__":
    unittest.main()
