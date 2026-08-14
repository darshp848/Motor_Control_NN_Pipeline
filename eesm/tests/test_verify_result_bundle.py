from __future__ import annotations

import hashlib
import json
from pathlib import Path

from eesm.verify_result_bundle import verify_bundle


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_verify_bundle_accepts_matching_repo_files(tmp_path: Path):
    artifact = tmp_path / "artifact.txt"
    manifest = tmp_path / "manifest.json"
    artifact.write_bytes(b"artifact\n")
    manifest.write_bytes(b"{}\n")
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "manifest_sha256": _sha(b"{}\n"),
                "artifacts": [
                    {"path": "artifact.txt", "sha256": _sha(b"artifact\n")}
                ],
            }
        ),
        encoding="utf-8",
    )

    report = verify_bundle(bundle, tmp_path, manifest)

    assert report["status"] == "verified"
    assert {check["status"] for check in report["checks"]} == {"verified"}


def test_verify_bundle_reports_mismatch(tmp_path: Path):
    artifact = tmp_path / "artifact.txt"
    manifest = tmp_path / "manifest.json"
    artifact.write_bytes(b"changed\n")
    manifest.write_bytes(b"{}\n")
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "manifest_sha256": _sha(b"{}\n"),
                "artifacts": [
                    {"path": "artifact.txt", "sha256": _sha(b"original\n")}
                ],
            }
        ),
        encoding="utf-8",
    )

    report = verify_bundle(bundle, tmp_path, manifest)

    assert report["status"] == "failed"
    assert report["checks"][0]["status"] == "mismatch"


def test_verify_bundle_refuses_path_escape(tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    manifest.write_bytes(b"{}\n")
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "manifest_sha256": _sha(b"{}\n"),
                "artifacts": [{"path": "../outside.txt", "sha256": "0" * 64}],
            }
        ),
        encoding="utf-8",
    )

    report = verify_bundle(bundle, tmp_path, manifest)

    assert report["status"] == "failed"
    assert report["checks"][0]["status"] == "refused_outside_repo"
