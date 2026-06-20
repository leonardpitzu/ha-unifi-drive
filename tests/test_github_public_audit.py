"""Tests for public GitHub surface audit helpers."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pytest

from tests.module_stubs import ROOT, load_repo_module


def _load_github_audit_module():
    return load_repo_module(
        "github_public_audit_for_tests",
        ROOT / "scripts" / "audit_github_public_surfaces.py",
    )


def _write_zip(path: Path, members: dict[str, str | bytes]) -> None:
    """Write a small ZIP fixture."""
    with ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)


def test_public_surface_scan_reports_labels_without_content() -> None:
    """Public text scan should report categories without echoing raw content."""
    module = _load_github_audit_module()
    risky = "official " + "Ubi" + "quiti integration with token=secret"

    issues = module._scan_text("release body", risky)

    assert issues == ["release body: possible official vendor integration claim"]
    assert risky not in "\n".join(issues)


def test_public_surface_scan_catches_vendor_copyright() -> None:
    """Public text scan should catch likely vendor copyright headers."""
    module = _load_github_audit_module()
    content = "Copy" + "right 2026 " + "Ubi" + "quiti\n"

    issues = module._scan_text("PR body", content)

    assert issues == ["PR body: possible Ubiquiti copyright header"]


def test_public_surface_scan_catches_jwt_like_token() -> None:
    """Public text scan should catch token shapes."""
    module = _load_github_audit_module()
    token = ".".join(("eyJ" + "a" * 20, "b" * 20, "c" * 20))

    issues = module._scan_text("comment", f"token={token}")

    assert issues == ["comment: possible JWT-like token"]


def test_public_surface_scan_catches_local_identity_markers() -> None:
    """Public text scan should catch local address shapes."""
    module = _load_github_audit_module()

    issues = module._scan_text("comment", "host=" + ".".join(("10", "1", "2", "3")))

    assert issues == ["comment: possible private local IPv4 address"]


def test_public_surface_scan_catches_configured_local_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Public text scan should catch configured local identity markers."""
    module = _load_github_audit_module()
    marker = "private" + "-user"
    monkeypatch.setenv("UNIFI_UNAS_FORBIDDEN_MARKERS", marker)

    issues = module._scan_text("comment", f"user={marker}")

    assert issues == ["comment: possible configured local identifier marker"]


def test_public_surface_audit_matches_zip_assets_case_insensitively() -> None:
    """Release asset ZIP matching should not depend on extension case."""
    module = _load_github_audit_module()

    assert module._is_release_zip_asset_name("unifi_unas.zip")
    assert module._is_release_zip_asset_name("UNIFI_UNAS.ZIP")
    assert module._is_release_zip_asset_name("unifi_unas.Zip")


def test_public_surface_zip_scan_rejects_unsafe_member_paths(tmp_path) -> None:
    """Public release ZIP scans should catch unsafe member paths."""
    module = _load_github_audit_module()
    zip_path = tmp_path / "asset.zip"
    _write_zip(
        zip_path,
        {
            "/unifi_unas/__init__.py": "# package\n",
            "unifi_unas/manifest.json": "{}\n",
        },
    )

    issues = module._scan_zip_asset("release asset", zip_path)

    assert issues == ["release asset: unsafe ZIP member path"]


def test_public_surface_zip_scan_rejects_unsafe_directory_member_paths(
    tmp_path: Path,
) -> None:
    """Directory entries must be validated before they are skipped."""
    module = _load_github_audit_module()
    zip_path = tmp_path / "asset.zip"
    _write_zip(
        zip_path,
        {
            "../escape/": b"",
            "/unifi_unas/": b"",
            "unifi_unas/__init__.py": "# package\n",
        },
    )

    issues = module._scan_zip_asset("release asset", zip_path)

    assert issues == [
        "release asset: unsafe ZIP member path",
        "release asset: unsafe ZIP member path",
    ]


def test_release_asset_download_uses_exact_api_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Release asset downloads should not use glob pattern matching."""
    module = _load_github_audit_module()
    calls: list[list[str]] = []

    def fake_gh_bytes(args: list[str]) -> bytes:
        calls.append(args)
        return b"zip-bytes"

    monkeypatch.setattr(module, "_gh_bytes", fake_gh_bytes)
    destination = tmp_path / "asset.zip"

    module._download_release_asset(
        "https://api.github.com/repos/owner/repo/releases/assets/42",
        destination,
    )

    assert calls == [
        [
            "api",
            "https://api.github.com/repos/owner/repo/releases/assets/42",
            "-H",
            "Accept: application/octet-stream",
        ]
    ]
    assert destination.read_bytes() == b"zip-bytes"


def test_public_surface_audit_scans_release_asset_from_exact_api_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Release ZIP assets should be downloaded by asset URL and scanned locally."""
    module = _load_github_audit_module()
    downloads: list[tuple[str, str]] = []

    def fake_paginated_api_items(path: str) -> list[dict[str, object]]:
        if path == "repos/owner/repo/releases":
            return [
                {
                    "tag_name": "v1.0.0",
                    "name": "Release",
                    "body": None,
                    "assets": [
                        {
                            "name": "unifi_unas[release].ZIP",
                            "url": "https://api.github.com/repos/owner/repo/releases/assets/42",
                        }
                    ],
                }
            ]
        return []

    def fake_download_release_asset(asset_url: str, destination: Path) -> None:
        downloads.append((asset_url, destination.name))
        _write_zip(destination, {"unifi_unas/__init__.py": "# package\n"})

    monkeypatch.setattr(module, "_paginated_api_items", fake_paginated_api_items)
    monkeypatch.setattr(module, "_download_release_asset", fake_download_release_asset)

    counts, issues = module.audit_public_surfaces(
        repo="owner/repo",
        hacs_repo=None,
        hacs_prs=[],
    )

    assert issues == []
    assert counts["release_assets"] == 1
    assert downloads == [
        ("https://api.github.com/repos/owner/repo/releases/assets/42", "asset-1.zip")
    ]


def test_repo_pull_requests_use_paginated_rest_api(monkeypatch: pytest.MonkeyPatch) -> None:
    """PR audits must scan the full paginated public PR history."""
    module = _load_github_audit_module()
    calls: list[list[str]] = []

    def fake_gh_json(args: list[str]) -> object:
        calls.append(args)
        return [{"number": 1, "title": "PR", "body": None}]

    monkeypatch.setattr(module, "_gh_json", fake_gh_json)

    assert module._repo_pull_requests("owner/repo") == [
        {"number": 1, "title": "PR", "body": None}
    ]
    assert calls == [["api", "repos/owner/repo/pulls?state=all&per_page=100&page=1"]]


def test_paginated_api_items_reads_all_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Paginated REST collection output should be fetched page by page."""
    module = _load_github_audit_module()
    first_page = [{"id": index} for index in range(100)]
    second_page = [{"id": 100}]
    calls: list[list[str]] = []

    def fake_gh_json(args: list[str]) -> object:
        calls.append(args)
        return first_page if len(calls) == 1 else second_page

    monkeypatch.setattr(module, "_gh_json", fake_gh_json)

    assert module._paginated_api_items("repos/owner/repo/comments") == [
        *first_page,
        {"id": 100},
    ]
    assert calls == [
        ["api", "repos/owner/repo/comments?per_page=100&page=1"],
        ["api", "repos/owner/repo/comments?per_page=100&page=2"],
    ]


def test_repo_issues_use_paginated_rest_api_and_filter_prs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue audits must scan full history without duplicating PR issues."""
    module = _load_github_audit_module()
    calls: list[list[str]] = []

    def fake_gh_json(args: list[str]) -> object:
        calls.append(args)
        return [
            {"number": 1, "title": "issue", "body": None},
            {"number": 2, "title": "pr", "body": None, "pull_request": {}},
        ]

    monkeypatch.setattr(module, "_gh_json", fake_gh_json)

    assert module._repo_issues("owner/repo") == [{"number": 1, "title": "issue", "body": None}]
    assert calls == [["api", "repos/owner/repo/issues?state=all&per_page=100&page=1"]]
