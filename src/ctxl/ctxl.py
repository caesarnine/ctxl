import logging
import os
import xml.etree.ElementTree as ET
from typing import Dict, List, Set

import pathspec

from .preset_manager import (
    get_presets,
)

# Default exclude patterns
DEFAULT_EXCLUDE = [".*"]  # This will exclude all dotfiles and folders

logger = logging.getLogger(__name__)


def detect_project_types(folder_path: str) -> Set[str]:
    detected_types = set()

    for root, _, files in os.walk(folder_path):
        for file in files:
            file_lower = file.lower()

            # Check prefixes
            for project_type, preset in get_presets().items():
                if "prefixes" in preset and any(
                    file_lower.startswith(prefix.lower())
                    for prefix in preset["prefixes"]
                ):
                    detected_types.add(project_type)
                    continue

            # Check suffixes
            _, ext = os.path.splitext(file)
            if ext:
                for project_type, preset in get_presets().items():
                    if ext in preset["suffixes"]:
                        detected_types.add(project_type)
                        break  # No need to check other presets for this file

            # Check for exact matches (like docker-compose.yml)
            for project_type, preset in get_presets().items():
                if file in preset.get("include", []):
                    detected_types.add(project_type)

    logger.debug(f"Detected project types: {detected_types}")
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
    logger.debug(
        f"Parsed filter patterns - Include: {include_patterns}, Exclude: {exclude_patterns}"
    )
    return {"include": include_patterns, "exclude": exclude_patterns}


def combine_presets(
    preset_names: List[str], filter_patterns: Dict[str, List[str]]
) -> Dict[str, List[str]]:
    combined_preset = {"include": set(), "exclude": set(DEFAULT_EXCLUDE)}
    presets = get_presets()

    for preset_name in preset_names:
        if preset_name in presets:
            preset = presets[preset_name]
            combined_preset["include"].update(preset["include"])
            combined_preset["exclude"].update(preset["exclude"])
        else:
            logger.warning(f"Preset '{preset_name}' not found. Skipping.")

    # Add user-specified filter patterns
    combined_preset["include"].update(filter_patterns["include"])
    combined_preset["exclude"].update(filter_patterns["exclude"])

    logger.debug(
        f"Combined preset - Include: {combined_preset['include']}, Exclude: {combined_preset['exclude']}"
    )
    return {
        "include": sorted(list(combined_preset["include"])),
        "exclude": sorted(list(combined_preset["exclude"])),
    }


def read_gitignore(gitignore_path):
    patterns = []
    if os.path.isfile(gitignore_path):
        with open(gitignore_path, "r") as f:
            patterns = f.read().splitlines()
    logger.debug(f"Read {len(patterns)} patterns from .gitignore")
    return patterns


def create_file_element(file_path, file_content):
    file_element = ET.Element("file", path=file_path)
    content_element = ET.SubElement(file_element, "content")
    content_element.text = file_content
    return file_element


def generate_tree(
    folder_path: str,
    include_patterns: List[str],
    exclude_patterns: List[str],
    gitignore_path: str,
    include_dotfiles: bool,
) -> str:
    gitignore_patterns = read_gitignore(gitignore_path)

    # Create separate PathSpec objects for include and exclude patterns
    include_spec = pathspec.PathSpec.from_lines("gitwildmatch", include_patterns)
    exclude_spec = pathspec.PathSpec.from_lines(
        "gitwildmatch", exclude_patterns + gitignore_patterns
    )

    def build_tree(root_path, prefix=""):
        tree_str = ""
        items = sorted(os.listdir(root_path))
        if not include_dotfiles:
            items = [item for item in items if not item.startswith(".")]

        for index, item in enumerate(items):
            item_path = os.path.join(root_path, item)
            rel_item_path = os.path.relpath(item_path, folder_path)

            if exclude_spec.match_file(rel_item_path):
                continue

            connector = "└── " if index == len(items) - 1 else "├── "
            tree_str += f"{prefix}{connector}{item}\n"

            if os.path.isdir(item_path):
                extension = "    " if index == len(items) - 1 else "│   "
                tree_str += build_tree(item_path, prefix + extension)

        return tree_str

    return build_tree(folder_path)


def generate_xml(
    folder_path: str,
    include_patterns: List[str],
    exclude_patterns: List[str],
    gitignore_path: str,
    task: str,
    include_dotfiles: bool,
) -> str:
    gitignore_patterns = read_gitignore(gitignore_path)

    # Create separate PathSpec objects for include and exclude patterns
    include_spec = pathspec.PathSpec.from_lines("gitwildmatch", include_patterns)
    exclude_spec = pathspec.PathSpec.from_lines(
        "gitwildmatch", exclude_patterns + gitignore_patterns
    )

    root_element = ET.Element("root")
    project_context = ET.SubElement(root_element, "project_context")

    file_count = 0
    error_count = 0

    for root, dirs, files in os.walk(folder_path):
        rel_root = os.path.relpath(root, folder_path)
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
                    file_count += 1
                except Exception as e:
                    error_element = ET.Element("error", path=rel_file_path)
                    error_element.text = str(e)
                    project_context.append(error_element)
                    error_count += 1
                    logger.error(f"Error processing file {rel_file_path}: {str(e)}")

    logger.info(f"Processed {file_count} files with {error_count} errors")

    # Generate complete directory structure in tree format
    tree_output = generate_tree(folder_path, include_patterns, exclude_patterns, gitignore_path, include_dotfiles)
    dir_structure_element = ET.SubElement(project_context, "directory_structure")
    dir_structure_element.text = tree_output

    task_element = ET.SubElement(root_element, "task")
    task_element.text = task

    return ET.tostring(root_element, encoding="unicode", xml_declaration=True)
