"""Read only structured metadata; never include legacy logs or transcript databases."""

import json
import re
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from runtime_diagnostics import COMPONENTS, EVENTS, app_health, root_directory, safe_fields


def snapshot(root: Path | None = None) -> dict:
    root = root or root_directory()
    result = {"schema": 1, "app_health": app_health(root), "recent_events": []}
    for component in sorted(COMPONENTS):
        path = root / f"{component}.events.jsonl"
        try:
            # Bound reads regardless of corrupt or unexpectedly large files.
            with path.open("rb") as stream:
                stream.seek(max(0, path.stat().st_size - 65536))
                lines = stream.read().decode("utf-8", errors="replace").splitlines()[-25:]
            for line in lines:
                try:
                    entry = json.loads(line.lstrip("\ufeff"))
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("event") not in EVENTS or entry.get("component") != component:
                        continue
                    record = safe_fields(entry)
                    timestamp = entry.get("utc")
                    if isinstance(timestamp, str):
                        with suppress(ValueError):
                            record["utc"] = datetime.fromisoformat(timestamp).isoformat()
                    exception = entry.get("exception", {})
                    exception_type = (
                        exception.get("type", "") if isinstance(exception, dict) else ""
                    )
                    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", exception_type):
                        record["exception_type"] = exception_type
                    wrapper_exception = entry.get("exception_type", "")
                    if isinstance(wrapper_exception, str) and re.fullmatch(
                        r"[A-Za-z_][A-Za-z0-9_.]{0,120}", wrapper_exception
                    ):
                        record["exception_type"] = wrapper_exception
                    for key in ("epoch", "pid", "ppid", "elapsed_s"):
                        if type(entry.get(key)) in (int, float):
                            record[key] = entry[key]
                    for key in ("run_id", "task_run_id"):
                        value = entry.get(key, "")
                        if (
                            isinstance(value, str)
                            and len(value) == 32
                            and all(c in "0123456789abcdef" for c in value)
                        ):
                            record[key] = value
                    record.update(component=component, event=entry["event"])
                    result["recent_events"].append(record)
                except (ValueError, TypeError):
                    continue
        except OSError:
            pass
    result["recent_events"].sort(key=lambda item: item.get("epoch", 0))
    return result


if __name__ == "__main__":
    print(json.dumps(snapshot(), indent=2))
