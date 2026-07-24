"""
Unit tests for DevMind architecture graph builder and digest generator.
"""
import unittest
import os
import tempfile
from devmind.web.app import build_codebase_graph_data


class TestGraphDigest(unittest.TestCase):

    def test_build_codebase_graph_data(self):
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        graph_data = build_codebase_graph_data(project_dir)
        
        self.assertIn("nodes", graph_data)
        self.assertIn("edges", graph_data)
        self.assertIn("stats", graph_data)
        
        stats = graph_data["stats"]
        self.assertGreaterEqual(stats["total_files"], 1)
        self.assertGreaterEqual(stats["total_nodes"], 1)


if __name__ == "__main__":
    unittest.main()
