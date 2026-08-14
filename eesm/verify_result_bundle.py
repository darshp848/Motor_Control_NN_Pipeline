#!/usr/bin/env python
"""Verify every file hash referenced by an EESM result bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BUNDLE = REPO_ROOT / "out" / "eesm" / "phase0_close_20260813" / "result_bundle.json"
DEFAULT_MANIFEST = REPO_ROOT / "eesm" / "configs" / "eesm_experiment_manifest.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _inside_repo(path: Path, repo_root: Path) -> bool:
    try:
        path.relative_to(repo_root)
    except ValueError:
        return False
    return True


def verify_bundle(
    bundle_path: Path,
    repo_root: Path = REPO_ROOT,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    bundle_path = bundle_path.resolve()
    manifest_path = manifest_path.resolve()
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    checks: list[dict[str, Any]] = []

    for artifact in bundle.get("artifacts", []):
        relative = Path(str(artifact["path"]))
        candidate = (repo_root / relative).resolve()
        expected = str(artifact["sha256"]).lower()
        entry: dict[str, Any] = {
            "path": relative.as_posix(),
            "expected_sha256": expected,
        }
        if not _inside_repo(candidate, repo_root):
            entry.update(status="refused_outside_repo", actual_sha256=None)
        elif not candidate.is_file():
            entry.update(status="missing", actual_sha256=None)
        else:
            actual = sha256_file(candidate)
            entry.update(
                status="verified" if actual == expected else "mismatch",
                actual_sha256=actual,
            )
        checks.append(entry)

    expected_manifest = str(bundle.get("manifest_sha256", "")).lower()
    if manifest_path.is_file() and _inside_repo(manifest_path, repo_root):
        actual_manifest = sha256_file(manifest_path)
        manifest_status = "verified" if actual_manifest == expected_manifest else "mismatch"
    else:
        actual_manifest = None
        manifest_status = "missing"
    checks.append(
        {
            "path": manifest_path.relative_to(repo_root).as_posix()
            if _inside_repo(manifest_path, repo_root)
            else str(manifest_path),
            "expected_sha256": expected_manifest,
            "actual_sha256": actual_manifest,
            "status": manifest_status,
        }
    )

    verified = bool(checks) and all(check["status"] == "verified" for check in checks)
    return {
        "bundle": str(bundle_path),
        "checks": checks,
        "status": "verified" if verified else "failed",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)
    report = verify_bundle(args.bundle, args.repo_root, args.manifest)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
