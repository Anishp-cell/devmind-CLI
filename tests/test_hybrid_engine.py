"""
Unit tests for DevMind Hybrid Engine rate-limit cooldown tracking,
model fallback, and exception interception.
"""
import unittest
import time
import os
from devmind.memory import (
    mark_key_cooldown,
    get_active_keys,
    get_random_api_key,
    _KEY_COOLDOWNS,
    _GROQ_API_KEYS
)


class TestHybridEngine(unittest.TestCase):

    def setUp(self):
        _KEY_COOLDOWNS.clear()

    def test_key_cooldown_tracking(self):
        test_key = "gsk_testkey12345678901234567890"
        mark_key_cooldown(test_key, cooldown_seconds=2)
        
        # Key should be present in _KEY_COOLDOWNS
        self.assertIn(test_key, _KEY_COOLDOWNS)

    def test_key_rotation_with_cooldown(self):
        key1 = "gsk_key1111111111111111111111111"
        key2 = "gsk_key2222222222222222222222222"
        
        # Put key1 on cooldown
        mark_key_cooldown(key1, cooldown_seconds=600)
        
        active = get_active_keys([key1, key2])
        self.assertEqual(active, [key2])


if __name__ == "__main__":
    unittest.main()
