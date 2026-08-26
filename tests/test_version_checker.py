"""
tests/test_version_checker.py

Unit tests for devmind.version_checker:
Tests version comparison, caching mechanism, environment variable opt-out,
and banner rendering.
"""

import pytest
import os
import json
import time
import pathlib

from devmind.version_checker import (
    parse_version_tuple,
    is_version_newer,
    get_cached_latest_version,
    check_for_updates,
    show_update_notification,
    get_cache_file_path
)


class TestVersionComparison:
    def test_parse_version_tuple(self):
        assert parse_version_tuple("0.3.7") == (0, 3, 7)
        assert parse_version_tuple("1.0.0") == (1, 0, 0)
        assert parse_version_tuple("v2.1.4") == (2, 1, 4)

    def test_is_version_newer(self):
        assert is_version_newer("1.0.0", "0.3.7") is True
        assert is_version_newer("0.3.8", "0.3.7") is True
        assert is_version_newer("0.3.7", "0.3.7") is False
        assert is_version_newer("0.3.6", "0.3.7") is False
        assert is_version_newer("0.2.99", "0.3.0") is False


class TestVersionCache:
    def test_reads_valid_cache(self, monkeypatch, tmp_path):
        fake_cache = tmp_path / "version_cache.json"
        fake_cache.write_text(json.dumps({
            "last_checked": time.time(),
            "latest_version": "1.5.0"
        }))

        monkeypatch.setattr("devmind.version_checker.get_cache_file_path", lambda: fake_cache)
        assert get_cached_latest_version() == "1.5.0"

    def test_ignores_expired_cache(self, monkeypatch, tmp_path):
        fake_cache = tmp_path / "version_cache.json"
        fake_cache.write_text(json.dumps({
            "last_checked": time.time() - 90000,  # > 24 hours ago
            "latest_version": "1.5.0"
        }))

        monkeypatch.setattr("devmind.version_checker.get_cache_file_path", lambda: fake_cache)
        assert get_cached_latest_version() is None


class TestOptOutAndNotifications:
    def test_opt_out_with_env_var(self, monkeypatch):
        monkeypatch.setenv("DEVMIND_NO_UPDATE_CHECK", "1")
        assert check_for_updates() is None

    def test_opt_out_in_ci(self, monkeypatch):
        monkeypatch.setenv("CI", "true")
        assert check_for_updates() is None

    def test_notification_renders_without_crash(self, monkeypatch):
        monkeypatch.setattr("devmind.version_checker.check_for_updates", lambda: "1.0.0")
        # Should execute cleanly without raising any exceptions
        show_update_notification()
