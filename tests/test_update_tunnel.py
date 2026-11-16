from __future__ import annotations

import json

import pytest

import tunnel
import updater


class Response:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size=-1):
        return self.body


class Opener:
    def __init__(self, body: bytes):
        self.body = body
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append((request, timeout))
        return Response(self.body)


def test_version_comparison():
    assert updater.parse_version("v1.2.3") == (1, 2, 3, 1, "")
    assert updater.parse_version("1.2.3-beta") < updater.parse_version("1.2.3")
    assert updater.is_newer("v1.2.4", "1.2.3")
    assert not updater.is_newer("v1.2.3", "1.2.3")
    assert not updater.is_newer("garbage", "1.2.3")


def test_trusted_host_requires_github_domain():
    assert updater._trusted_host("github.com")
    assert updater._trusted_host("objects.githubusercontent.com")
    assert not updater._trusted_host("github.com.example.org")
    assert not updater._trusted_host("notgithub.com")


def test_update_check_parses_release_with_verified_asset():
    release = {
        "tag_name": "v9.9.9",
        "body": "notes",
        "html_url": "https://github.com/owner/repo/releases/tag/v9.9.9",
        "assets": [
            {
                "name": "FNauto.exe",
                "browser_download_url": "https://github.com/owner/repo/releases/download/v9.9.9/FNauto.exe",
                "size": 2000000,
                "digest": "sha256:" + "a" * 64,
            }
        ],
    }
    opener = Opener(json.dumps(release).encode())
    info = updater.AutoUpdater("1.0.0", "owner/repo", opener=opener).check_for_updates()
    assert info is not None
    assert info.latest_version == "9.9.9"
    assert info.sha256 == "a" * 64
    assert info.size == 2000000


def test_update_check_rejects_asset_outside_repository():
    release = {
        "tag_name": "v9.9.9",
        "assets": [
            {
                "name": "FNauto.exe",
                "browser_download_url": "https://example.com/FNauto.exe",
                "digest": "sha256:" + "a" * 64,
            }
        ],
    }
    info = updater.AutoUpdater("1.0.0", "owner/repo", opener=Opener(json.dumps(release).encode())).check_for_updates()
    assert info is None


def test_empty_update_repository_is_a_noop():
    opener = Opener(b"{}")
    info = updater.AutoUpdater("1.0.0", "", opener=opener).check_for_updates()
    assert info is None
    assert opener.requests == []


def test_tunnel_url_extraction():
    assert tunnel.extract_url("INF | https://one-two.trycloudflare.com | ready") == (
        "https://one-two.trycloudflare.com"
    )
    assert tunnel.extract_url("https://example.com") is None
    assert tunnel.extract_url("") is None


def test_tunnel_asset_requires_pinned_release_and_checksum():
    asset = {
        "name": tunnel.ASSET,
        "browser_download_url": tunnel.DOWNLOAD_PREFIX + "v1/" + tunnel.ASSET,
        "digest": "sha256:" + "b" * 64,
        "size": tunnel.MIN_BYTES,
    }
    url, size, digest = tunnel.pick_asset({"assets": [asset]})
    assert url.startswith(tunnel.DOWNLOAD_PREFIX)
    assert size == tunnel.MIN_BYTES
    assert digest == "b" * 64
    with pytest.raises(tunnel.TunnelError):
        tunnel.pick_asset({"assets": [dict(asset, digest="")]})
    with pytest.raises(tunnel.TunnelError):
        tunnel.pick_asset({"assets": [dict(asset, browser_download_url="https://example.com/x.exe")]})


def test_tunnel_bin_dir_uses_local_appdata():
    assert tunnel.bin_dir(r"C:\Users\example\AppData\Local").endswith(r"FNauto\bin")
