import unittest

from analysis.ebw_track_a_v33_heldout_ttc_prompt_manifest import packet_id


class TestEbwTrackAHeldoutTtcPromptManifest(unittest.TestCase):
    def test_packet_id_is_stable(self):
        self.assertEqual(packet_id("literal_export_path_binding_missing"), "R_HELDOUT_LITERAL_EXPORT_PATH_BINDING_MISSING_V33")


if __name__ == "__main__":
    unittest.main()