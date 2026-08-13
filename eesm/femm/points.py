"""Turn an AEDT-dialect frozen points file into one the FEMM campaign reads.

Why this module exists
----------------------
The only frozen points file in the repository is the Task 9 baseline's, and
`campaign.read_points()` refuses it:

    Refusing run: frozen points file is missing columns
    ['point_name', 'id_a', 'iq_a', 'if_a']

That file spells its columns the AEDT way (`PointName`, `Id [A]`, `Iq [A]`,
`If [A]`). The fix is NOT to teach `read_points` those aliases -- a reader
that accepts two dialects cannot tell an operator which one it just read, and
loosening a fail-closed gate to admit a convenient input is exactly what
AGENTS.md forbids. Instead the conversion is explicit, one-directional, and
leaves an audit trail.

What this module guarantees
---------------------------
  - The source file is never opened for writing and never moved.
  - A destination inside the source's own directory is REFUSED, so a
    conversion can never deposit derived files into a preserved freeze.
  - An existing destination is REFUSED rather than overwritten; a new
    conversion means a new directory, not a rewritten one.
  - Frozen identities (`point_id`, `role`, `region`) are copied verbatim.
    This module renames columns; it never renumbers, reorders, or reclassifies
    a point.
  - Every conversion writes a sidecar recording the source path, the source
    SHA-256, the exact column mapping applied, and the columns dropped -- so
    the original file remains the authority and nothing is silently lost.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .campaign import FROZEN_POINT_FIELDS


class PointsRefusal(RuntimeError):
    """A conversion invariant failed. Nothing was written."""


#: Source column -> FEMM campaign column. The AEDT exporter's spelling is on
#: the left; `campaign.FROZEN_POINT_FIELDS` is on the right.
AEDT_TO_FEMM_COLUMNS: Mapping[str, str] = {
    "PointName": "point_name",
    "point_id": "point_id",
    "role": "role",
    "region": "region",
    "Id [A]": "id_a",
    "Iq [A]": "iq_a",
    "If [A]": "if_a",
}

#: Written beside the converted points file.
SIDECAR_SUFFIX = ".provenance.json"


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def sidecar_path(points_path: str) -> str:
    return points_path + SIDECAR_SUFFIX


def read_header(path: str) -> List[str]:
    """The source file's column names. Refuses an unreadable or empty file."""
    if not os.path.exists(path):
        raise PointsRefusal("Refusing conversion: source file missing: %s" % path)
    with open(path, "r", encoding="utf-8", newline="") as stream:
        names = list(csv.DictReader(stream).fieldnames or [])
    if not names:
        raise PointsRefusal("Refusing conversion: source file has no header: %s" % path)
    return names


def dialect_of(path: str) -> str:
    """'femm' if the campaign can already read it, 'aedt' if it maps, else raise."""
    names = read_header(path)
    if all(field in names for field in FROZEN_POINT_FIELDS):
        return "femm"
    if all(source in names for source in AEDT_TO_FEMM_COLUMNS):
        return "aedt"
    raise PointsRefusal(
        "Refusing conversion: %s is neither dialect. It has %s; the FEMM "
        "campaign needs %s and the AEDT export has %s."
        % (path, sorted(names), sorted(FROZEN_POINT_FIELDS),
           sorted(AEDT_TO_FEMM_COLUMNS))
    )


def _guard_destination(source: str, dest: str) -> None:
    """Refuse a destination that would write into the source's directory."""
    source_dir = os.path.realpath(os.path.dirname(os.path.abspath(source)))
    dest_dir = os.path.realpath(os.path.dirname(os.path.abspath(dest)))
    if source_dir == dest_dir:
        raise PointsRefusal(
            "Refusing conversion: destination directory is the source's own "
            "directory (%s). A preserved freeze must not receive derived "
            "files; convert into a separate campaign root." % source_dir
        )
    if os.path.exists(dest):
        raise PointsRefusal(
            "Refusing conversion: destination already exists: %s. A new "
            "conversion is a new directory, never a rewritten one." % dest
        )


def copy_femm_points_file(source: str, dest: str) -> Dict[str, Any]:
    """Copy an already-FEMM-dialect points file into a new campaign root.

    Bytes are copied verbatim so the destination SHA-256 matches the source.
    The source freeze is not opened for writing.
    """
    if dialect_of(source) != "femm":
        raise PointsRefusal(
            "Refusing copy: %s is not in the FEMM campaign dialect." % source
        )
    _guard_destination(source, dest)
    source_hash = sha256_file(source)
    with open(source, "r", encoding="utf-8", newline="") as stream:
        rows = [dict(row) for row in csv.DictReader(stream)]
    if not rows:
        raise PointsRefusal("Refusing copy: source file has no rows")

    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    with open(source, "rb") as incoming, open(dest, "wb") as outgoing:
        outgoing.write(incoming.read())
    dest_hash = sha256_file(dest)
    if dest_hash != source_hash:
        os.remove(dest)
        raise PointsRefusal(
            "Refusing copy: destination hash drifted from source %s" % source_hash
        )

    payload: Dict[str, Any] = {
        "copied_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source_path": os.path.abspath(source),
        "source_sha256": source_hash,
        "source_columns": read_header(source),
        "column_mapping": {name: name for name in FROZEN_POINT_FIELDS},
        "dropped_columns": [],
        "rows": len(rows),
        "dest_path": os.path.abspath(dest),
        "dest_sha256": dest_hash,
        "note": (
            "Verbatim copy of a FEMM-dialect freeze. Identities, roles and "
            "regions are unchanged; the source file and its hash remain "
            "the authority."
        ),
    }
    with open(sidecar_path(dest), "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
    return payload


def adapt_points_file(source: str, dest: str,
                      mapping: Optional[Mapping[str, str]] = None,
                      ) -> Dict[str, Any]:
    """Write `source` to `dest` in the FEMM campaign's dialect.

    Returns the provenance payload, which is also written to the sidecar.
    Raises PointsRefusal, having written nothing, if any invariant fails.
    """
    mapping = dict(mapping if mapping is not None else AEDT_TO_FEMM_COLUMNS)
    _guard_destination(source, dest)

    names = read_header(source)
    missing = [column for column in mapping if column not in names]
    if missing:
        raise PointsRefusal(
            "Refusing conversion: source is missing columns %s" % sorted(missing)
        )
    produced = sorted(set(mapping.values()))
    unmapped = [field for field in FROZEN_POINT_FIELDS if field not in produced]
    if unmapped:
        raise PointsRefusal(
            "Refusing conversion: mapping does not produce required columns %s"
            % unmapped
        )

    source_hash = sha256_file(source)
    with open(source, "r", encoding="utf-8", newline="") as stream:
        rows = [dict(row) for row in csv.DictReader(stream)]
    if not rows:
        raise PointsRefusal("Refusing conversion: source file has no rows")

    converted: List[Dict[str, str]] = [
        {target: row[column] for column, target in mapping.items()}
        for row in rows
    ]

    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    fieldnames: Sequence[str] = list(FROZEN_POINT_FIELDS)
    with open(dest, "w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fieldnames),
                                extrasaction="raise")
        writer.writeheader()
        for row in converted:
            writer.writerow(row)

    payload: Dict[str, Any] = {
        "converted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source_path": os.path.abspath(source),
        "source_sha256": source_hash,
        "source_columns": names,
        "column_mapping": dict(mapping),
        "dropped_columns": [c for c in names if c not in mapping],
        "rows": len(converted),
        "dest_path": os.path.abspath(dest),
        "dest_sha256": sha256_file(dest),
        "note": (
            "Column rename only. point_id, role and region are verbatim from "
            "the source; the source file and its hash remain the authority."
        ),
    }
    with open(sidecar_path(dest), "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
    return payload
