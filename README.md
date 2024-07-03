# ctxl: Contextual

[![PyPI version](https://badge.fury.io/py/ctxl.svg)](https://badge.fury.io/py/ctxl)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

ctxl is a CLI tool designed to transform project directories into a structured XML format suitable for language models and AI analysis. It intelligently extracts file contents and directory structures while respecting gitignore rules and custom filters. A key feature of ctxl is its ability to automatically detect project types (such as Python, JavaScript, or web projects) based on the files present in the directory. This auto-detection enables ctxl to make smart decisions about which files to include or exclude, ensuring that the output is relevant and concise. Users can also override this auto-detection with custom presets if needed.

The tool creates a comprehensive project snapshot that can be easily parsed by LLMs, complete with a customizable task specification. This task specification acts as a prompt, priming the LLM to provide more targeted and relevant assistance with your project.

ctxl was developed through a bootstrapping process, where each version was used to generate context for an LLM in developing the next version.

## Table of Contents
- [Why ctxl?](#why-ctxl)
- [Installation](#installation)
- [Quick Start](#quick-start)
  - [Workflow](#workflow)
- [How It Works](#how-it-works)
- [Usage](#usage)
  - [Basic Usage](#basic-usage)
  - [Command-line Options](#command-line-options)
  - [Presets](#presets)
- [Features](#features)
- [Output Example](#output-example)
- [Integration with LLMs](#integration-with-llms)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## Why ctxl?

ctxl streamlines the process of providing project context to LLMs. Instead of manually copying and pasting file contents or explaining your project structure, ctxl automatically generates a comprehensive, structured representation of your project. This allows LLMs to have a more complete understanding of your codebase, leading to more accurate and context-aware assistance.

## Installation

To install ctxl, you can use pip:

```bash
pip install ctxl
```

## Quick Start

After installation, you can quickly generate an XML representation of your project:

```bash
ctxl /path/to/your/project > project_context.xml
```

This command will create an XML file which you can then provide to an LLM for analysis or assistance. The XML output includes file contents, directory structure, and a default task description that guides the LLM in analyzing your project.

### Workflow

This is how I've been using it - essentially as a iterative process.

1. Paste this directly into your LLM's chat interface (or via API/CLI) and let it respond first. I've found the latest Claude models (Sonnet 3.5 as of writing this) to work best.
2. The LLM will respond with a thorough breakdown and summary of the project first, which helps to prime the LLM with a better contextual understanding of the project, frameworks/libraries used, and overall user/data flow. 
3. Chat with it as normal after. You can ask for things like:
    >I'd like to update the frontend to show live progress when the backend is processing documents.

4. The LLM will use the context of your entire project to suggest refactors/updates to all the relevant files involved to fulfill that ask.
5. Update those files/sections, see if it works/if you like it, if not give feedback/error messages back to the model and keep iterating on.

Future improvements to ctxl will likely automate #4 and #5 of this process.


## How It Works

ctxl operates in several steps:
1. It scans the specified directory to detect the project type(s).
2. Based on the detected type(s) or user-specified presets, it determines which files to include or exclude.
3. It reads the contents of included files and constructs a directory structure.
4. All this information is then formatted into an XML structure, along with the specified task.
5. The resulting XML is output to stdout or a specified file.

## Usage

### Basic Usage

To use ctxl, simply run the following command in your terminal:

```bash
ctxl /path/to/your/project
```

By default, this will output the XML representation of your project to stdout. This allows for piping the output into other CLI tools, for example with [LLM](https://github.com/simonw/llm):

```bash
ctxl /path/to/your/project | llm
```

To output to a file:

```bash
ctxl /path/to/your/project > context.xml
```

or 

```bash
ctxl /path/to/your/project -o context.xml
```

### Command-line Options

ctxl offers several command-line options to customize its behavior:

- `-o, --output`: Specify the output file path (default: stdout)
- `--presets`: Choose preset project types to combine (default: auto-detect)
- `--suffixes`: Specify allowed file suffixes (overrides presets)
- `--ignore`: Add additional folders/files to ignore
- `--include-dotfiles`: Include dotfiles and folders in the output
- `--gitignore`: Specify a custom .gitignore file path
- `--task`: Include a custom task description in the output
- `--no-auto-detect`: Disable auto-detection of project types

Example:

```bash
ctxl /path/to/your/project --presets python javascript --output project_context.xml --task "Analyze this project for potential security vulnerabilities"
```

### Presets

ctxl includes presets for common project types:

- python: Includes .py, .pyi, .pyx, .ipynb files, ignores common Python-specific directories and files
- javascript: Includes .js, .jsx, .mjs, .cjs files, ignores node_modules and other JS-specific files
- typescript: Includes .ts, .tsx files, similar ignores to JavaScript
- web: Includes .html, .css, .scss, .sass, .less files
- misc: Includes common configuration and documentation file types

The tool can automatically detect project types, or you can specify them manually.

## Features

- Extracts project structure and file contents
- Supports multiple programming languages and project types
- Customizable file inclusion/exclusion
- Respects .gitignore rules
- Generates XML output for easy parsing
- Auto-detects project types
- Allows custom task specifications for LLM priming

## Output Example

Here's an example of what the XML output might look like when run on the ctxl project itself.

To generate this output, you would run:

```bash
ctxl /path/to/ctxl/repository --output ctxl_context.xml
```

The resulting `ctxl_context.xml` would look something like this:

```xml
<root>
  <project_context>
    <file path="src/ctxl/ctxl.py">
      <content>
        ...truncated for examples sake...
      </content>
    </file>
    <file path="src/ctxl/__init__.py">
      <content>
        ...truncated for examples sake...
      </content>
    </file>
    <file path="pyproject.toml">
      <content>
        ...truncated for examples sake...
      </content>
    </file>
    <directory_structure>
      <directory path=".">
        <file path="README.md" />
        <file path="pyproject.toml" />
        <directory path="src">
          <directory path="src/ctxl">
            <file path="src/ctxl/ctxl.py" />
            <file path="src/ctxl/__init__.py" />
          </directory>
        </directory>
      </directory>
    </directory_structure>
  </project_context>
  <task>Describe this project in detail. Pay special attention to the structure of the code, the design of the project, any frameworks/UI frameworks used, and the overall structure/workflow. If artifacts are available, then use workflow and sequence diagrams to help describe the project.</task>
</root>
```

The XML output provides a comprehensive view of the ctxl project, including file contents, structure, and a task description. This format allows LLMs to easily parse and understand the project context, enabling them to provide more accurate and relevant assistance.

## Project Structure

The ctxl project has the following structure:

```
ctxl/
├── src/
│   └── ctxl/
│       ├── __init__.py
│       └── ctxl.py
├── README.md
└── pyproject.toml
```

The main functionality is implemented in `src/ctxl/ctxl.py`.

## Troubleshooting

- **Issue**: ctxl is not detecting my project type correctly.
  **Solution**: Use the `--presets` option to manually specify the project type(s).

- **Issue**: ctxl is including/excluding files I don't want.
  **Solution**: Use the `--suffixes` and `--ignore` options to customize file selection.

- **Issue**: The XML output is too large for my LLM to process.
  **Solution**: Try using more specific presets or custom ignore patterns to reduce the amount of included content.

## Contributing

Contributions to ctxl are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the Apache License, Version 2.0. See the LICENSE file for details.