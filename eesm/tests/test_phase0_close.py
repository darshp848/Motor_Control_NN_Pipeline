"""Write-once guard for the frozen Phase 0 close."""

from __future__ import annotations

import importlib.util
import os
import stat
from pathlib import Path

import pytest

_EESM = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    spec = importlib.util.spec_from_file_location(
        "run_phase0_close", os.path.join(_EESM, "run_phase0_close.py")
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_default_out_is_not_the_frozen_tree():
    runner = _load()
    default = os.path.normcase(os.path.abspath(runner.default_close_out()))
    frozen = os.path.normcase(os.path.abspath(runner.FROZEN_CLOSE))
    assert default != frozen
    assert os.path.basename(default).startswith("phase0_close_")
    assert os.path.basename(default) != "phase0_close_20260813"


def test_refuse_frozen_path_even_when_empty(tmp_path):
    runner = _load()
    frozen = tmp_path / "phase0_close_20260813"
    frozen.mkdir()
    msg = runner.refuse_existing_close(frozen, frozen)
    assert msg is not None
    assert "immutable" in msg


def test_refuse_when_result_bundle_exists(tmp_path):
    runner = _load()
    dest = tmp_path / "new_close"
    dest.mkdir()
    (dest / "result_bundle.json").write_text("{}\n", encoding="utf-8")
    frozen = tmp_path / "phase0_close_20260813"
    frozen.mkdir()
    msg = runner.refuse_existing_close(dest, frozen)
    assert msg is not None
    assert "result_bundle.json" in msg


def test_allow_fresh_directory(tmp_path):
    runner = _load()
    dest = tmp_path / "new_close"
    dest.mkdir()
    frozen = tmp_path / "phase0_close_20260813"
    frozen.mkdir()
    assert runner.refuse_existing_close(dest, frozen) is None


def test_protect_marks_bundle_read_only(tmp_path):
    runner = _load()
    bundle = tmp_path / "result_bundle.json"
    close = tmp_path / "phase0_close.json"
    bundle.write_text("{}\n", encoding="utf-8")
    close.write_text("{}\n", encoding="utf-8")
    try:
        marked = runner.protect_frozen_close(tmp_path)
        assert bundle in marked
        assert close in marked
        assert not (bundle.stat().st_mode & stat.S_IWUSR)
        with pytest.raises(PermissionError):
            bundle.write_text("overwrite\n", encoding="utf-8")
    finally:
        for path in (bundle, close):
            if path.exists():
                path.chmod(path.stat().st_mode | stat.S_IWUSR)


def test_main_refuses_frozen_out_before_loading_inputs():
    runner = _load()
    assert runner.main(["--out", runner.FROZEN_CLOSE]) == 2
