import unittest
from pathlib import Path

from hl7fhir.mapping import (MappingError, adt_to_bundle, adt_to_patient,
                             hl7_date, hl7_datetime)
from hl7fhir.parser import HL7Message

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def load(name):
    return HL7Message((SAMPLES / name).read_text())


class DateTests(unittest.TestCase):
    def test_dates(self):
        self.assertEqual(hl7_date("19850214"), "1985-02-14")
        self.assertEqual(hl7_date("198502"), "1985-02")
        self.assertIsNone(hl7_date("not a date"))

    def test_datetime_keeps_timezone(self):
        self.assertEqual(hl7_datetime("20261117080000-0700"), "2026-11-17T08:00:00-07:00")

    def test_datetime_without_timezone_uses_default(self):
        self.assertEqual(hl7_datetime("202611170800", "-07:00"), "2026-11-17T08:00:00-07:00")


class PatientTests(unittest.TestCase):
    def setUp(self):
        self.patient = adt_to_patient(load("adt_a01.hl7"))

    def test_demographics(self):
        self.assertEqual(self.patient["name"][0]["family"], "Doe")
        self.assertEqual(self.patient["name"][0]["given"], ["Jane", "Q"])
        self.assertEqual(self.patient["gender"], "female")
        self.assertEqual(self.patient["birthDate"], "1985-02-14")
        self.assertEqual(self.patient["address"][0]["city"], "DENVER")
        self.assertEqual(self.patient["telecom"][0]["value"], "(303) 555-0123")

    def test_mrn_is_kept_and_ssn_is_dropped(self):
        values = [i["value"] for i in self.patient["identifier"]]
        self.assertEqual(values, ["MRN123456"])


class BundleTests(unittest.TestCase):
    def test_admit_creates_in_progress_inpatient_encounter(self):
        bundle = adt_to_bundle(load("adt_a01.hl7"))
        patient_entry, encounter_entry = bundle["entry"]
        encounter = encounter_entry["resource"]
        self.assertEqual(bundle["type"], "transaction")
        self.assertEqual(encounter["status"], "in-progress")
        self.assertEqual(encounter["class"]["code"], "IMP")
        self.assertEqual(encounter["subject"]["reference"], patient_entry["fullUrl"])
        self.assertEqual(encounter["period"]["start"], "2026-11-17T08:00:00-07:00")

    def test_patient_create_is_conditional_on_mrn(self):
        bundle = adt_to_bundle(load("adt_a01.hl7"))
        request = bundle["entry"][0]["request"]
        self.assertEqual(request["ifNoneExist"], "identifier=urn:id:MERCY_HOSP|MRN123456")

    def test_discharge_finishes_encounter(self):
        encounter = adt_to_bundle(load("adt_a03.hl7"))["entry"][1]["resource"]
        self.assertEqual(encounter["status"], "finished")
        self.assertEqual(encounter["period"]["end"], "2026-11-20T14:00:00-07:00")

    def test_non_adt_messages_are_rejected(self):
        oru = HL7Message("MSH|^~\\&|LAB|X|Y|Z|20260101||ORU^R01|1|P|2.5.1\rPID|1||1")
        with self.assertRaises(MappingError):
            adt_to_bundle(oru)


if __name__ == "__main__":
    unittest.main()
