import json
from pathlib import Path

PROJECT_ROOT = Path(
    r"C:\Users\darsh\TAMU\EMPE_Lab\Motor_Control_NN_Pipeline\aedt_mcp"
)
DEFAULT_PROJECT = PROJECT_ROOT / "tmp" / "aedt_projects" / "ipm_1_probe" / "ipm_1.aedt"
OUT = PROJECT_ROOT / "tmp" / "aedt_jobs" / "gui_probe_result.json"


def list_or_empty(fn):
    try:
        return list(fn())
    except BaseException:
        return []


def open_default_if_needed():
    projects = list_or_empty(oDesktop.GetProjectList)
    if projects:
        return projects[-1]
    if DEFAULT_PROJECT.exists():
        oDesktop.OpenProject(str(DEFAULT_PROJECT))
        projects = list_or_empty(oDesktop.GetProjectList)
        if projects:
            return projects[-1]
    return None


def probe():
    project_name = open_default_if_needed()
    if not project_name:
        return {"status": "error", "message": "No project is open and default copied project was not found."}

    project = oDesktop.SetActiveProject(project_name)
    designs = []
    for raw_design in list_or_empty(project.GetTopDesignList):
        design_name = str(raw_design).split(";")[-1]
        item = {
            "name": design_name,
            "raw_name": str(raw_design),
            "type": None,
            "setups": [],
            "variables": [],
            "excitations": [],
        }
        try:
            design = project.SetActiveDesign(design_name)
            item["type"] = design.GetDesignType()
            item["variables"] = list_or_empty(design.GetVariables)
            try:
                item["setups"] = list(design.GetModule("AnalysisSetup").GetSetups())
            except BaseException as exc:
                item["setups_error"] = str(exc)
            try:
                item["excitations"] = list(design.GetModule("BoundarySetup").GetExcitations())
            except BaseException as exc:
                item["excitations_error"] = str(exc)
        except BaseException as exc:
            item["error"] = str(exc)
        designs.append(item)

    return {
        "status": "ok",
        "project": project_name,
        "project_path_hint": str(DEFAULT_PROJECT),
        "designs": designs,
    }


OUT.parent.mkdir(parents=True, exist_ok=True)
payload = probe()
OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
AddWarningMessage("Wrote GUI probe result to: " + str(OUT))
