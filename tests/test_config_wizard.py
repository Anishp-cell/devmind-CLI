"""
tests/test_config_wizard.py

Unit tests for devmind.config_wizard:
Tests saving/loading configuration, provider validation, and auto-detection.
"""
import os
import json
import pytest
import pathlib
from unittest.mock import patch, MagicMock

from devmind.config_wizard import (
    get_global_config_path,
    load_global_config,
    save_configuration,
    is_any_provider_configured,
    verify_provider_connection
)

class TestConfigWizardStorage:
    def test_global_config_path_resolution(self):
        path = get_global_config_path()
        assert isinstance(path, pathlib.Path)
        assert path.name == "config.json"
        assert path.parent.name == "devmind"

    def test_save_and_load_global_config(self, tmp_path, monkeypatch):
        fake_cfg = tmp_path / "devmind" / "config.json"
        monkeypatch.setattr("devmind.config_wizard.get_global_config_path", lambda: fake_cfg)

        sample_data = {
            "LLM_PROVIDER": "groq",
            "GROQ_API_KEY": "gsk_test123",
            "LLM_MODEL": "groq/llama-3.3-70b-versatile"
        }
        saved_path = save_configuration(sample_data, global_scope=True)
        assert str(fake_cfg) == saved_path
        assert fake_cfg.exists()

        loaded = load_global_config()
        assert loaded["LLM_PROVIDER"] == "groq"
        assert loaded["GROQ_API_KEY"] == "gsk_test123"

    def test_save_local_env_config(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        sample_data = {
            "LLM_PROVIDER": "anthropic",
            "ANTHROPIC_API_KEY": "sk-ant-test456"
        }
        saved_path = save_configuration(sample_data, global_scope=False)
        env_file = tmp_path / ".env"
        assert env_file.exists()
        content = env_file.read_text(encoding="utf-8")
        assert "LLM_PROVIDER=anthropic" in content
        assert "ANTHROPIC_API_KEY=sk-ant-test456" in content

    def test_is_any_provider_configured_with_env(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_live_key")
        assert is_any_provider_configured() is True

    def test_is_any_provider_configured_with_ollama(self, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        assert is_any_provider_configured() is True


class TestVerifyProviderConnection:
    @patch("urllib.request.urlopen")
    def test_groq_verification_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        success, msg = verify_provider_connection("groq", api_key="gsk_valid")
        assert success is True
        assert "verified" in msg.lower()

    @patch("urllib.request.urlopen")
    def test_openai_verification_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        success, msg = verify_provider_connection("openai", api_key="sk_valid")
        assert success is True
        assert "verified" in msg.lower()

    @patch("urllib.request.urlopen")
    def test_ollama_verification_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        success, msg = verify_provider_connection("ollama", base_url="http://localhost:11434")
        assert success is True
        assert "ollama" in msg.lower()

    @patch("urllib.request.urlopen")
    def test_auth_failure_handling(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.groq.com",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=None
        )
        success, msg = verify_provider_connection("groq", api_key="invalid_key")
        assert success is False
        assert "invalid api key" in msg.lower()
