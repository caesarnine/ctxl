import argparse
import os
import sys
import xml.etree.ElementTree as ET
from typing import BinaryIO, Dict, List, Set, TextIO, Union

import pathspec

# Define presets for different project types
PRESETS: Dict[str, Dict[str, List[str]]] = {
    "python": {
        "suffixes": [".py", ".pyi", ".pyx", ".ipynb"],
        "ignore": [
            "__pycache__",
            "*.pyc",
            "*.pyo",
            "*.pyd",
            "build",
            "dist",
            "*.egg-info",
            "venv",
        ],
    },
    "javascript": {
        "suffixes": [".js", ".jsx", ".mjs", ".cjs"],
        "ignore": [
            "node_modules",
            "npm-debug.log",
            "yarn-error.log",
            "yarn-debug.log",
            "package-lock.json",
            "yarn.lock",
            "dist",
            "build",
        ],
    },
    "typescript": {
        "suffixes": [".ts", ".tsx"],
        "ignore": [
            "node_modules",
            "npm-debug.log",
            "yarn-error.log",
            "yarn-debug.log",
            "package-lock.json",
            "yarn.lock",
            "dist",
            "build",
        ],
    },
    "web": {
        "suffixes": [".html", ".css", ".scss", ".sass", ".less"],
        "ignore": ["node_modules", "bower_components", "dist", "build", ".cache"],
    },
    "misc": {
        "suffixes": [
            ".md",
            ".txt",
            ".json",
            ".xml",
            ".yml",
            ".yaml",
            ".ini",
            ".cfg",
            ".conf",
            ".toml",
        ],
        "ignore": [],
    },
}

# Default ignore patterns
DEFAULT_IGNORE = [".*"]  # This will ignore all dotfiles and folders


def detect_project_types(folder_path: str) -> Set[str]:
    """
    Detect project types based on the file suffixes present in the directory.

    Args:
    folder_path (str): Path to the project folder

    Returns:
    Set[str]: Set of detected project types
    """
    detected_suffixes = set()

    for root, _, files in os.walk(folder_path):
        for file in files:
            _, ext = os.path.splitext(file)
            if ext:
                detected_suffixes.add(ext.lower())

    detected_types = set()
    for project_type, preset in PRESETS.items():
        if any(suffix in detected_suffixes for suffix in preset["suffixes"]):
            detected_types.add(project_type)

    return detected_types


def combine_presets(preset_names: List[str]) -> Dict[str, List[str]]:
    """
    Combine multiple presets into a single configuration.

    Args:
    preset_names (List[str]): List of preset names to combine.

    Returns:
    Dict[str, List[str]]: Combined preset configuration.
    """
    combined_preset = {"suffixes": set(), "ignore": set(DEFAULT_IGNORE)}

    for preset_name in preset_names:
        if preset_name in PRESETS:
            preset = PRESETS[preset_name]
            combined_preset["suffixes"].update(preset["suffixes"])
            combined_preset["ignore"].update(preset["ignore"])
        else:
            print(f"Warning: Preset '{preset_name}' not found. Skipping.")

    return {
        "suffixes": sorted(list(combined_preset["suffixes"])),
        "ignore": sorted(list(combined_preset["ignore"])),
    }


def read_gitignore(gitignore_path):
    patterns = []
    if os.path.isfile(gitignore_path):
        with open(gitignore_path, "r") as f:
            patterns = f.read().splitlines()
    return patterns


def create_file_element(file_path, file_content):
    file_element = ET.Element("file", path=file_path)
    content_element = ET.SubElement(file_element, "content")
    content_element.text = file_content
    return file_element


def dump_folder_contents(
    folder_path,
    output: Union[str, TextIO, BinaryIO],
    allowed_suffixes,
    additional_ignore,
    gitignore_path,
    task,
):
    gitignore_patterns = read_gitignore(gitignore_path)
    all_ignore_patterns = DEFAULT_IGNORE + gitignore_patterns + additional_ignore
    spec = pathspec.PathSpec.from_lines("gitwildmatch", all_ignore_patterns)

    root_element = ET.Element("root")
    project_context = ET.SubElement(root_element, "project_context")

    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [
            d
            for d in dirs
            if not spec.match_file(os.path.relpath(os.path.join(root, d), folder_path))
        ]
        for file in files:
            file_path = os.path.join(root, file)
            rel_file_path = os.path.relpath(file_path, folder_path)
            if any(
                file.endswith(suffix) for suffix in allowed_suffixes
            ) and not spec.match_file(rel_file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        file_content = f.read()
                    file_element = create_file_element(rel_file_path, file_content)
                    project_context.append(file_element)
                except Exception as e:
                    error_element = ET.Element("error", path=file_path)
                    error_element.text = str(e)
                    project_context.append(error_element)

    dir_structure_element = ET.SubElement(project_context, "directory_structure")
    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [
            d
            for d in dirs
            if not spec.match_file(os.path.relpath(os.path.join(root, d), folder_path))
        ]
        dir_element = ET.Element("directory", path=os.path.relpath(root, folder_path))
        for file in files:
            rel_file_path = os.path.relpath(os.path.join(root, file), folder_path)
            if any(
                file.endswith(suffix) for suffix in allowed_suffixes
            ) and not spec.match_file(rel_file_path):
                file_element = ET.Element("file", path=rel_file_path)
                dir_element.append(file_element)
        dir_structure_element.append(dir_element)

    task_element = ET.SubElement(root_element, "task")
    task_element.text = task

    tree = ET.ElementTree(root_element)

    if isinstance(output, str):
        tree.write(output, encoding="utf-8", xml_declaration=True)
    else:
        # For stdout or other file-like objects
        xml_string = ET.tostring(root_element, encoding="unicode", xml_declaration=True)
        output.write(xml_string)


def main():
    parser = argparse.ArgumentParser(description="Dump folder contents and structure.")
    parser.add_argument("folder_path", help="Path to the folder to be dumped")
    parser.add_argument(
        "-o", "--output", help="Path to the output file (default: stdout)", default="-"
    )
    parser.add_argument(
        "--presets",
        nargs="+",
        choices=list(PRESETS.keys()),
        help="Preset project types to combine (default: auto-detect)",
    )
    parser.add_argument(
        "--suffixes", nargs="+", help="Allowed file suffixes (overrides presets)"
    )
    parser.add_argument(
        "--ignore",
        nargs="*",
        help="Additional folders/files to ignore (added to preset ignores)",
    )
    parser.add_argument(
        "--include-dotfiles",
        action="store_true",
        help="Include dotfiles and folders in the output",
    )
    parser.add_argument(
        "--gitignore",
        help="Path to the .gitignore file (default: .gitignore in the folder_path)",
        default=None,
    )
    parser.add_argument(
        "--task",
        help="Task description to be included in the output",
        default="Describe this project in detail. Pay special attention to the structure of the code, the design of the project, any frameworks/UI frameworks used, and the overall structure/workflow. If artifacts are available, then use workflow and sequence diagrams to help describe the project.",
    )
    parser.add_argument(
        "--no-auto-detect",
        action="store_true",
        help="Disable auto-detection of project types",
    )
    args = parser.parse_args()

    # Auto-detect project types if not disabled and no presets specified
    if not args.no_auto_detect and not args.presets:
        detected_types = detect_project_types(args.folder_path)
        if detected_types:
            print(
                f"Detected project types: {', '.join(detected_types)}", file=sys.stderr
            )
            args.presets = list(detected_types)
        else:
            print(
                "No specific project types detected. Using misc preset.",
                file=sys.stderr,
            )
            args.presets = ["misc"]
    elif not args.presets:
        args.presets = ["misc"]

    # Always include 'misc' preset
    if "misc" not in args.presets:
        args.presets.append("misc")

    # Combine presets
    combined_preset = combine_presets(args.presets)

    # Apply combined preset and custom arguments
    suffixes = args.suffixes if args.suffixes else combined_preset["suffixes"]
    ignore = combined_preset["ignore"] + (args.ignore or [])

    # Remove the default dotfile ignore if --include-dotfiles is specified
    if args.include_dotfiles:
        ignore = [pattern for pattern in ignore if pattern != ".*"]

    # Set the default gitignore path if not provided
    if args.gitignore is None:
        args.gitignore = os.path.join(args.folder_path, ".gitignore")

    # Determine the output stream
    if args.output == "-":
        output = sys.stdout
    else:
        output = args.output

    dump_folder_contents(
        args.folder_path,
        output,
        suffixes,
        ignore,
        args.gitignore,
        args.task,
    )


if __name__ == "__main__":
    main()

# Explicitly export the main function
__all__ = ["main"]
