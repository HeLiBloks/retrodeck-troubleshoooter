"""The controller id derivation, pinned to a pad that was measured by hand."""

import unittest

from support import ProbeTestCase

from rdtroubleshoot.inputs import _sdl_guid_bytes, controller_guid


class ControllerGuidTest(ProbeTestCase):
    def test_dualshock4_matches_the_hand_derivation(self):
        """The DS4 on this machine, derived from sysfs and confirmed against Ryujinx.

        bustype 0003, vendor 054c, product 05c4, version 8111. Anything that changes
        the byte order changes this string, which is the whole point of pinning it.
        """
        self.assertEqual(
            controller_guid(0x0003, 0x054C, 0x05C4, 0x8111),
            "0-00000003-054c-0000-c405-000011810000",
        )

    def test_the_sdl_layout_is_four_le_shorts_each_zero_padded(self):
        self.assertEqual(
            _sdl_guid_bytes(0x0003, 0x054C, 0x05C4, 0x8111).hex(),
            "030000004c050000c405000011810000",
        )

    def test_vendor_is_byte_swapped_in_field2_and_raw_in_field4(self):
        """.NET reads the first three fields little-endian and the last eight raw.

        This asymmetry is the thing that makes the id impossible to guess, so it is
        worth asserting directly rather than only through the DS4 case.
        """
        guid = controller_guid(0x0003, 0x054C, 0x05C4, 0x8111)
        _, field1, field2, field3, field4, field5 = guid.split("-")
        self.assertEqual(field2, "054c", "vendor read little-endian from bytes 4-5")
        self.assertEqual(field3, "0000")
        self.assertEqual(field4 + field5, "c405000011810000", "product/version raw from bytes 8-15")

    def test_player_index_is_the_leading_field(self):
        self.assertTrue(controller_guid(3, 0x054C, 0x05C4, 0x8111, player_index=2).startswith("2-"))

    def test_an_xbox_pad_derives_the_id_the_troubleshooting_notes_record(self):
        """The X360 profile already in Config.json, as a second independent case."""
        self.assertEqual(
            controller_guid(0x0003, 0x045E, 0x0000, 0x0000).split("-", 1)[1][:14],
            "00000003-045e-",
        )


if __name__ == "__main__":
    unittest.main()


class InputSeverityTest(ProbeTestCase):
    """An unmatched pad is only the black-screen case when nothing else is bound.

    Reporting FAIL either way overstates the case where a keyboard is bound, and — worse —
    cites the black-screen symptom for a situation that will not produce it. The distinction
    is what makes the level worth reading.
    """

    def test_the_version_field_varies_for_one_pad_model(self):
        """So the id must be derived from the CONNECTED device, never from the model.

        A DualShock 4 on this machine has been seen reporting version 0x8111 and 0x6801,
        giving different ids for the same physical model.
        """
        a = controller_guid(0x0003, 0x054C, 0x05C4, 0x8111)
        b = controller_guid(0x0003, 0x054C, 0x05C4, 0x6801)
        self.assertNotEqual(a, b)
        self.assertTrue(a.startswith("0-00000003-054c-0000-c405-"))
        self.assertTrue(b.startswith("0-00000003-054c-0000-c405-"))

    def test_an_xbox_pad_derives_the_id_that_was_applied(self):
        """bustype 0003, vendor 045e, product 02a1, version 0330 — read from sysfs."""
        self.assertEqual(
            controller_guid(0x0003, 0x045E, 0x02A1, 0x0330),
            "0-00000003-045e-0000-a102-000030030000",
        )
