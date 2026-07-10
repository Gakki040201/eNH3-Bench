from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from enh3bench.lab_profile import (
    default_ustc_linnr_profile,
    feasible_controls,
    infeasible_controls,
    load_lab_profile,
    missing_capabilities_for_controls,
    save_lab_profile,
    validate_lab_profile,
)


class LabProfileTests(unittest.TestCase):
    def test_default_lab_profile_validates(self) -> None:
        valid, errors = validate_lab_profile(default_ustc_linnr_profile())
        self.assertTrue(valid)
        self.assertEqual(errors, [])

    def test_missing_critical_fields_are_reported(self) -> None:
        profile = default_ustc_linnr_profile()
        del profile["reactor_capabilities"]["can_do_flow_cell"]
        valid, errors = validate_lab_profile(profile)
        self.assertFalse(valid)
        self.assertIn("missing reactor_capabilities.can_do_flow_cell", errors)

    def test_yaml_path_uses_json_fallback_without_pyyaml(self) -> None:
        profile = default_ustc_linnr_profile()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profile.yaml"
            with patch("enh3bench.lab_profile._yaml_module", return_value=None):
                save_lab_profile(profile, path)
                loaded = load_lab_profile(path)
        self.assertEqual(loaded["profile_id"], profile["profile_id"])

    def test_missing_15n_capability_marks_control_infeasible(self) -> None:
        profile = default_ustc_linnr_profile()
        controls = ["15N2 isotope validation", "primary body text pairing"]
        self.assertIn("15N2 isotope validation", infeasible_controls(profile, controls))
        self.assertIn("primary body text pairing", feasible_controls(profile, controls))
        self.assertIn("can_do_15N_control", missing_capabilities_for_controls(profile, controls))


if __name__ == "__main__":
    unittest.main()
