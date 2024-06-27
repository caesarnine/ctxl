import argparse
import os
import xml.etree.ElementTree as ET

import pathspec

default_task = """Describe this coding project in detail. 

Pay special attention to the structure of the code, the design of the project, any frameworks/UI frameworks used, and the overall structure/workflow.

If artifacts are available, then include any diagrams or charts that you think would be helpful.

When suggesting new code or updates always output the entire file, not just the changes.
"""


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
    folder_path, output_file, allowed_suffixes, additional_ignore, gitignore_path, task
):
    gitignore_patterns = read_gitignore(gitignore_path)
    all_ignore_patterns = gitignore_patterns + additional_ignore
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
                    with open(file_path, "r") as f:
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
    tree.write(output_file, encoding="utf-8", xml_declaration=True)


default_task = """Describe this coding project in detail. 

Pay special attention to the structure of the code, the design of the project, any frameworks/UI frameworks used, and the overall structure/workflow.

If artifacts are available, then include any diagrams or charts that you think would be helpful.

When suggesting new code or updates always output the entire file, not just the changes.
"""


def main():
    parser = argparse.ArgumentParser(description="Dump folder contents and structure.")
    parser.add_argument("folder_path", help="Path to the folder to be dumped")
    parser.add_argument("output_file", help="Path to the output file")
    parser.add_argument(
        "--suffixes",
        nargs="+",
        help="Allowed file suffixes (e.g., .txt .py)",
        default=[".py", ".txt", ".tsx", ".js", ".css", ".json", ".html"],
    )
    parser.add_argument(
        "--ignore",
        nargs="*",
        help="Additional folders/files to ignore",
        default=[
            ".git",
            ".idea",
            "__pycache__",
            "**packages**",
            "**node_modules**",
            "package-lock.json",
        ],
    )
    parser.add_argument(
        "--gitignore",
        help="Path to the .gitignore file (default: .gitignore in the folder_path)",
        default=None,
    )
    parser.add_argument(
        "--task",
        help=f"Task description to be included in the output (default: '{default_task}')",
        default=default_task,
    )
    args = parser.parse_args()

    # Set the default gitignore path if not provided
    if args.gitignore is None:
        args.gitignore = os.path.join(args.folder_path, ".gitignore")

    dump_folder_contents(
        args.folder_path,
        args.output_file,
        args.suffixes,
        args.ignore,
        args.gitignore,
        args.task,
    )


if __name__ == "__main__":
    main()

# Explicitly export the main function
__all__ = ["main"]
