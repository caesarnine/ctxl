import os
from typing import Any, Dict

import yaml

DEFAULT_PRESET_FILE = "ctxl_presets.yaml"

# Define the built-in presets
BUILT_IN_PRESETS = {
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


def load_presets(preset_file: str = DEFAULT_PRESET_FILE) -> Dict[str, Any]:
    if os.path.exists(preset_file):
        with open(preset_file, "r") as f:
            return yaml.safe_load(f)
    return {}


def save_presets(
    presets: Dict[str, Any], preset_file: str = DEFAULT_PRESET_FILE
) -> None:
    with open(preset_file, "w") as f:
        yaml.dump(presets, f, default_flow_style=False)


def get_presets() -> Dict[str, Any]:
    custom_presets = load_presets()
    return {**BUILT_IN_PRESETS, **custom_presets}


def view_presets() -> str:
    presets = get_presets()
    return yaml.dump(presets, default_flow_style=False)


def save_built_in_presets(preset_file: str = DEFAULT_PRESET_FILE) -> None:
    save_presets(BUILT_IN_PRESETS, preset_file)
