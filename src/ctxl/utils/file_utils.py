import os
import fnmatch


def load_gitignore(path):
    gitignore = set()
    gitignore_path = os.path.join(path, ".gitignore")
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    gitignore.add(line)
    return gitignore


def should_ignore(path, name, gitignore, ignore_dotfiles):
    if ignore_dotfiles and name.startswith("."):
        return True
    if gitignore:
        for pattern in gitignore:
            if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(
                os.path.join(path, name), pattern
            ):
                return True
    return False


def generate_tree(startpath, max_depth=3, ignore_dotfiles=True, use_gitignore=True):
    gitignore = load_gitignore(startpath) if use_gitignore else set()
    tree = []
    for root, dirs, files in os.walk(startpath):
        level = root.replace(startpath, "").count(os.sep)
        if level > max_depth:
            continue
        indent = "│   " * (level)
        tree.append(f"{indent}├── {os.path.basename(root)}/")
        subindent = "│   " * (level + 1)

        dirs[:] = [
            d for d in dirs if not should_ignore(root, d, gitignore, ignore_dotfiles)
        ]
        files = [
            f for f in files if not should_ignore(root, f, gitignore, ignore_dotfiles)
        ]

        for f in files:
            tree.append(f"{subindent}├── {f}")
    return "\n".join(tree)
