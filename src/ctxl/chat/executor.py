import logging
import subprocess
from typing import Callable, Optional, Tuple

from ..utils.diff_utils import apply_diff
from ..version_control import VersionControl

logger = logging.getLogger(__name__)


def lint_and_format_code(path: str = ".") -> str:
    command = f"ruff check --fix {path} && ruff format {path}"
    result = subprocess.run(
        command, shell=True, check=False, text=True, capture_output=True
    )
    return f"<lint_result>\n{result.stdout}\n{result.stderr}\n</lint_result>"


class CommandExecutor:
    def __init__(
        self,
        version_control: VersionControl,
        lint_func: Callable[[str], str] = lint_and_format_code,
    ):
        self.version_control = version_control
        self.lint_func = lint_func

    def execute_with_versioning(
        self,
        text: str,
        user_initiated: bool = False,
        target_path: Optional[str] = None,
        is_diff: bool = False,
        purpose: Optional[str] = None,
    ) -> str:
        try:
            if not user_initiated:
                user_confirmation = (
                    input(f"\nExecute:\n'{text}'? (y/n): ").strip().lower()
                )
                if user_confirmation not in ["y", "yes", ""]:
                    logger.info("User skipped execution.")
                    return """<result userskipped="true">\nUser skipped execution.\n</result>"""

            if user_initiated:
                text = text.removeprefix("!").strip()

            if not is_diff:
                output = self._execute_command(text, purpose)
            else:
                output = self._apply_diff(target_path, text, purpose)

            return output
        except Exception as e:
            logger.error(f"Error executing command: {str(e)}")
            return f"""<result userskipped="false">\nError: {str(e)}\n</result>"""

    def _execute_command(self, content: str, purpose: Optional[str]) -> str:
        try:
            result = subprocess.run(
                content,
                shell=True,
                check=True,
                text=True,
                capture_output=True,
                executable="/bin/bash",
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"Command execution failed: {str(e)}")
            return f"""<result userskipped="false" returncode="{e.returncode}">\n{e.stdout}\n{e.stderr}\n</result>"""

        commit_message = purpose if purpose else f"Executed command: {content}"
        commit_hash = self.version_control.create_new_version(commit_message)
        lint_result = self.lint_func()

        return f"""<result userskipped="false" returncode="{result.returncode}" commit_hash="{commit_hash}">\n{result.stdout}\n{result.stderr}\n{lint_result}</result>"""

    def _apply_diff(
        self, target_path: Optional[str], content: str, purpose: Optional[str]
    ) -> str:
        if not target_path:
            raise ValueError("Target path is required for applying diff")

        try:
            result, unified_diff = apply_diff(target_path, content)
        except Exception as e:
            logger.error(f"Failed to apply diff: {str(e)}")
            return f"""<result userskipped="false">\nError applying diff: {str(e)}\n_/result_"""

        commit_message = purpose if purpose else f"Applied diff to {target_path}"
        commit_hash = self.version_control.create_new_version(commit_message)
        lint_result = self.lint_func()

        return f"""<result userskipped="false" commit_hash="{commit_hash}"><updated_file>\n{result}\n</updated_file>\n{lint_result}</result>"""

    def execute_user_command(self, command: str) -> Tuple[bool, str]:
        return self.execute_with_versioning(command, user_initiated=True)

    def execute_diff(self, diff: str) -> Tuple[bool, str]:
        return self.execute_with_versioning(diff, is_diff=True)
