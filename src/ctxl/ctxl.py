import argparse
import os
import sys
import xml.etree.ElementTree as ET
from typing import BinaryIO, Dict, List, Set, TextIO, Union

import pathspec

PRESETS: Dict[str, Dict[str, List[str]]] = {
    "python": {
        "suffixes": [".py", ".pyi", ".pyx", ".ipynb"],
        "include": ["*.py", "*.pyi", "*.pyx", "*.ipynb"],
        "exclude": [
            "__pycache__",
            "*.pyc",
            "*.pyo",
            "*.pyd",
            "build",
            "dist",
            "*.egg-info",
            "venv",
            ".pytest_cache",
        ],
    },
    "javascript": {
        "suffixes": [".js", ".mjs", ".cjs", ".jsx"],
        "include": ["*.js", "*.mjs", "*.cjs", "*.jsx"],
        "exclude": [
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
        "include": ["*.ts", "*.tsx"],
        "exclude": [
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
        "suffixes": [".html", ".css", ".scss", ".sass", ".less", ".vue"],
        "include": ["*.html", "*.css", "*.scss", "*.sass", "*.less", "*.vue"],
        "exclude": ["node_modules", "bower_components", "dist", "build", ".cache"],
    },
    "java": {
        "suffixes": [".java"],
        "include": ["*.java"],
        "exclude": [
            "target",
            ".gradle",
            "build",
            "out",
        ],
    },
    "csharp": {
        "suffixes": [".cs", ".csx", ".csproj"],
        "include": ["*.cs", "*.csx", "*.csproj"],
        "exclude": [
            "bin",
            "obj",
            "*.suo",
            "*.user",
            "*.userosscache",
            "*.sln.docstates",
        ],
    },
    "go": {
        "suffixes": [".go"],
        "include": ["*.go"],
        "exclude": [
            "vendor",
        ],
    },
    "ruby": {
        "suffixes": [".rb", ".rake", ".gemspec"],
        "include": ["*.rb", "*.rake", "*.gemspec"],
        "exclude": [
            ".bundle",
            "vendor/bundle",
        ],
    },
    "php": {
        "suffixes": [".php"],
        "include": ["*.php"],
        "exclude": [
            "vendor",
            "composer.lock",
        ],
    },
    "rust": {
        "suffixes": [".rs"],
        "include": ["*.rs"],
        "exclude": [
            "target",
            "Cargo.lock",
        ],
    },
    "swift": {
        "suffixes": [".swift"],
        "include": ["*.swift"],
        "exclude": [
            ".build",
            "Packages",
        ],
    },
    "kotlin": {
        "suffixes": [".kt", ".kts"],
        "include": ["*.kt", "*.kts"],
        "exclude": [
            ".gradle",
            "build",
            "out",
        ],
    },
    "scala": {
        "suffixes": [".scala", ".sc"],
        "include": ["*.scala", "*.sc"],
        "exclude": [
            ".bloop",
            ".metals",
            "target",
        ],
    },
    "docker": {
        "suffixes": [".dockerfile", ".dockerignore"],
        "prefixes": ["Dockerfile"],
        "include": [
            "Dockerfile",
            "Dockerfile.*",
            ".dockerignore",
            "docker-compose.yml",
            "docker-compose.yaml",
        ],
        "exclude": [],
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
        "include": [
            "*.md",
            "*.txt",
            "*.json",
            "*.xml",
            "*.yml",
            "*.yaml",
            "*.ini",
            "*.cfg",
            "*.conf",
            "*.toml",
        ],
        "exclude": [],
    },
}

# Default exclude patterns
DEFAULT_EXCLUDE = [".*"]  # This will exclude all dotfiles and folders


def detect_project_types(folder_path: str) -> Set[str]:
    detected_types = set()

    for root, _, files in os.walk(folder_path):
        for file in files:
            file_lower = file.lower()

            # Check prefixes
            for project_type, preset in PRESETS.items():
                if "prefixes" in preset and any(
                    file_lower.startswith(prefix.lower())
                    for prefix in preset["prefixes"]
                ):
                    detected_types.add(project_type)
                    continue

            # Check suffixes
            _, ext = os.path.splitext(file)
            if ext:
                for project_type, preset in PRESETS.items():
                    if ext in preset["suffixes"]:
                        detected_types.add(project_type)
                        break  # No need to check other presets for this file

            # Check for exact matches (like docker-compose.yml)
            for project_type, preset in PRESETS.items():
                if file in preset.get("include", []):
                    detected_types.add(project_type)

    return detected_types


def parse_filter_patterns(filter_string: str) -> Dict[str, List[str]]:
    if not filter_string:
        return {"include": [], "exclude": []}

    patterns = filter_string.split()
    include_patterns = []
    exclude_patterns = []
    for pattern in patterns:
        if pattern.startswith("!"):
            exclude_patterns.append(pattern[1:])
        else:
            include_patterns.append(pattern)
    return {"include": include_patterns, "exclude": exclude_patterns}


def combine_presets(
    preset_names: List[str], filter_patterns: Dict[str, List[str]]
) -> Dict[str, List[str]]:
    combined_preset = {"include": set(), "exclude": set(DEFAULT_EXCLUDE)}

    for preset_name in preset_names:
        if preset_name in PRESETS:
            preset = PRESETS[preset_name]
            combined_preset["include"].update(preset["include"])
            combined_preset["exclude"].update(preset["exclude"])
        else:
            print(
                f"Warning: Preset '{preset_name}' not found. Skipping.", file=sys.stderr
            )

    # Add user-specified filter patterns
    combined_preset["include"].update(filter_patterns["include"])
    combined_preset["exclude"].update(filter_patterns["exclude"])

    return {
        "include": sorted(list(combined_preset["include"])),
        "exclude": sorted(list(combined_preset["exclude"])),
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
    include_patterns,
    exclude_patterns,
    gitignore_path,
    task,
):
    gitignore_patterns = read_gitignore(gitignore_path)

    # Create separate PathSpec objects for include and exclude patterns
    include_spec = pathspec.PathSpec.from_lines("gitwildmatch", include_patterns)
    exclude_spec = pathspec.PathSpec.from_lines(
        "gitwildmatch", exclude_patterns + gitignore_patterns
    )

    root_element = ET.Element("root")
    project_context = ET.SubElement(root_element, "project_context")

    for root, dirs, files in os.walk(folder_path):
        rel_root = os.path.relpath(root, folder_path)
        dirs[:] = [
            d for d in dirs if not exclude_spec.match_file(os.path.join(rel_root, d))
        ]
        for file in files:
            rel_file_path = os.path.join(rel_root, file)
            if include_spec.match_file(rel_file_path) and not exclude_spec.match_file(
                rel_file_path
            ):
                try:
                    with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                        file_content = f.read()
                    file_element = create_file_element(rel_file_path, file_content)
                    project_context.append(file_element)
                except Exception as e:
                    error_element = ET.Element("error", path=rel_file_path)
                    error_element.text = str(e)
                    project_context.append(error_element)

    dir_structure_element = ET.SubElement(project_context, "directory_structure")
    for root, dirs, files in os.walk(folder_path):
        rel_root = os.path.relpath(root, folder_path)
        dirs[:] = [
            d for d in dirs if not exclude_spec.match_file(os.path.join(rel_root, d))
        ]
        dir_element = ET.Element("directory", path=rel_root)
        for file in files:
            rel_file_path = os.path.join(rel_root, file)
            if include_spec.match_file(rel_file_path) and not exclude_spec.match_file(
                rel_file_path
            ):
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
        "--filter",
        type=str,
        help="Filter patterns to include or exclude files. Use '!' to exclude. Example: --filter '*.py !__pycache__ !*.pyc'",
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
            args.presets = []
    elif not args.presets:
        args.presets = []

    # Parse filter patterns
    filter_patterns = parse_filter_patterns(args.filter or [])

    # Combine presets and apply filters
    combined_preset = combine_presets(args.presets, filter_patterns)

    # Remove the default dotfile exclude if --include-dotfiles is specified
    if args.include_dotfiles:
        combined_preset["exclude"] = [
            pattern for pattern in combined_preset["exclude"] if pattern != ".*"
        ]

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
        combined_preset["include"],
        combined_preset["exclude"],
        args.gitignore,
        args.task,
    )


if __name__ == "__main__":
    main()

# Explicitly export the main function
__all__ = ["main"]
