from __future__ import annotations

import unittest

from enh3bench.benchmark_splitter import deterministic_split


class BenchmarkSplitterTests(unittest.TestCase):
    def test_deterministic_split_keeps_same_paper_in_only_one_split(self) -> None:
        records = [
            {"benchmark_id": "A1", "paper_id": "P1"},
            {"benchmark_id": "A2", "paper_id": "P1"},
            {"benchmark_id": "B1", "paper_id": "P2"},
            {"benchmark_id": "C1", "paper_id": "P3"},
            {"benchmark_id": "D1", "paper_id": "P4"},
        ]
        splits = deterministic_split(records, seed=13)
        memberships: dict[str, set[str]] = {}
        for split_name, rows in splits.items():
            for row in rows:
                memberships.setdefault(row["paper_id"], set()).add(split_name)
        self.assertTrue(all(len(split_names) == 1 for split_names in memberships.values()))

    def test_deterministic_split_is_reproducible_with_seed(self) -> None:
        records = [{"benchmark_id": f"R{i}", "paper_id": f"P{i}"} for i in range(8)]
        first = deterministic_split(records, seed=19)
        second = deterministic_split(records, seed=19)
        self.assertEqual(
            {key: [row["benchmark_id"] for row in rows] for key, rows in first.items()},
            {key: [row["benchmark_id"] for row in rows] for key, rows in second.items()},
        )


if __name__ == "__main__":
    unittest.main()
