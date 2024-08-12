import json
from datetime import datetime
from pathlib import Path


def save_snapshot(
    file_path: Path,
    original_content: str,
    applied_diff: str,
    updated_content: str,
    unified_diff: str,
    lint_output: str,
):
    ctxl_dir = Path.cwd() / ".ctxl"
    ctxl_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().isoformat(timespec="seconds").replace(":", "-")
    snapshot_file = ctxl_dir / f"snapshot_{timestamp}.json"

    snapshot_data = {
        "file_path": str(file_path),
        "original_content": original_content,
        "applied_diff": applied_diff,
        "updated_content": updated_content,
        "post_diff": unified_diff,
        "lint_output": lint_output,
        "timestamp": timestamp,
    }

    with snapshot_file.open("w") as f:
        json.dump(snapshot_data, f, indent=2)
