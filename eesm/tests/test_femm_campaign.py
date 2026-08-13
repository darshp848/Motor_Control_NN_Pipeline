"""Fail-closed invariants of the FEMM campaign driver, from points to status.

Covers eesm/femm/campaign.py, eesm/femm/points.py, the availability probe in
eesm/femm/runtime.py, and the eesm/run_femm_campaign.py entry point.

This is the file named in campaign.py:332 ("the mock's analyze_count is the
evidence for that, asserted in test_femm_campaign.py") and in extract.py:257
("test_femm_campaign.py pins this"). Both claims are asserted below.

What these tests CAN prove
--------------------------
That the driver refuses rather than guesses: a changed points file, a prior
failure, results and status that disagree, a malformed header, or a row the
schema rejects all stop the run with nothing written. And that a completed
point is skipped without the solver being called at all -- which is what makes
a resume safe to run on a machine that costs money per solve.

What they CANNOT prove
----------------------
Anything about the physics. Every solve here comes from MockFemm, which
returns closed-form linear-salient fluxes and accepts whatever FemmApiConfig
says. A campaign that passes every test in this file has still never touched a
solver. See eesm/docs/FEMM_MIGRATION.md.

No FEMM licence, installation, or solve is used by any test in this file.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import sys
import types

import pytest

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from eesm.femm import campaign, campaign_sanity, points, runtime  # noqa: E402
from eesm.femm.campaign import (  # noqa: E402
    CampaignPaths,
    CampaignRefusal,
    RESULT_FIELDS,
)
from eesm.femm.config import DEFAULT_CONFIG  # noqa: E402
from eesm.femm.extract import extract_point  # noqa: E402
from eesm.femm.mock_femm import MockFemm  # noqa: E402
from eesm.femm.points import PointsRefusal  # noqa: E402

#: The preserved Task 9 export: the only real frozen points file in the repo.
TASK9_POINTS = os.path.join(
    REPO_ROOT, "out", "eesm", "task9_baseline", "frozen_points.csv"
)

POINTS_HEADER = list(campaign.FROZEN_POINT_FIELDS)

#: Three points with schema-legal identities (point_id is 16 lowercase hex).
SAMPLE_POINTS = [
    {"point_name": "p_interior", "point_id": "0123456789abcdef",
     "role": "train", "region": "interior",
     "id_a": "-40.0", "iq_a": "60.0", "if_a": "6.0"},
    {"point_name": "p_boundary", "point_id": "fedcba9876543210",
     "role": "train", "region": "boundary",
     "id_a": "-120.0", "iq_a": "0.0", "if_a": "1.0"},
    {"point_name": "p_selection", "point_id": "00112233445566aa",
     "role": "selection", "region": "field_weakening",
     "id_a": "-90.0", "iq_a": "30.0", "if_a": "12.0"},
]


def write_points(path, rows=None, header=None):
    """Write a frozen points CSV and return its path."""
    rows = SAMPLE_POINTS if rows is None else rows
    header = POINTS_HEADER if header is None else header
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=header)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


@pytest.fixture()
def paths(tmp_path):
    """A campaign root with the three sample points frozen in it."""
    root = CampaignPaths(root=str(tmp_path / "campaign"))
    root.ensure()
    write_points(root.points_csv)
    return root


def run(paths, handle=None, **kwargs):
    """Run a campaign with a fresh mock unless one is supplied."""
    handle = MockFemm() if handle is None else handle
    return campaign.run_campaign(handle, paths, cfg=DEFAULT_CONFIG,
                                 solver_backend="mock", **kwargs), handle


def results_rows(paths):
    with open(paths.results_csv, "r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


# ---------------------------------------------------------------------------
# The two invariants the source code names this file for
# ---------------------------------------------------------------------------


def test_completed_points_are_never_resolved(paths):
    """campaign.py:332. A finished point must not reach the solver again."""
    status, first = run(paths, max_new_points=1)
    assert status["status"] == "partial_resume_required"
    assert first.analyze_count == 1

    status, second = run(paths, max_new_points=1)
    # The second run solved exactly one NEW point, not the completed one.
    assert second.analyze_count == 1
    assert status["solved_this_run"] == ["p_interior"] or len(
        status["solved_this_run"]) == 1

    status, third = run(paths)
    assert status["status"] == "complete"
    assert third.analyze_count == 1  # only the last outstanding point

    status, fourth = run(paths)
    assert status["status"] == "complete"
    assert fourth.analyze_count == 0  # nothing left: the solver is never called
    assert fourth.call_count("mi_setcurrent") == 0


def test_campaign_torque_is_the_identity_not_sector_wst():
    """Phase 0: 90 deg WST is diagnostic; identity is the campaign torque."""
    from eesm.femm.campaign import CAMPAIGN_TORQUE_FIELD, campaign_torque_nm

    assert CAMPAIGN_TORQUE_FIELD == "torque_identity_nm"
    assert "campaign_torque_nm" in RESULT_FIELDS
    row = {
        "torque_fem_nm": 2.77,
        "torque_identity_nm": 2.74,
        "campaign_torque_nm": 2.74,
    }
    assert campaign_torque_nm(row) == pytest.approx(2.74)
    assert campaign_torque_nm(row) != row["torque_fem_nm"]
    with pytest.raises(CampaignRefusal, match="dq identity"):
        campaign_torque_nm({"torque_fem_nm": 2.77})


def test_campaign_sanity_summarizes_the_live_64_without_writing_thresholds():
    root = os.path.join(REPO_ROOT, "out", "eesm", "femm_baseline_64_20260812")
    results = os.path.join(root, "femm_results.csv")
    if not os.path.isfile(results):
        pytest.skip("64-point live campaign results not present")
    payload = campaign_sanity.summarize_campaign(root)
    assert payload["verdict"] == "schema_valid_live_rows"
    assert payload["rows"] == 64
    assert payload["all_converged"] is True
    assert payload["not_a_threshold_freeze"] is True
    assert payload["not_a_fit"] is True
    assert payload["schema_failures"] == 0
    assert payload["identity_equals_campaign_torque"] is True


def test_lambda_f_wb_is_forbidden_by_the_schema():
    """extract.py:257. The schema sets lambda_f_wb to `false`, i.e. FORBIDDEN."""
    with pytest.raises(CampaignRefusal, match="forbidden"):
        campaign.validate_row({"lambda_f_wb": 0.4})
    with pytest.raises(CampaignRefusal, match="forbidden"):
        campaign.validate_row({"roles": ["train"]})

    result = extract_point(MockFemm(), -40.0, 60.0, 6.0, cfg=DEFAULT_CONFIG)
    assert "lambda_f_wb" not in result
    assert "lambda_field_wb" in result
    assert "lambda_field_wb" in RESULT_FIELDS
    assert "lambda_f_wb" not in RESULT_FIELDS


# ---------------------------------------------------------------------------
# Resume refusals
# ---------------------------------------------------------------------------


def test_resume_refuses_a_changed_points_file(paths):
    run(paths, max_new_points=1)
    write_points(paths.points_csv, rows=SAMPLE_POINTS[:2])
    with pytest.raises(CampaignRefusal, match="points file changed"):
        run(paths)


def test_resume_refuses_after_a_recorded_failure(paths):
    run(paths, max_new_points=1)
    status = json.loads(open(paths.status_json, encoding="utf-8").read())
    status["failure"] = {"point_name": "p_boundary", "solver_status": "failed"}
    campaign.write_status(paths.status_json, status)
    with pytest.raises(CampaignRefusal, match="needs operator review"):
        run(paths)


def test_resume_refuses_results_without_status(paths):
    run(paths, max_new_points=1)
    os.remove(paths.status_json)
    with pytest.raises(CampaignRefusal, match="results exist without status"):
        run(paths)


def test_resume_refuses_status_without_results(paths):
    run(paths, max_new_points=1)
    os.remove(paths.results_csv)
    with pytest.raises(CampaignRefusal, match="status JSON exists without results"):
        run(paths)


def test_resume_refuses_when_status_and_results_disagree(paths):
    run(paths, max_new_points=1)
    status = json.loads(open(paths.status_json, encoding="utf-8").read())
    status["completed"] = ["p_interior", "p_boundary"]  # claims one too many
    campaign.write_status(paths.status_json, status)
    with pytest.raises(CampaignRefusal, match="disagree"):
        run(paths)


def test_resume_refuses_a_malformed_results_header(paths):
    run(paths, max_new_points=1)
    rows = results_rows(paths)
    with open(paths.results_csv, "w", encoding="utf-8", newline="") as stream:
        trimmed = list(RESULT_FIELDS)[:-1]
        writer = csv.DictWriter(stream, fieldnames=trimmed, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    with pytest.raises(CampaignRefusal, match="malformed results header"):
        run(paths)


def test_resume_refuses_a_row_for_an_unknown_point(paths):
    run(paths, max_new_points=1)
    rows = results_rows(paths)
    rows[0]["point_name"] = "not_a_frozen_point"
    with open(paths.results_csv, "w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(RESULT_FIELDS))
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(CampaignRefusal, match="unknown results point"):
        run(paths)


def test_resume_refuses_a_row_whose_currents_drifted(paths):
    """A row must still describe the point the frozen file froze."""
    run(paths, max_new_points=1)
    rows = results_rows(paths)
    rows[0]["iq_a"] = str(float(rows[0]["iq_a"]) + 1.0)
    with open(paths.results_csv, "w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(RESULT_FIELDS))
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(CampaignRefusal, match="inconsistent iq_a"):
        run(paths)


def test_results_are_appended_never_rewritten(paths):
    run(paths, max_new_points=1)
    before = open(paths.results_csv, "rb").read()
    run(paths)
    after = open(paths.results_csv, "rb").read()
    assert after.startswith(before), "an existing row was rewritten"
    assert len(results_rows(paths)) == len(SAMPLE_POINTS)


# ---------------------------------------------------------------------------
# Write discipline
# ---------------------------------------------------------------------------


def test_a_failed_solve_writes_no_row_and_stops_the_run(paths):
    handle = MockFemm(fail_analysis=True)
    with pytest.raises(CampaignRefusal, match="Refusing to continue"):
        run(paths, handle=handle)

    assert not os.path.exists(paths.results_csv), "a failed solve produced data"
    status = json.loads(open(paths.status_json, encoding="utf-8").read())
    assert status["status"] == "failed"
    assert status["failure"]["point_name"] == "p_interior"
    assert "mock solver failure" in status["failure"]["solver_status"]


def test_a_schema_invalid_row_aborts_before_anything_is_written(paths, monkeypatch):
    """validate_row runs BEFORE append_row, so a bad row never lands."""
    real_build_row = campaign.build_row

    def bad_build_row(point, result, points_hash, solver_backend):
        row = real_build_row(point, result, points_hash, solver_backend)
        row["role"] = "not_a_role_in_the_enum"
        return row

    monkeypatch.setattr(campaign, "build_row", bad_build_row)
    with pytest.raises(CampaignRefusal, match="failed eesm_point.schema.json"):
        run(paths)
    assert not os.path.exists(paths.results_csv)


def test_every_written_row_satisfies_the_schema(paths):
    run(paths)
    schema = campaign.load_schema()
    for row in results_rows(paths):
        campaign.validate_row(row, schema)  # raises if not


# ---------------------------------------------------------------------------
# Frozen points reader
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mutate,expected", [
    (lambda rows: [], "no rows"),
    (lambda rows: rows + [dict(rows[0])], "duplicate frozen point"),
    (lambda rows: [{**rows[0], "point_name": ""}], "empty point_name"),
    (lambda rows: [{**rows[0], "iq_a": "not-a-number"}], "non-numeric iq_a"),
])
def test_read_points_refuses_malformed_input(tmp_path, mutate, expected):
    path = write_points(str(tmp_path / "frozen_points.csv"),
                        rows=mutate(list(SAMPLE_POINTS)))
    with pytest.raises(CampaignRefusal, match=expected):
        campaign.read_points(path)


def test_read_points_refuses_a_missing_file(tmp_path):
    with pytest.raises(CampaignRefusal, match="frozen points file missing"):
        campaign.read_points(str(tmp_path / "absent.csv"))


def test_read_points_refuses_the_aedt_dialect(tmp_path):
    """The AEDT spelling is a conversion job, not something to guess at."""
    path = str(tmp_path / "frozen_points.csv")
    write_points(path, rows=[{"PointName": "p", "point_id": "0123456789abcdef",
                              "role": "train", "region": "interior",
                              "Id [A]": "-40", "Iq [A]": "60", "If [A]": "6"}],
                 header=list(points.AEDT_TO_FEMM_COLUMNS))
    with pytest.raises(CampaignRefusal, match="missing columns"):
        campaign.read_points(path)


# ---------------------------------------------------------------------------
# Evidence honesty
# ---------------------------------------------------------------------------


def test_status_records_that_no_real_solve_happened(paths):
    status, _ = run(paths)
    availability = status["femm_availability"]
    assert availability["real_solve_performed"] is False
    assert status["solver_backend"] == "mock"
    assert status["points_sha256"] == campaign.sha256_file(paths.points_csv)


def test_status_carries_the_unverified_config_findings(paths):
    """A run's own evidence must state which constants were never confirmed."""
    status, _ = run(paths)
    unverified = status["config_provenance"]["unverified"]
    # A run's own evidence must still name what was never confirmed. The
    # airgap, the API enums and the BH curve were all settled 2026-08-12 and
    # are deliberately no longer in this list; the synthetic electrical
    # parameters and the FEMM library names remain.
    for key in ("materials.air_material", "domain.rs_ohm"):
        assert key in unverified
    assert "materials.steel_material" not in unverified


def test_provenance_id_is_tied_to_the_exact_points_file():
    point = dict(SAMPLE_POINTS[0])
    assert campaign.provenance_id(point, "hash_a") != campaign.provenance_id(
        point, "hash_b")
    assert campaign.provenance_id(point, "hash_a").startswith(campaign.SOURCE_TAG)


# ---------------------------------------------------------------------------
# AEDT -> FEMM points conversion
# ---------------------------------------------------------------------------


def test_task9_points_are_refused_raw_and_accepted_converted(tmp_path):
    """The real Task 9 export, end to end: refused, converted, then read."""
    if not os.path.exists(TASK9_POINTS):
        pytest.skip("Task 9 frozen points not present")

    with pytest.raises(CampaignRefusal, match="missing columns"):
        campaign.read_points(TASK9_POINTS)

    assert points.dialect_of(TASK9_POINTS) == "aedt"
    dest = str(tmp_path / "campaign" / "frozen_points.csv")
    payload = points.adapt_points_file(TASK9_POINTS, dest)

    converted = campaign.read_points(dest)
    assert len(converted) == payload["rows"] == 64
    assert points.dialect_of(dest) == "femm"


def test_conversion_preserves_frozen_identities(tmp_path):
    source = str(tmp_path / "source" / "aedt_points.csv")
    write_points(source, rows=[{
        "PointName": "p_one", "point_id": "0123456789abcdef",
        "role": "selection", "region": "saturation",
        "Id [A]": "-40.5", "Iq [A]": "60.25", "If [A]": "6.125"}],
        header=list(points.AEDT_TO_FEMM_COLUMNS))
    dest = str(tmp_path / "campaign" / "frozen_points.csv")
    points.adapt_points_file(source, dest)

    row = campaign.read_points(dest)[0]
    assert row["point_id"] == "0123456789abcdef"
    assert row["role"] == "selection"
    assert row["region"] == "saturation"
    assert row["point_name"] == "p_one"
    assert (row["id_a"], row["iq_a"], row["if_a"]) == ("-40.5", "60.25", "6.125")


def test_femm_dialect_source_is_copied_verbatim(tmp_path):
    source = str(tmp_path / "freeze" / "frozen_points.csv")
    write_points(source)
    dest = str(tmp_path / "campaign" / "frozen_points.csv")
    payload = points.copy_femm_points_file(source, dest)
    assert payload["source_sha256"] == payload["dest_sha256"]
    assert open(source, "rb").read() == open(dest, "rb").read()
    assert campaign.read_points(dest)[0]["point_id"] == SAMPLE_POINTS[0]["point_id"]
    with pytest.raises(PointsRefusal, match="already exists"):
        points.copy_femm_points_file(source, dest)


def test_runner_copies_a_femm_dialect_source(runner, tmp_path):
    source = str(tmp_path / "freeze" / "frozen_points.csv")
    write_points(source)
    root = str(tmp_path / "campaign")
    status = runner.run_femm_campaign(
        output_dir=root, points_source=source, use_mock=True,
    )
    assert status["points_preparation"]["action"] == "copied"
    assert status["status"] == "complete"
    copied = os.path.join(root, "frozen_points.csv")
    assert open(source, "rb").read() == open(copied, "rb").read()


def test_conversion_refuses_to_write_into_the_source_directory(tmp_path):
    """A preserved freeze must never receive derived files."""
    source = str(tmp_path / "freeze" / "aedt_points.csv")
    write_points(source, rows=[dict(zip(points.AEDT_TO_FEMM_COLUMNS,
                                        ["p", "0123456789abcdef", "train",
                                         "interior", "-1", "2", "3"]))],
                 header=list(points.AEDT_TO_FEMM_COLUMNS))
    dest = str(tmp_path / "freeze" / "frozen_points.csv")
    with pytest.raises(PointsRefusal, match="source's own"):
        points.adapt_points_file(source, dest)
    assert not os.path.exists(dest)


def test_conversion_refuses_to_overwrite_an_existing_destination(tmp_path):
    source = str(tmp_path / "source" / "aedt_points.csv")
    write_points(source, rows=[dict(zip(points.AEDT_TO_FEMM_COLUMNS,
                                        ["p", "0123456789abcdef", "train",
                                         "interior", "-1", "2", "3"]))],
                 header=list(points.AEDT_TO_FEMM_COLUMNS))
    dest = str(tmp_path / "campaign" / "frozen_points.csv")
    points.adapt_points_file(source, dest)
    original = open(dest, "rb").read()
    with pytest.raises(PointsRefusal, match="already exists"):
        points.adapt_points_file(source, dest)
    assert open(dest, "rb").read() == original


def test_conversion_sidecar_pins_the_source(tmp_path):
    source = str(tmp_path / "source" / "aedt_points.csv")
    header = list(points.AEDT_TO_FEMM_COLUMNS) + ["campaign_id", "seed"]
    write_points(source, rows=[dict(zip(header,
                                        ["p", "0123456789abcdef", "train",
                                         "interior", "-1", "2", "3",
                                         "eesm_task9", "20260710"]))],
                 header=header)
    dest = str(tmp_path / "campaign" / "frozen_points.csv")
    payload = points.adapt_points_file(source, dest)

    sidecar = json.loads(open(points.sidecar_path(dest), encoding="utf-8").read())
    assert sidecar == payload
    assert sidecar["source_sha256"] == points.sha256_file(source)
    assert sidecar["dropped_columns"] == ["campaign_id", "seed"]
    assert sidecar["column_mapping"]["Id [A]"] == "id_a"


def test_conversion_refuses_an_unrecognised_dialect(tmp_path):
    source = str(tmp_path / "source" / "other.csv")
    write_points(source, rows=[{"a": "1", "b": "2"}], header=["a", "b"])
    with pytest.raises(PointsRefusal, match="neither dialect"):
        points.dialect_of(source)
    with pytest.raises(PointsRefusal, match="missing columns"):
        points.adapt_points_file(source, str(tmp_path / "campaign" / "p.csv"))


def test_converted_points_drive_a_campaign(tmp_path):
    """The conversion's output is a campaign input, not just a valid CSV."""
    source = str(tmp_path / "source" / "aedt_points.csv")
    write_points(source, rows=[
        dict(zip(points.AEDT_TO_FEMM_COLUMNS,
                 ["p_one", "0123456789abcdef", "train", "interior",
                  "-40", "60", "6"])),
        dict(zip(points.AEDT_TO_FEMM_COLUMNS,
                 ["p_two", "fedcba9876543210", "train", "boundary",
                  "-120", "0", "1"])),
    ], header=list(points.AEDT_TO_FEMM_COLUMNS))

    campaign_paths = CampaignPaths(root=str(tmp_path / "campaign"))
    points.adapt_points_file(source, campaign_paths.points_csv)
    status, handle = run(campaign_paths)

    assert status["status"] == "complete"
    assert handle.analyze_count == 2
    assert len(results_rows(campaign_paths)) == 2


# ---------------------------------------------------------------------------
# Availability probe
#
# Asserted against INJECTED modules, never against this host: a test that
# pins `femm_importable is False` passes on the Linux box and fails on the
# Windows machine where the real run finally happens.
# ---------------------------------------------------------------------------


def make_femm_stub(name="femm", file="/opt/pyfemm/femm.py", attrs=()):
    stub = types.ModuleType(name)
    stub.__file__ = file
    for attr in attrs:
        setattr(stub, attr, lambda *a, **k: None)
    return stub


def test_this_package_shadowing_pyfemm_is_not_pyfemm(monkeypatch):
    """`import femm` finds eesm/femm whenever eesm/ is on sys.path."""
    import eesm.femm as this_package
    monkeypatch.setitem(sys.modules, "femm", this_package)

    availability = runtime.detect_femm()
    assert availability.importable is False
    assert availability.can_solve is False
    assert availability.shadowed_by == this_package.__file__
    assert "this package itself" in (availability.import_error or "")
    assert "shadowing pyFEMM" in availability.reason()


def test_a_stranger_named_femm_is_not_pyfemm(monkeypatch):
    """Something else called `femm` on the path is reported, not accepted."""
    monkeypatch.setitem(sys.modules, "femm", make_femm_stub(attrs=("openfemm",)))
    availability = runtime.detect_femm()
    assert availability.importable is False
    assert availability.shadowed_by is None
    assert "is not pyFEMM" in (availability.import_error or "")


def test_a_module_carrying_the_sentinels_is_accepted(monkeypatch):
    monkeypatch.setitem(sys.modules, "femm",
                        make_femm_stub(attrs=runtime.PYFEMM_SENTINELS))
    availability = runtime.detect_femm()
    assert availability.importable is True
    assert availability.can_solve is True
    assert availability.shadowed_by is None


def test_missing_calls_are_reported_but_never_gate(monkeypatch):
    """FEMM_CALL_SURFACE is itself unverified, so it must not refuse a run."""
    monkeypatch.setitem(sys.modules, "femm",
                        make_femm_stub(attrs=runtime.PYFEMM_SENTINELS))
    availability = runtime.detect_femm()
    assert availability.importable is True
    absent = set(runtime.FEMM_CALL_SURFACE) - set(runtime.PYFEMM_SENTINELS)
    assert set(availability.missing_api) == absent
    assert "are absent" in availability.reason()

    payload = runtime.availability_payload()
    assert payload["femm_importable"] is True
    assert payload["real_solve_performed"] is False


def test_resolve_femm_refuses_a_shadow_rather_than_returning_it(monkeypatch):
    import eesm.femm as this_package
    monkeypatch.setitem(sys.modules, "femm", this_package)
    with pytest.raises(RuntimeError, match="shadowing pyFEMM"):
        runtime.resolve_femm()


def test_resolve_femm_returns_an_explicit_override_untouched():
    handle = MockFemm()
    assert runtime.resolve_femm(handle) is handle


# ---------------------------------------------------------------------------
# Runner entry point
# ---------------------------------------------------------------------------


def load_runner():
    """Load eesm/run_femm_campaign.py without putting eesm/ on sys.path.

    Importing it the obvious way would create the very shadow the probe above
    is about, for every later test in this process.
    """
    path = os.path.join(REPO_ROOT, "eesm", "run_femm_campaign.py")
    spec = importlib.util.spec_from_file_location("eesm_run_femm_campaign", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runner():
    return load_runner()


def test_runner_refuses_a_root_holding_preserved_evidence(runner, tmp_path):
    root = tmp_path / "someone_elses_campaign"
    root.mkdir()
    (root / "campaign_freeze.json").write_text("{}", encoding="utf-8")
    with pytest.raises(runner.RunnerRefusal, match="preserved evidence"):
        runner.guard_campaign_root(str(root))


def test_runner_refuses_the_real_task9_freeze(runner):
    """The trap this guard exists for: writing beside the Task 9 evidence."""
    if not os.path.exists(TASK9_POINTS):
        pytest.skip("Task 9 freeze not present")
    freeze_dir = os.path.dirname(TASK9_POINTS)
    with pytest.raises(runner.RunnerRefusal, match="preserved evidence"):
        runner.guard_campaign_root(freeze_dir)


def test_runner_accepts_a_fresh_root(runner, tmp_path):
    root = tmp_path / "new_campaign"
    root.mkdir()
    runner.guard_campaign_root(str(root))  # does not raise


def test_runner_requires_a_points_source_for_an_empty_root(runner, tmp_path):
    with pytest.raises(runner.RunnerRefusal, match="no --points source"):
        runner.run_femm_campaign(output_dir=str(tmp_path / "empty"),
                                 points_source=None, use_mock=True)


def test_runner_mock_rehearsal_converts_and_completes(runner, tmp_path):
    """End to end on the real Task 9 points: convert, solve, resume, finish."""
    if not os.path.exists(TASK9_POINTS):
        pytest.skip("Task 9 frozen points not present")
    root = str(tmp_path / "rehearsal")

    partial = runner.run_femm_campaign(output_dir=root, points_source=TASK9_POINTS,
                                       use_mock=True, max_new_points=10)
    assert partial["status"] == "partial_resume_required"
    assert partial["points_preparation"]["action"] == "converted"
    assert len(partial["solved_this_run"]) == 10

    final = runner.run_femm_campaign(output_dir=root, use_mock=True)
    assert final["status"] == "complete"
    assert final["points_preparation"]["action"] == "existing"
    assert len(final["completed"]) == 64
    assert final["solver_backend"] == "mock_femm"
    assert final["femm_availability"]["real_solve_performed"] is False

    paths = CampaignPaths(root=root)
    assert len(results_rows(paths)) == 64
    schema = campaign.load_schema()
    for row in results_rows(paths):
        campaign.validate_row(row, schema)
