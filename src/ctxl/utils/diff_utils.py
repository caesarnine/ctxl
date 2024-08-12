from difflib import unified_diff
from pathlib import Path

from diff_match_patch import diff_match_patch

from .snapshot_utils import save_snapshot

dmp = diff_match_patch()
dmp.Match_Distance = 1000000


def parse_diff(diff_text):
    lines = diff_text.split("\n")
    diffs = []
    current_hunk = []
    for line in lines:
        # ignore the file headers
        if line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("@@"):
            if current_hunk:
                diffs.append(current_hunk)
            current_hunk = []
        if line.startswith(" "):
            current_hunk.append((0, line[1:] + "\n"))
        elif line.startswith("+"):
            current_hunk.append((1, line[1:] + "\n"))
        elif line.startswith("-"):
            current_hunk.append((-1, line[1:] + "\n"))

    if current_hunk:
        dmp.diff_cleanupSemanticLossless(current_hunk)
        dmp.diff_cleanupMerge(current_hunk)
        dmp.diff_cleanupEfficiency(current_hunk)
        diffs.append(current_hunk)

    return diffs


def apply_diff(file_path: Path | str, diff_text: str) -> tuple[str, str]:
    file_path = Path(file_path)  # Ensure file_path is a Path object

    # to handle the case where it's a diff for a new file
    if not file_path.exists():
        file_path.touch()

    with file_path.open("r") as f:
        original_content = f.read()

    text = original_content

    # Apply diff
    hunk_diffs = parse_diff(diff_text)
    hunk_patches = [dmp.patch_make(hunk) for hunk in hunk_diffs]

    failed_hunks = []
    text = original_content

    for i, patch in enumerate(hunk_patches, 1):
        text, applied_successfully = dmp.patch_apply(patch, text)

        if not all(applied_successfully):
            failed_hunks.append(str(i))

    if failed_hunks:
        failed_hunks_str = ", ".join(failed_hunks)
        return (
            f"Failed to apply hunk(s): {failed_hunks_str}. The file has not been modified.",
            "",
        )

    with file_path.open("w") as f:
        f.write(text)

    with file_path.open("r") as f:
        updated_content = f.read()

    # Generate unified diff
    unified_diff_lines = list(
        unified_diff(
            original_content.splitlines(keepends=True),
            updated_content.splitlines(keepends=True),
            fromfile=str(file_path),
            tofile=str(file_path),
            lineterm="",
        )
    )

    unified_diff_text = "".join(unified_diff_lines)

    save_snapshot(
        file_path,
        original_content,
        diff_text,
        updated_content,
        unified_diff_text,
        "",  # We don't have lint output here, so passing an empty string
    )

    return updated_content, unified_diff_text
