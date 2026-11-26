import csv
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "scripts"))

from prepare_parts import split_csv
from worker import count_pairs


class PartitionTests(unittest.TestCase):
    def test_quoted_newline_and_pair_totals_survive_split(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.csv"
            rows = [
                ("программист, разработчик", "Python developer", "Python;SQL;Git", "line 1\nline 2"),
                ("программист, разработчик", "Backend Python developer", "Python;SQL", "quoted, comma"),
                ("программист, разработчик", "Java developer", "Java", "not selected"),
                ("программист, разработчик", "FastAPI developer", "Python;FastAPI", "selected"),
            ]
            with source.open("w", encoding="utf-8", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(("role", "name", "key_skills", "description"))
                writer.writerows(rows)
            with source.open("r", encoding="utf-8", newline="") as file:
                expected_total, expected_selected, expected_pairs = count_pairs(file)
            paths, counts = split_csv(source, Path(temporary), 3)
            self.assertEqual(counts, [2, 1, 1])
            total = selected = 0
            pairs = Counter()
            for path in paths:
                with path.open("r", encoding="utf-8", newline="") as file:
                    part_total, part_selected, part_pairs = count_pairs(file)
                total += part_total
                selected += part_selected
                pairs.update(part_pairs)
            self.assertEqual((total, selected, pairs),
                             (expected_total, expected_selected, expected_pairs))


if __name__ == "__main__":
    unittest.main()
