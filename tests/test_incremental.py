"""
Unit tests for DevMind git diff change detection and incremental scanner.
"""
import unittest
import os
import tempfile
import pathlib
from devmind.ingestion.git_parser import get_changed_files_git_diff


class TestIncrementalScanner(unittest.TestCase):

    def test_non_git_repo_returns_empty_set(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            changed = get_changed_files_git_diff(tmpdir)
            self.assertIsInstance(changed, set)
            self.assertEqual(len(changed), 0)


if __name__ == "__main__":
    unittest.main()
