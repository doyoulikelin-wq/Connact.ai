"""Security-related tests: SSRF protection, input validation, etc."""

from __future__ import annotations

from unittest.mock import patch
import socket
import pytest

from src.web_scraper import _is_safe_url


def _mock_getaddrinfo_public(host, port, *args, **kwargs):
    """Mock DNS resolution that returns a public IP."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))]


class TestSSRFProtection:
    """Verify that _is_safe_url blocks private and internal URLs."""

    @patch('src.web_scraper.socket.getaddrinfo', side_effect=_mock_getaddrinfo_public)
    def test_allows_public_https(self, mock_dns):
        assert _is_safe_url("https://www.google.com/search?q=test") is True

    @patch('src.web_scraper.socket.getaddrinfo', side_effect=_mock_getaddrinfo_public)
    def test_allows_public_http(self, mock_dns):
        assert _is_safe_url("http://example.com") is True

    def test_blocks_localhost(self):
        assert _is_safe_url("http://localhost/admin") is False

    def test_blocks_127(self):
        assert _is_safe_url("http://127.0.0.1:8080/secret") is False

    def test_blocks_ipv6_loopback(self):
        assert _is_safe_url("http://[::1]/admin") is False

    def test_blocks_private_10(self):
        assert _is_safe_url("http://10.0.0.1/internal") is False

    def test_blocks_private_192(self):
        assert _is_safe_url("http://192.168.1.1/router") is False

    def test_blocks_private_172(self):
        assert _is_safe_url("http://172.16.0.1/internal") is False

    def test_blocks_ftp_scheme(self):
        assert _is_safe_url("ftp://example.com/file") is False

    def test_blocks_file_scheme(self):
        assert _is_safe_url("file:///etc/passwd") is False

    def test_blocks_empty(self):
        assert _is_safe_url("") is False

    def test_blocks_no_host(self):
        assert _is_safe_url("http://") is False

    def test_blocks_zero_ip(self):
        assert _is_safe_url("http://0.0.0.0/") is False
