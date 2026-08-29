from __future__ import annotations

import socket
import unittest

from acceptance_support import REPOSITORY_ROOT, assert_deterministic_success

FIXTURE_DIRECTORY = REPOSITORY_ROOT / "tests" / "fixtures" / "identity-2"


class IdentityRoundTripAcceptanceTest(unittest.TestCase):
    def test_identity_round_trip_through_public_command(self) -> None:
        run = assert_deterministic_success(self, FIXTURE_DIRECTORY)
        run.canonical_cube.decode("ascii")
        self.assertNotIn(b"\r", run.canonical_cube)
        self.assertTrue(run.canonical_cube.endswith(b"\n"))

        report = run.report
        self.assertEqual(report["case_id"], "identity-2-trilinear")
        self.assertEqual(report["interpolation"], "trilinear")
        self.assertEqual(report["lattice_size"], 2)
        self.assertEqual(report["sample_count"], 8)
        self.assertEqual(report["evaluation_count"], 9)

        report_text = run.report_bytes.decode("ascii")
        self.assertNotIn(run.first_output_directory, report_text)
        self.assertNotIn(run.second_output_directory, report_text)
        self.assertNotIn(socket.gethostname(), report_text)
        self.assertNotIn("Photoshop", report_text)
        self.assertNotIn("Resolve", report_text)
        self.assertNotIn("timestamp", report_text.lower())


if __name__ == "__main__":
    unittest.main()
