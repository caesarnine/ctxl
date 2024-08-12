import argparse
import logging
import os
import sys

from .chat.chat import ChatMode, Config
from .ctxl import (
    combine_presets,
    detect_project_types,
    generate_xml,
    parse_filter_patterns,
)
from .preset_manager import get_presets, load_presets
from .version_control import VersionControl

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool):
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(levelname)s - %(message)s"
    )


def chat_command(args):
    version_control = VersionControl(".")
    config = Config()
    chat = ChatMode(
        config=config, bedrock=args.bedrock, version_control=version_control
    )
    chat.start()


def generate_command(args):
    # Set the default gitignore path if not provided
    if args.gitignore is None:
        args.gitignore = os.path.join(args.folder_path, ".gitignore")

    # Load presets from the directory
    current_dir_presets = load_presets(
        os.path.join(args.folder_path, "ctxl_presets.yaml")
    )
    if current_dir_presets:
        logger.info("Loaded custom presets from the project directory.")

    # Auto-detect project types if not disabled and no presets specified
    if not args.no_auto_detect and not args.presets:
        detected_types = detect_project_types(args.folder_path)
        if detected_types:
            logger.info(f"Detected project types: {', '.join(detected_types)}")
            args.presets = list(detected_types)
        else:
            logger.info(
                "No specific project types detected. No presets will be applied."
            )
            args.presets = []
    elif not args.presets:
        args.presets = []

    # Parse filter patterns
    filter_patterns = parse_filter_patterns(args.filter or "")

    # Combine presets and apply filters
    combined_preset = combine_presets(args.presets, filter_patterns)

    # Remove the default dotfile exclude if --include-dotfiles is specified
    if args.include_dotfiles:
        combined_preset["exclude"] = [
            pattern for pattern in combined_preset["exclude"] if pattern != ".*"
        ]
        logger.debug("Included dotfiles in the output")

    # Generate XML
    xml_output = generate_xml(
        args.folder_path,
        combined_preset["include"],
        combined_preset["exclude"],
        args.gitignore,
        args.task,
        args.include_dotfiles,
    )

    # Output XML
    if args.output == "-":
        output = sys.stdout
    else:
        output = args.output

    if isinstance(output, str):
        with open(output, "w", encoding="utf-8") as f:
            f.write(xml_output)
        logger.info(f"Output written to file: {output}")
    else:
        output.write(xml_output)
        logger.info("Output written to stdout")


def add_common_arguments(parser):
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--bedrock",
        action="store_true",
        help="Use AWS Bedrock for Claude API in interactive mode",
    )


def main():
    parser = argparse.ArgumentParser(description="Contextual CLI tool")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Chat command
    chat_parser = subparsers.add_parser(
        "chat", help="Start an interactive chat session"
    )
    add_common_arguments(chat_parser)

    # Generate command
    generate_parser = subparsers.add_parser(
        "generate", help="Generate project structure and content"
    )
    generate_parser.add_argument(
        "folder_path", help="Path to the folder to be analyzed"
    )
    generate_parser.add_argument(
        "-o", "--output", help="Path to the output file (default: stdout)", default="-"
    )
    generate_parser.add_argument(
        "--presets",
        nargs="+",
        choices=list(get_presets().keys()),
        help="Preset project types to combine (default: auto-detect)",
    )
    generate_parser.add_argument(
        "--filter",
        type=str,
        help="Filter patterns to include or exclude files. Use '!' to exclude. Example: --filter '*.py !__pycache__ !*.pyc'",
    )
    generate_parser.add_argument(
        "--include-dotfiles",
        action="store_true",
        help="Include dotfiles and folders in the output",
    )
    generate_parser.add_argument(
        "--gitignore",
        help="Path to the .gitignore file (default: .gitignore in the folder_path)",
        default=None,
    )
    generate_parser.add_argument(
        "--task",
        help="Task description to be included in the output",
        default="Describe this project in detail. Pay special attention to the structure of the code, the design of the project, any frameworks/UI frameworks used, and the overall structure/workflow. If artifacts are available, then display workflow and sequence diagrams to help describe the project.",
    )
    generate_parser.add_argument(
        "--no-auto-detect",
        action="store_true",
        help="Disable auto-detection of project types",
    )
    add_common_arguments(generate_parser)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    setup_logging(args.verbose)

    if args.command == "chat":
        chat_command(args)
    elif args.command == "generate":
        generate_command(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
