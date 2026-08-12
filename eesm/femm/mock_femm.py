"""A mock of the `femm` module: enough to exercise geometry/extract/campaign
with no FEMM installed, on Linux.

Two jobs
--------
1. RECORD every call, so geometry.py can be asserted structurally (the
   antiperiodic condition landed on two distinct edges, the turns signs match
   the RMxprt map, the depth is the emitted value). Offline that is the only
   thing about the geometry that CAN be asserted.

2. RETURN analytically-exact flux linkages for a LINEAR SALIENT machine, so
   the dq and torque arithmetic can be asserted to floating-point precision:

       lambda_d = Ld * id + M * if
       lambda_q = Lq * iq

   with Ld > Lq > 0. Terminal currents are recovered from the branch currents
   the code under test set (x stator_parallel_branches), which is exactly the
   convention the real path must honour -- so a wrong branch factor shows up
   as a wrong flux linkage rather than passing silently.

What this mock is NOT
---------------------
It is not a solver and it is not evidence. Its default inductances are set to
the AEDT pilot's order-of-magnitude figures so that mock output looks
physically sane to a reader, but nothing here validates the real machine, the
geometry, the BH curve, or FEMM's own API constants. A wrong value in
FemmApiConfig CANNOT be caught by this mock -- the mock accepts whatever
config says. That is stated again in eesm/docs/FEMM_MIGRATION.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .config import (
    DEFAULT_CONFIG,
    FIELD_CIRCUIT,
    FemmConfig,
    PHASE_CIRCUITS,
)
from .extract import abc_from_dq, dq_from_abc


@dataclass(frozen=True)
class Call:
    """One recorded API call."""

    name: str
    args: Tuple[Any, ...]
    kwargs: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LinearSalientMachine:
    """The analytic machine the mock pretends to solve.

    Defaults are the AEDT pilot's order-of-magnitude figures
    (eesm/aedt/flux_extraction_v2.py: Ld=3.58e-3, Lq=1.89e-3 H, and the
    brief's d(lambda_d)/d(If) = +4.63e-3 Wb/A). They are SANITY TARGETS from
    a different mesh and solver, not measurements of this model.
    """

    ld_h: float = 3.58e-3
    lq_h: float = 1.89e-3
    #: d(lambda_d)/d(If), Wb/A. Positive, as the field must project onto +d.
    mutual_field_d_wb_per_a: float = 4.63e-3
    #: Field-circuit self inductance, for a plausible lambda_field readout.
    lf_h: float = 0.12
    #: Mock mesh size. Deliberately far above the ~2000-element AEDT Student
    #: cap that forced this migration.
    mesh_elements: int = 12457

    def flux_dq(self, id_a: float, iq_a: float, if_a: float) -> Tuple[float, float]:
        lambda_d = self.ld_h * id_a + self.mutual_field_d_wb_per_a * if_a
        lambda_q = self.lq_h * iq_a
        return lambda_d, lambda_q

    def flux_field(self, id_a: float, if_a: float) -> float:
        """Reciprocal coupling: the same mutual term appears on the field side."""
        return self.lf_h * if_a + self.mutual_field_d_wb_per_a * id_a


class MockFemm:
    """Drop-in stand-in for the pyfemm module.

    Pass an instance wherever `runtime.resolve_femm()` would have returned the
    real module. Every method name matches the FEMM 4.2 API.
    """

    def __init__(self, cfg: FemmConfig = DEFAULT_CONFIG,
                 machine: Optional[LinearSalientMachine] = None,
                 fail_analysis: bool = False) -> None:
        self.cfg = cfg
        self.machine = machine or LinearSalientMachine()
        self.fail_analysis = fail_analysis

        self.calls: List[Call] = []
        self.currents: Dict[str, float] = {}
        self.blocks: List[Dict[str, Any]] = []
        self.segments: List[Dict[str, Any]] = []
        self.arc_segments: List[Dict[str, Any]] = []
        self.boundary_props: List[Dict[str, Any]] = []
        self.circuits: List[Dict[str, Any]] = []
        self.materials: List[str] = []
        self.problem: Optional[Dict[str, Any]] = None
        self.documents: List[str] = []

        self.rotor_angle_deg: float = 0.0
        self._selected_label: Optional[Tuple[float, float]] = None
        self._selected_segment: Optional[Tuple[float, float]] = None
        self._selected_arc: Optional[Tuple[float, float]] = None
        self._selected_groups: List[int] = []
        self._solution: Optional[Dict[str, float]] = None

    # -- recording ---------------------------------------------------------

    def _record(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append(Call(name=name, args=tuple(args), kwargs=dict(kwargs)))

    def calls_named(self, name: str) -> List[Call]:
        return [call for call in self.calls if call.name == name]

    def call_count(self, name: str) -> int:
        return len(self.calls_named(name))

    @property
    def analyze_count(self) -> int:
        """How many solves were actually requested. The resume test's evidence."""
        return self.call_count("mi_analyze")

    # -- session -----------------------------------------------------------

    def openfemm(self, *args: Any) -> None:
        self._record("openfemm", *args)

    def newdocument(self, doctype: int) -> None:
        self._record("newdocument", doctype)

    def closefemm(self) -> None:
        self._record("closefemm")

    def mi_saveas(self, path: str) -> None:
        self._record("mi_saveas", path)
        self.documents.append(path)

    # -- problem definition ------------------------------------------------

    def mi_probdef(self, frequency: float, units: str, problem_type: str,
                   precision: float, depth: float, min_angle: float,
                   *rest: Any) -> None:
        self._record("mi_probdef", frequency, units, problem_type, precision,
                     depth, min_angle, *rest)
        self.problem = {
            "frequency": frequency,
            "units": units,
            "type": problem_type,
            "precision": precision,
            "depth": depth,
            "min_angle": min_angle,
        }

    def mi_getmaterial(self, name: str) -> None:
        self._record("mi_getmaterial", name)
        self.materials.append(name)

    def mi_addmaterial(self, name: str, *args: Any) -> None:
        self._record("mi_addmaterial", name, *args)
        self.materials.append(name)

    def mi_addcircprop(self, name: str, current: float, circuit_type: int) -> None:
        self._record("mi_addcircprop", name, current, circuit_type)
        self.circuits.append({"name": name, "current": current,
                              "type": circuit_type})
        self.currents[name] = current

    def mi_addboundprop(self, name: str, *args: Any) -> None:
        self._record("mi_addboundprop", name, *args)
        self.boundary_props.append({"name": name,
                                    "format": args[-1] if args else None})

    # -- drawing -----------------------------------------------------------

    def mi_drawline(self, x0: float, y0: float, x1: float, y1: float) -> None:
        self._record("mi_drawline", x0, y0, x1, y1)

    def mi_drawarc(self, x0: float, y0: float, x1: float, y1: float,
                   angle: float, maxseg: float) -> None:
        self._record("mi_drawarc", x0, y0, x1, y1, angle, maxseg)

    def mi_addblocklabel(self, x: float, y: float) -> None:
        self._record("mi_addblocklabel", x, y)

    # -- selection ---------------------------------------------------------

    def mi_selectlabel(self, x: float, y: float) -> None:
        self._record("mi_selectlabel", x, y)
        self._selected_label = (x, y)

    def mi_selectsegment(self, x: float, y: float) -> None:
        self._record("mi_selectsegment", x, y)
        self._selected_segment = (x, y)

    def mi_selectarcsegment(self, x: float, y: float) -> None:
        """ARCS need this, not mi_selectsegment, which only takes LINES.

        Added 2026-08-12 with the outer-boundary fix: the Dirichlet condition
        had been going through mi_selectsegment and landing on a stator slot
        wall instead of the outer arc.
        """
        self._record("mi_selectarcsegment", x, y)
        self._selected_arc = (x, y)

    def mi_selectgroup(self, group: int) -> None:
        self._record("mi_selectgroup", group)
        self._selected_groups.append(group)

    def mi_clearselected(self) -> None:
        self._record("mi_clearselected")
        self._selected_label = None
        self._selected_segment = None
        self._selected_arc = None
        self._selected_groups = []

    # -- property assignment ----------------------------------------------

    def mi_setblockprop(self, material: str, automesh: int, meshsize: float,
                        circuit: str, magdir: float, group: int,
                        turns: float) -> None:
        self._record("mi_setblockprop", material, automesh, meshsize, circuit,
                     magdir, group, turns)
        self.blocks.append({
            "material": material,
            "circuit": circuit,
            "group": group,
            "turns": turns,
            "position": self._selected_label,
        })

    def mi_setsegmentprop(self, boundary: str, elementsize: float,
                          automesh: int, hide: int, group: int) -> None:
        self._record("mi_setsegmentprop", boundary, elementsize, automesh,
                     hide, group)
        self.segments.append({
            "boundary": boundary,
            "group": group,
            "position": self._selected_segment,
        })

    def mi_setarcsegmentprop(self, maxsegdeg: float, boundary: str,
                             hide: int, group: int) -> None:
        """Note the DIFFERENT argument order from mi_setsegmentprop."""
        self._record("mi_setarcsegmentprop", maxsegdeg, boundary, hide, group)
        self.arc_segments.append({
            "boundary": boundary,
            "group": group,
            "maxsegdeg": maxsegdeg,
            "position": self._selected_arc,
        })

    def mi_setcurrent(self, circuit: str, current: float) -> None:
        self._record("mi_setcurrent", circuit, current)
        self.currents[circuit] = current

    # -- rotor motion ------------------------------------------------------

    def mi_moverotate(self, base_x: float, base_y: float, angle_deg: float,
                      group: int) -> None:
        self._record("mi_moverotate", base_x, base_y, angle_deg, group)
        self.rotor_angle_deg += angle_deg

    # -- solving -----------------------------------------------------------

    def _terminal_dq(self) -> Tuple[float, float, float, float]:
        """Recover (id, iq, if, theta) from the branch currents that were set."""
        branches = float(self.cfg.machine.stator_parallel_branches)
        terminal_abc = tuple(
            self.currents.get(name, 0.0) * branches for name in PHASE_CIRCUITS
        )
        field_branches = float(self.cfg.machine.field_parallel_branches)
        if_a = self.currents.get(FIELD_CIRCUIT, 0.0) * field_branches
        theta = (self.cfg.extraction.d_axis_electrical_deg
                 + self.cfg.machine.pole_pairs * self.rotor_angle_deg)
        id_a, iq_a = dq_from_abc(terminal_abc[0], terminal_abc[1],
                                 terminal_abc[2], theta)
        return id_a, iq_a, if_a, theta

    def mi_analyze(self, flag: int = 1) -> None:
        self._record("mi_analyze", flag)
        if self.fail_analysis:
            raise RuntimeError("mock solver failure")
        id_a, iq_a, if_a, theta = self._terminal_dq()
        lambda_d, lambda_q = self.machine.flux_dq(id_a, iq_a, if_a)
        lambda_a, lambda_b, lambda_c = abc_from_dq(lambda_d, lambda_q, theta)
        torque_full = (self.cfg.extraction.torque_identity_constant
                       * self.cfg.machine.pole_pairs
                       * (lambda_d * iq_a - lambda_q * id_a))
        self._solution = {
            "id_a": id_a,
            "iq_a": iq_a,
            "if_a": if_a,
            "theta": theta,
            "lambda_d": lambda_d,
            "lambda_q": lambda_q,
            "PhaseA": lambda_a,
            "PhaseB": lambda_b,
            "PhaseC": lambda_c,
            FIELD_CIRCUIT: self.machine.flux_field(id_a, if_a),
            # The block integral covers ONE sector, so the mock returns the
            # full-machine torque divided by the sector count -- which is
            # what the real solver would report and what extract.py must
            # multiply back up.
            "torque_sector": torque_full / self.cfg.extraction.torque_sector_multiplier,
        }

    def mi_loadsolution(self) -> None:
        self._record("mi_loadsolution")
        if self._solution is None:
            raise RuntimeError("mi_loadsolution before a successful mi_analyze")

    # -- post-processing ---------------------------------------------------

    def _require_solution(self) -> Dict[str, float]:
        if self._solution is None:
            raise RuntimeError("post-processing before mi_loadsolution")
        return self._solution

    def mo_getcircuitproperties(self, circuit: str) -> Tuple[float, float, float]:
        self._record("mo_getcircuitproperties", circuit)
        solution = self._require_solution()
        if circuit not in solution:
            raise RuntimeError("unknown circuit %r" % circuit)
        current = self.currents.get(circuit, 0.0)
        voltage = 0.0  # magnetostatic
        return current, voltage, solution[circuit]

    def mo_groupselectblock(self, group: int) -> None:
        self._record("mo_groupselectblock", group)
        self._selected_groups.append(group)

    def mo_clearblock(self) -> None:
        self._record("mo_clearblock")
        self._selected_groups = []

    def mo_blockintegral(self, integral_type: int) -> float:
        self._record("mo_blockintegral", integral_type)
        solution = self._require_solution()
        if integral_type != self.cfg.api.block_integral_torque:
            raise RuntimeError(
                "mock only implements block integral type %d (torque), got %d"
                % (self.cfg.api.block_integral_torque, integral_type)
            )
        return solution["torque_sector"]

    def mo_numelements(self) -> int:
        self._record("mo_numelements")
        return self.machine.mesh_elements

    def mo_close(self) -> None:
        self._record("mo_close")


def build_mock(cfg: FemmConfig = DEFAULT_CONFIG, **kwargs: Any) -> MockFemm:
    """Convenience constructor used by the tests."""
    machine_keys = {"ld_h", "lq_h", "mutual_field_d_wb_per_a", "lf_h",
                    "mesh_elements"}
    machine_kwargs = {k: v for k, v in kwargs.items() if k in machine_keys}
    other = {k: v for k, v in kwargs.items() if k not in machine_keys}
    machine = LinearSalientMachine(**machine_kwargs) if machine_kwargs else None
    return MockFemm(cfg=cfg, machine=machine, **other)


def analytic_torque_nm(id_a: float, iq_a: float, if_a: float,
                       machine: LinearSalientMachine,
                       cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    """Closed-form full-machine torque for the mock's machine.

    Independent of the extraction path, so a test can compare the two without
    the comparison being a tautology.
    """
    lambda_d, lambda_q = machine.flux_dq(id_a, iq_a, if_a)
    return (cfg.extraction.torque_identity_constant * cfg.machine.pole_pairs
            * (lambda_d * iq_a - lambda_q * id_a))
