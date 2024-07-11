import ast
import importlib.util
import os
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Set


class DependencyAnalyzer:
    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.dependencies = defaultdict(
            lambda: {
                "upstream": {"external": set(), "internal": set()},
                "downstream": set(),
            }
        )

    def analyze_repo(self) -> None:
        for root, _, files in os.walk(self.repo_path):
            for file in files:
                if file.endswith(".py"):
                    file_path = os.path.join(root, file)
                    self.analyze_file(file_path)
        self.resolve_local_dependencies()

    def analyze_file(self, file_path: str) -> None:
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                content = file.read()

            tree = ast.parse(content)
            relative_path = os.path.relpath(file_path, self.repo_path)
            module_name = relative_path.replace("/", ".").replace(".py", "")

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.add_dependency(module_name, alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.level == 0:  # absolute import
                        if node.module:
                            self.add_dependency(module_name, node.module)
                    else:  # relative import
                        self.add_relative_dependency(
                            module_name, node.module, node.level
                        )

        except Exception as e:
            print(f"Error analyzing file {file_path}: {str(e)}")

    def add_dependency(self, importer: str, imported: str) -> None:
        if self.is_standard_library(imported):
            self.dependencies[importer]["upstream"]["external"].add(imported)
        elif imported.split(".")[0] in self.get_top_level_packages():
            self.dependencies[importer]["upstream"]["internal"].add(imported)
        else:
            self.dependencies[importer]["upstream"]["external"].add(imported)

    def add_relative_dependency(self, importer: str, imported: str, level: int) -> None:
        if imported is None:
            imported = ""
        importer_parts = importer.split(".")
        if level > len(importer_parts):
            print(f"Warning: Invalid relative import in {importer}")
            return
        base = ".".join(importer_parts[:-level])
        full_import = f"{base}.{imported}" if base else imported
        self.dependencies[importer]["upstream"]["internal"].add(full_import)

    def resolve_local_dependencies(self) -> None:
        for importer, deps in self.dependencies.items():
            for imported in deps["upstream"]["internal"]:
                if imported in self.dependencies:
                    self.dependencies[imported]["downstream"].add(importer)

    @staticmethod
    def is_standard_library(module_name: str) -> bool:
        try:
            spec = importlib.util.find_spec(module_name.split(".")[0])
            return spec is not None and "site-packages" not in spec.origin
        except (ImportError, AttributeError):
            return False

    def get_top_level_packages(self) -> Set[str]:
        return {
            name
            for name in os.listdir(self.repo_path)
            if os.path.isdir(os.path.join(self.repo_path, name))
            and name not in {"tests", "docs", "examples"}
        }

    def get_dependencies_xml(self) -> ET.Element:
        dependencies_element = ET.Element("dependencies")
        for file, deps in self.dependencies.items():
            file_element = ET.SubElement(dependencies_element, "file", path=file)

            upstream_element = ET.SubElement(file_element, "upstream")
            external_element = ET.SubElement(upstream_element, "external")
            for ext_dep in sorted(deps["upstream"]["external"]):
                ET.SubElement(external_element, "dependency").text = ext_dep

            internal_element = ET.SubElement(upstream_element, "internal")
            for int_dep in sorted(deps["upstream"]["internal"]):
                ET.SubElement(internal_element, "dependency").text = int_dep

            downstream_element = ET.SubElement(file_element, "downstream")
            for down_dep in sorted(deps["downstream"]):
                ET.SubElement(downstream_element, "dependency").text = down_dep

        return dependencies_element


def analyze_dependencies(repo_path: str) -> ET.Element:
    analyzer = DependencyAnalyzer(repo_path)
    analyzer.analyze_repo()
    return analyzer.get_dependencies_xml()
