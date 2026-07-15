from __future__ import annotations

import unittest
from pathlib import Path


class PackagingConfigurationTests(unittest.TestCase):
    def test_setuptools_discovery_and_ci_health_gate_configuration(self) -> None:
        pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
        workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn('license = "MIT"', pyproject)
        self.assertIn("[tool.setuptools.packages.find]", pyproject)
        self.assertIn('include = ["enh3bench*"]', pyproject)
        self.assertIn("namespaces = false", pyproject)
        self.assertIn("fail-fast: false", workflow)
        self.assertIn("python -m pip check", workflow)
        self.assertNotIn("contents: write", workflow)


if __name__ == "__main__":
    unittest.main()
