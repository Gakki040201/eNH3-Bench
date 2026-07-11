from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path

from enh3bench.lab_profile import capability_available, default_ustc_linnr_profile, load_lab_profile, migrate_lab_profile


class NOxCapabilitySplitTests(unittest.TestCase):
    def test_liquid_ic_does_not_imply_gas_phase_nox(self) -> None:
        profile = default_ustc_linnr_profile(profile_template="ustc-linnr-realistic")
        self.assertTrue(capability_available(profile, "liquid_nitrate_nitrite_IC_available"))
        self.assertFalse(capability_available(profile, "gas_phase_NOx_quantification_available"))
        self.assertFalse(capability_available(profile, "feed_gas_impurity_testing_available"))

    def test_legacy_nox_field_warns_without_enabling_gas_phase_capability(self) -> None:
        profile = {"analytics": {"NOx_quantification_available": True}}
        migrated, warnings = migrate_lab_profile(profile)
        self.assertTrue(any("ambiguous" in warning for warning in warnings))
        self.assertFalse(capability_available(migrated, "gas_phase_NOx_quantification_available"))

    def test_legacy_liquid_field_migrates_to_liquid_ic(self) -> None:
        profile = {"analytics": {"nitrate_nitrite_quantification_available": True}}
        migrated, warnings = migrate_lab_profile(profile)
        self.assertTrue(capability_available(migrated, "liquid_nitrate_nitrite_IC_available"))
        self.assertTrue(any("liquid_nitrate_nitrite_IC_available" in warning for warning in warnings))

    def test_loaded_legacy_profile_exports_migration_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "legacy.json"
            path.write_text(json.dumps({"analytics": {"NOx_quantification_available": True}}), encoding="utf-8")
            loaded = load_lab_profile(path)
        self.assertTrue(any("ambiguous" in warning for warning in loaded["migration_warnings"]))
        self.assertFalse(capability_available(loaded, "gas_phase_NOx_quantification_available"))


if __name__ == "__main__":
    unittest.main()
