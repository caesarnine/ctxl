from typing import Dict, List, Optional

import git
from git import GitCommandError


class VersionControl:
    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        self.repo = self._initialize_repo()

    def _initialize_repo(self) -> git.Repo:
        try:
            # Try to initialize a repo or find an existing one
            repo = git.Repo(self.root_dir, search_parent_directories=True)
        except git.InvalidGitRepositoryError:
            # If no Git repo is found, create a new one in root_dir
            repo = git.Repo.init(self.root_dir)
            repo.index.commit("Initial commit")
        return repo

    def create_new_version(self, message: str, branch: Optional[str] = None) -> str:
        if branch:
            self.repo.git.checkout(branch)
        # Stage all changes
        self.repo.git.add(A=True)
        # Commit changes
        commit = self.repo.index.commit(message)
        return commit.hexsha

    def switch_to_version(self, commit_hash: str):
        try:
            self.repo.git.checkout(commit_hash)
        except GitCommandError as e:
            raise ValueError(f"Failed to switch to version {commit_hash}: {str(e)}")

    def create_branch(self, branch_name: str, start_point: Optional[str] = None):
        try:
            if start_point:
                self.repo.git.checkout(start_point, b=branch_name)
            else:
                self.repo.git.checkout(b=branch_name)
        except GitCommandError as e:
            raise ValueError(f"Failed to create branch {branch_name}: {str(e)}")

    def get_version_history(self) -> List[Dict[str, any]]:
        history = []
        for commit in self.repo.iter_commits():
            history.append(
                {
                    "id": commit.hexsha,
                    "message": commit.message.strip(),
                    "author": commit.author.name,
                    "timestamp": commit.authored_datetime.isoformat(),
                    "is_current": commit.hexsha == self.repo.head.commit.hexsha,
                }
            )
        return history

    def get_current_branch(self) -> str:
        return self.repo.active_branch.name

    def get_branches(self) -> List[str]:
        return [branch.name for branch in self.repo.branches]

    def get_diff(self, from_branch: str, to_branch: str) -> str:
        try:
            return self.repo.git.diff(f"{from_branch}...{to_branch}")
        except GitCommandError as e:
            raise ValueError(
                f"Failed to get diff between {from_branch} and {to_branch}: {str(e)}"
            )

    def get_changed_files(self, branch: str) -> List[str]:
        try:
            return self.repo.git.diff(f"main...{branch}", name_only=True).split()
        except GitCommandError as e:
            raise ValueError(
                f"Failed to get changed files for branch {branch}: {str(e)}"
            )

    def get_file_contents(self, file_path: str, branch: str) -> str:
        try:
            return self.repo.git.show(f"{branch}:{file_path}")
        except GitCommandError as e:
            raise ValueError(
                f"Failed to get contents of {file_path} in branch {branch}: {str(e)}"
            )

    def merge_branch(self, source_branch: str, target_branch: str):
        current_branch = self.get_current_branch()
        try:
            self.repo.git.checkout(target_branch)
            self.repo.git.merge(source_branch)
        except GitCommandError as e:
            raise ValueError(
                f"Failed to merge {source_branch} into {target_branch}: {str(e)}"
            )
        finally:
            self.repo.git.checkout(current_branch)

    def abort_merge(self):
        try:
            self.repo.git.merge("--abort")
        except GitCommandError as e:
            raise ValueError(f"Failed to abort merge: {str(e)}")

    def delete_branch(self, branch_name: str):
        try:
            self.repo.git.branch("-D", branch_name)
        except GitCommandError as e:
            raise ValueError(f"Failed to delete branch {branch_name}: {str(e)}")


def initialize_version_control(root_dir: str) -> VersionControl:
    return VersionControl(root_dir)
