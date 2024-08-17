# ctxl: Contextual

[![PyPI version](https://badge.fury.io/py/ctxl.svg)](https://badge.fury.io/py/ctxl)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

ctxl is a CLI tool that combines project analysis with an interactive chat that can edit files and run commands. 

ctxl intelligently extracts file contents and directory structures while respecting gitignore rules and custom filters, and automatically detecting project types (such as Python, or Javascript, etc) to make smart decisions about what to include and exclude.

This dumps the project context in a format that can be easily parsed by LLMs, and can then be used to power an interactive chat session, allowing developers to get targeted, context-aware assistance with their projects.

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

ctxl streamlines the process of providing project context to LLMs and interacting with them for project-specific assistance. The LLM can use this rich context to generate better code, and the interactive chat allows it to run commands and edit files while also getting feedback on errors/issues.


## Installation

To install ctxl, you can use pip:

```bash
pip install ctxl
```

## Quick Start

After installation, you can quickly start using ctxl:

1. Generate your project context and drop into chat:
```bash
ctxl generate . | ctxl chat
```

2. Generate only the context and dump it to stdout or file.

```bash
ctxl /path/to/your/project > project_context.xml
```

This command will create an XML file which includes file contents, directory structure, and a default task description.

3. Start an interactive chat session:

```bash
ctxl chat
```

Start an interactive session with no initial context. The chatbot can still run commands and edit files.

### Workflow

Here's a typical workflow for using ctxl:

1. Start the chat session with `ctxl generate /path/to/your/project | ctxl chat`
2. ctxl will analyze your project and provide a summary, giving you a chance to confirm or adjust the context.
3. Begin chatting with the AI. You can ask questions, request code changes, or seek advice. For example:
   > "I'd like to update the frontend to show live progress when the backend is processing documents."
4. The AI will respond, including commands or diffs to modify your project.
5. You can review the suggestions, accept them or deny them, or continue chatting.
6. Continue this iterative process as you work on your project.

## Usage

### Basic Usage

#### Generate
```bash
ctxl /path/to/your/project
```

By default, this will output the XML representation of your project to stdout. You can pipe that into another tool (ctxl chat for example.)

```bash
ctxl /path/to/your/project | ctxl chat
```

To output to a file:

```bash
ctxl /path/to/your/project > context.xml
```

To start a chat session with no inital context.

```bash
ctxl chat
```

### Chat Mode Usage

In chat mode, you can interact with the AI assistant using natural language. Here are some example interactions:

1. Ask for a project summary: "Can you give me an overview of this project?"
2. Request code changes: "I need to add error handling to the main function in app.py"
3. Seek advice: "What's the best way to implement user authentication in this Flask app?"
4. Debug issues: "I'm getting a KeyError in this function. Can you help me fix it?"
5. Propose new features: "How can I add a caching layer to improve performance?"

### Command-line Options

ctxl has two main commands: `generate` and `chat`. Each command has its own set of options.

#### Generate Command

The `generate` command analyzes a project and produces an XML representation of its structure and contents.

Options:
- `-o, --output`: Specify the output file path (default: stdout)
- `--presets`: Choose preset project types to combine (default: auto-detect)
- `--filter`: Filter patterns to include or exclude (!) files. Example: `'*.py !__pycache__'`
- `--include-dotfiles`: Include dotfiles and folders in the output
- `--gitignore`: Specify a custom .gitignore file path
- `--task`: Include a custom task description in the output
- `--no-auto-detect`: Disable auto-detection of project types
- `--analyze-deps`: Analyze project dependencies (default: True)
- `-v, --verbose`: Enable verbose logging for more detailed output

#### Chat Command

The `chat` command starts an interactive chat session with an AI assistant.

Options:
- `-m, --message`: Initial message to send to the assistant
- `--model`: Specify the AI model to use for chat (default: claude-3-5-sonnet-20240620)
- `-v, --verbose`: Enable verbose logging for more detailed output

#### Global Options

These options are available for both commands:

- `--view-presets`: Display all available presets (both built-in and custom)
- `--save-presets`: Save the built-in presets to a YAML file for easy customization
- `--bedrock`: Use AWS Bedrock for Claude API in interactive mode

### Examples

1. Generate context and start a chat session:

Generate context with existing presets with additional filters to include `.log` and `.txt` and exclude a `temp` directory.

```bash
ctxl /path/to/your/project --presets python javascript --output project_context.xml --task "Analyze this project for potential security vulnerabilities" --filter *.log *.txt !temp | ctxl chat
```

2. Generate context without any presets and fully control what to include/exclude:

```bash
ctxl /path/to/your/project --no-auto-detect --output project_context.xml --task "Analyze this project for potential security vulnerabilities" --filter *.py *.js *.md !node_modules | ctxl chat
```

3. Start a chat session with an initial message:

```bash
ctxl chat -m "How can I optimize the performance of my Python web application?"
```

To view all available presets:

```bash
ctxl --view-presets
```

To save the built-in presets to a YAML file. You can then modify these/add your own, if this file exists in the directory you're running ctxl on then they'll automatically be loaded in and used instead of the defaults.

```bash
ctxl --save-presets
```

To enable verbose logging:

```bash
ctxl /path/to/your/project -v
```

### Presets

ctxl generate includes presets for common project types:

- python: Includes .py, .pyi, .pyx, .ipynb files, ignores common Python-specific directories and files
- javascript: Includes .js, .jsx, .mjs, .cjs files, ignores node_modules and other JS-specific files
- typescript: Includes .ts, .tsx files, similar ignores to JavaScript
- web: Includes .html, .css, .scss, .sass, .less, .vue files
- java: Includes .java files, ignores common Java build directories
- csharp: Includes .cs, .csx, .csproj files, ignores common C# build artifacts
- go: Includes .go files, ignores vendor directory
- ruby: Includes .rb, .rake, .gemspec files, ignores bundle-related directories
- php: Includes .php files, ignores vendor directory
- rust: Includes .rs files, ignores target directory and Cargo.lock
- swift: Includes .swift files, ignores .build and Packages directories
- kotlin: Includes .kt, .kts files, ignores common Kotlin/Java build directories
- scala: Includes .scala, .sc files, ignores common Scala build directories
- docker: Includes Dockerfile, .dockerignore, and docker-compose files
- misc: Includes common configuration and documentation file types

The tool automatically detects project types, but you can also specify them manually using the `--presets` option.

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
    <dependencies>
      <file path="src.ctxl.ctxl">
        <upstream>
          <external>
            <dependency>argparse</dependency>
            <dependency>logging</dependency>
            ...
          </external>
          <internal>
            <dependency>src.ctxl.dependency_analyzer</dependency>
            <dependency>src.ctxl.preset_manager</dependency>
          </internal>
        </upstream>
        <downstream />
      </file>
      ...
    </dependencies>
  </project_context>
  <task>Describe this project in detail. Pay special attention to the structure of the code, the design of the project, any frameworks/UI frameworks used, and the overall structure/workflow. If artifacts are available, then use workflow and sequence diagrams to help describe the project.</task>
</root>
```

The XML output provides a comprehensive view of the ctxl project, including file contents, structure, dependencies, and a task description. This format allows LLMs to easily parse and understand the project context, enabling them to provide more accurate and relevant assistance.

## Project Structure

The ctxl project has the following structure:

```
src/ctxl/
├── __init__.py
├── ctxl.py
├── cli.py
├── preset_manager.py
├── version_control.py
├── system_prompt.txt
├── chat/
│   ├── __init__.py
│   ├── ai_client.py
│   ├── chat.py
│   ├── executor.py
│   └── session.py
└── utils/
    ├── __init__.py
    ├── diff_utils.py
    ├── file_utils.py
    └── snapshot_utils.py
```

The main functionality is implemented across several files:

- `ctxl.py`: Core functionality for project analysis and XML generation
- `cli.py`: Command-line interface handling
- `preset_manager.py`: Manages project type presets
- `version_control.py`: Handles version control integration
- `chat/`: Directory containing chat-related functionality
  - `ai_client.py`: Handles communication with AI models
  - `chat.py`: Implements the chat interface and logic
  - `executor.py`: Executes commands and applies changes suggested by AI
  - `session.py`: Manages chat sessions and history
- `utils/`: Directory containing utility functions
  - `diff_utils.py`: Utilities for handling diffs
  - `file_utils.py`: File-related utility functions
  - `snapshot_utils.py`: Functions for creating project snapshots

The `system_prompt.txt` file contains the system prompt used to initialize the AI model for chat sessions.

## Troubleshooting

- **Issue**: ctxl is not detecting my project type correctly.
  **Solution**: Use the `--presets` option to manually specify the project type(s).

- **Issue**: ctxl is including/excluding files I don't want.
  **Solution**: Use the `--filter` option, if you want full control use `--filter` with `--no-auto-detect`.

- **Issue**: The XML output is too large for my LLM to process.
  **Solution**: Try using more specific presets or custom ignore patterns to reduce the amount of included content.

- **Issue**: I need more information about what ctxl is doing.
  **Solution**: Use the `-v` or `--verbose` flag to enable verbose logging for more detailed output.

- **Issue**: The dependency analysis is not working or is causing errors.
  **Solution**: You can disable dependency analysis with `--analyze-deps false` if it's causing issues.

- **Issue**: The chat functionality is not working as expected.
  **Solution**: Make sure you have the required dependencies installed and check the logs for any error messages. You can also try updating to the latest version of ctxl.

## Contributing

Contributions to ctxl are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the Apache License, Version 2.0. See the LICENSE file for details.