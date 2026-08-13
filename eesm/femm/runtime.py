"""The single place that knows how to obtain a FEMM handle.

Design rule
-----------
NOTHING in this package imports `femm` at module top level. FEMM 4.2 is
Windows-only (pyFEMM drives its ActiveX server through win32com), so a
top-level import would make every module in eesm/femm/ unimportable on Linux
and every test uncollectable. Instead:

  - `resolve_femm()` is the ONLY import site;
  - every other module takes the handle as a parameter.

That keeps the surface which must be verified against a real FEMM down to
one short list of calls, and it is what makes the mock honest -- the mock is
substituted at the same seam the real handle enters.
"""

from __future__ import annotations

import os
import platform
import shutil
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

#: This package's own directory. `import femm` finds THIS package whenever
#: eesm/ is on sys.path -- which Python does for free to any script under
#: eesm/, including eesm/run_femm_campaign.py. Detecting that is the
#: difference between "no FEMM here" and a run driven against the wrong
#: object, so the shadow is named explicitly rather than reported as success.
_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))

#: The GATE: names a real pyFEMM certainly exposes. Deliberately NOT the full
#: FEMM_CALL_SURFACE below -- that list is itself unverified, so gating on it
#: would let one wrong name reject a genuine pyFEMM and stall the Windows run
#: behind an error that looks like a FEMM fault.
PYFEMM_SENTINELS: Tuple[str, ...] = ("openfemm", "mi_probdef", "mi_analyze")


@dataclass(frozen=True)
class FemmAvailability:
    """What this machine can actually run, determined at runtime."""

    importable: bool
    platform_supported: bool
    system: str
    python_version: str
    wine_path: Optional[str] = None
    xfemm_paths: Dict[str, str] = field(default_factory=dict)
    import_error: Optional[str] = None
    #: Set when a module named `femm` imported but is this package, not pyFEMM.
    shadowed_by: Optional[str] = None
    #: Diagnostic only, never a gate: which of FEMM_CALL_SURFACE are absent.
    missing_api: Tuple[str, ...] = ()
    module_file: Optional[str] = None

    @property
    def can_solve(self) -> bool:
        """True only if a real solve could genuinely be attempted here."""
        return self.importable

    def reason(self) -> str:
        if self.importable:
            if self.missing_api:
                return ("pyfemm import succeeded, but %d of the calls this "
                        "package makes are absent: %s"
                        % (len(self.missing_api), ", ".join(self.missing_api)))
            return "pyfemm import succeeded"
        parts = ["pyfemm not importable (%s)" % (self.import_error or "unknown")]
        if self.shadowed_by:
            parts.append(
                "this repository's own eesm/femm package at %s is shadowing "
                "pyFEMM on sys.path" % self.shadowed_by
            )
        if not self.platform_supported:
            parts.append("platform %s is not Windows" % self.system)
        if self.wine_path:
            parts.append("wine found at %s but is NOT wired up here" % self.wine_path)
        if self.xfemm_paths:
            parts.append(
                "xfemm binaries found (%s) but xfemm is a different API and is "
                "NOT wired up here" % ", ".join(sorted(self.xfemm_paths))
            )
        return "; ".join(parts)


def _is_this_package(module_file: Optional[str]) -> bool:
    """True if `module_file` belongs to eesm/femm itself."""
    if not module_file:
        return False
    return os.path.realpath(module_file).startswith(
        os.path.realpath(_PACKAGE_DIR) + os.sep
    )


def detect_femm() -> FemmAvailability:
    """Probe for FEMM, Wine and xfemm. Never raises, never fakes.

    A module named `femm` that lacks PYFEMM_SENTINELS is NOT pyFEMM and is
    reported as unavailable, however it got onto sys.path.
    """
    system = platform.system()
    platform_supported = system == "Windows"

    importable = False
    import_error: Optional[str] = None
    shadowed_by: Optional[str] = None
    missing_api: Tuple[str, ...] = ()
    module_file: Optional[str] = None
    try:
        import femm  # noqa: F401
        module_file = getattr(femm, "__file__", None)
        missing_sentinels = [n for n in PYFEMM_SENTINELS if not hasattr(femm, n)]
        if missing_sentinels:
            if _is_this_package(module_file):
                shadowed_by = module_file
                import_error = (
                    "a module named 'femm' imported from %s, which is this "
                    "package itself, not pyFEMM" % module_file
                )
            else:
                import_error = (
                    "a module named 'femm' imported from %s but lacks %s, so "
                    "it is not pyFEMM" % (module_file, missing_sentinels)
                )
        else:
            importable = True
            missing_api = tuple(
                name for name in FEMM_CALL_SURFACE if not hasattr(femm, name)
            )
    except BaseException as exc:  # ImportError on Linux, COM errors elsewhere
        import_error = "%s: %s" % (type(exc).__name__, exc)

    wine_path = shutil.which("wine") or shutil.which("wine64")

    xfemm_paths: Dict[str, str] = {}
    for tool in ("fmesher", "fsolver", "fpproc"):
        found = shutil.which(tool)
        if found:
            xfemm_paths[tool] = found

    return FemmAvailability(
        importable=importable,
        platform_supported=platform_supported,
        system=system,
        python_version=sys.version.split()[0],
        wine_path=wine_path,
        xfemm_paths=xfemm_paths,
        import_error=import_error,
        shadowed_by=shadowed_by,
        missing_api=missing_api,
        module_file=module_file,
    )


def resolve_femm(override: Any = None) -> Any:
    """Return the object every other module will call FEMM through.

    `override` is the injection seam: pass a MockFemm in tests, or a live
    pyfemm module on Windows. Passing None imports the real thing and will
    raise on any machine without FEMM -- deliberately, because a silent
    fallback to a mock would let a run report numbers that no solver
    produced.
    """
    if override is not None:
        return override
    availability = detect_femm()
    if not availability.importable:
        raise RuntimeError(
            "FEMM is not available on this machine: %s. Pass an explicit "
            "handle (e.g. eesm.femm.mock_femm.MockFemm) to run offline. "
            "This package NEVER silently falls back to a mock."
            % availability.reason()
        )
    import femm  # pragma: no cover - Windows only
    return femm


def availability_payload() -> Dict[str, Any]:
    """Serialisable availability record, for status JSON and the migration doc."""
    availability = detect_femm()
    return {
        "femm_importable": availability.importable,
        "platform_supported": availability.platform_supported,
        "system": availability.system,
        "python_version": availability.python_version,
        "wine_path": availability.wine_path,
        "xfemm_paths": dict(availability.xfemm_paths),
        "shadowed_by": availability.shadowed_by,
        "module_file": availability.module_file,
        "missing_api": list(availability.missing_api),
        "reason": availability.reason(),
        "real_solve_performed": False,
    }


#: The complete list of FEMM API calls this package makes. Every one of these
#: must be confirmed against a live FEMM 4.2 on the first Windows run; this
#: list is the checklist in eesm/docs/FEMM_MIGRATION.md.
#:
#: This is a DIAGNOSTIC, not a gate. detect_femm() reports which of these a
#: live pyFEMM is missing but never refuses on that basis -- the list is
#: unverified, so a wrong name here must not be able to block a real run.
#: PYFEMM_SENTINELS above is the gate.
FEMM_CALL_SURFACE: List[str] = [
    "openfemm",
    "newdocument",
    "closefemm",
    "mi_probdef",
    "mi_getmaterial",
    "mi_addmaterial",
    "mi_addbhpoint",
    "mi_addcircprop",
    "mi_addboundprop",
    "mi_drawline",
    "mi_drawarc",
    "mi_addblocklabel",
    "mi_selectlabel",
    "mi_setblockprop",
    "mi_selectsegment",
    "mi_setsegmentprop",
    "mi_selectarcsegment",
    "mi_setarcsegmentprop",
    "mi_clearselected",
    "mi_setcurrent",
    "mi_saveas",
    "mi_analyze",
    "mi_loadsolution",
    "mo_getcircuitproperties",
    "mo_groupselectblock",
    "mo_blockintegral",
    "mo_clearblock",
    "mo_numelements",
    "mo_close",
]
