# ctxl: Contextual

ctxl is a CLI tool designed to transform project directories into a structured XML format suitable for language models and AI analysis. It extracts file contents and directory structures while respecting gitignore rules and custom filters. It creates a comprehensive project snapshot that can be easily parsed by LLMs, with a customizable task specification that primes the LLM to be a better assistant with your project.

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

This command will create an XML file containing your project's structure and file contents, which you can then provide to an LLM for analysis or assistance.

## Usage

### Basic Usage

To use ctxl, simply run the following command in your terminal:

```bash
ctxl /path/to/your/project
```

By default, this will output the XML representation of your project to stdout.

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
  <task>Describe this coding project in detail. Pay special attention to the structure of the code, the design of the project, any frameworks/UI frameworks used, and the overall structure/workflow.</task>
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

## Contributing

Contributions to ctxl are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License.