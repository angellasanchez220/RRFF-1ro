import unittest

from api.routes.sop import (
    _format_pi_number,
    _load_english_descriptions,
    _next_pi_number,
)


class PiNumberingTests(unittest.TestCase):
    def test_first_default_pi_is_19cl09067(self):
        self.assertEqual(_next_pi_number([]), "19CL09067")

    def test_sequence_continues_after_previous_pi(self):
        existing = ["19CL09064", "19CL09065", "19CL09066"]
        self.assertEqual(_next_pi_number(existing), "19CL09067")

    def test_next_pi_increments_latest_valid_code(self):
        existing = ["19CL09067", "PO-202611-123", "19cl09066", None]
        self.assertEqual(_next_pi_number(existing), "19CL09068")

    def test_pi_number_keeps_five_digit_sequence(self):
        self.assertEqual(_format_pi_number(9068), "19CL09068")

    def test_english_catalog_is_indexed_by_internal_code(self):
        descriptions = _load_english_descriptions()

        self.assertEqual(len(descriptions), 161)
        self.assertEqual(
            descriptions["C9402"],
            "DOUBLE ROLL PACK + P PROFILE",
        )


if __name__ == "__main__":
    unittest.main()
