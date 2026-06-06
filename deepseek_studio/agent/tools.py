"""Local tools exposed to DeepSeek Studio agent mode."""

from __future__ import annotations

import fnmatch
import os
import re
import shlex
import subprocess
import tempfile
import signal
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


TEXT_READ_BYTES = 1024 * 1024
MAX_COMMAND_OUTPUT = 200_000  # increased from 20k to 200k
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
}


@dataclass(frozen=True)
class ToolResult:
    """Result returned by a local tool."""

    ok: bool
    message: str

    def for_model(self) -> str:
        status = "OK" if self.ok else "ERROR"
        return f"{status}\n{self.message}"


@dataclass(frozen=True)
class ToolSpec:
    """Schema presented to the model."""

    name: str
    description: str
    args: dict[str, str]

    def render(self) -> str:
        args = ", ".join(f"{name}: {desc}" for name, desc in self.args.items()) or "no args"
        return f"- {self.name}: {self.description}\n  args: {args}"


class ToolRegistry:
    """Registry for filesystem and command tools."""

    def __init__(self, workspace: str | Path | None = None) -> None:
        self.workspace = Path(workspace or os.getcwd()).expanduser().resolve()
        self._tools: dict[str, tuple[ToolSpec, Callable[..., ToolResult]]] = {}
        self._register_defaults()

    def set_workspace(self, workspace: str | Path) -> None:
        path = Path(workspace).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Workspace does not exist: {path}")
        if not path.is_dir():
            raise NotADirectoryError(f"Workspace is not a directory: {path}")
        self.workspace = path

    def schema_text(self) -> str:
        return "\n".join(spec.render() for spec, _ in self._tools.values())

    def list_tool_names(self) -> list[str]:
        return sorted(self._tools)

    def execute(self, name: str, args: dict[str, Any] | None = None) -> ToolResult:
        if name not in self._tools:
            return ToolResult(False, f"Unknown tool: {name}. Available: {', '.join(self.list_tool_names())}")
        _, func = self._tools[name]
        try:
            return func(**(args or {}))
        except TypeError as exc:
            return ToolResult(False, f"Bad arguments for {name}: {exc}")
        except Exception as exc:  # noqa: BLE001 - tool errors should go back to the model
            return ToolResult(False, f"{type(exc).__name__}: {exc}")

    def _register(self, spec: ToolSpec, func: Callable[..., ToolResult]) -> None:
        self._tools[spec.name] = (spec, func)

    def _register_defaults(self) -> None:
        self._register(
            ToolSpec(
                "workspace_info",
                "Show the current workspace path and basic project files.",
                {},
            ),
            self.workspace_info,
        )
        self._register(
            ToolSpec(
                "list_files",
                "List files and directories under a workspace-relative path.",
                {
                    "path": "workspace-relative directory, default '.'",
                    "max_depth": "integer depth, default 2",
                    "include_hidden": "boolean, default false",
                    "limit": "maximum entries, default 200",
                },
            ),
            self.list_files,
        )
        self._register(
            ToolSpec(
                "read_file",
                "Read a text file with line numbers.",
                {
                    "path": "workspace-relative file path",
                    "start_line": "1-based start line, default 1",
                    "max_lines": "maximum lines, default 240",
                },
            ),
            self.read_file,
        )
        self._register(
            ToolSpec(
                "write_file",
                "Create or overwrite a text file.",
                {
                    "path": "workspace-relative file path",
                    "content": "complete file contents",
                    "create_dirs": "boolean, default true",
                },
            ),
            self.write_file,
        )
        self._register(
            ToolSpec(
                "edit_file",
                "Replace text in an existing file. Errors if old text is missing or ambiguous.",
                {
                    "path": "workspace-relative file path",
                    "old": "exact text to replace",
                    "new": "replacement text",
                    "replace_all": "boolean, default false",
                },
            ),
            self.edit_file,
        )
        self._register(
            ToolSpec(
                "mkdir",
                "Create a directory inside the workspace.",
                {"path": "workspace-relative directory path"},
            ),
            self.mkdir,
        )
        self._register(
            ToolSpec(
                "delete_path",
                "Delete a file or empty directory inside the workspace.",
                {
                    "path": "workspace-relative path",
                    "recursive": "boolean for directories, default false",
                },
            ),
            self.delete_path,
        )
        self._register(
            ToolSpec(
                "search_files",
                "Search text files for a literal or regex query.",
                {
                    "query": "literal text or regex pattern",
                    "path": "workspace-relative directory, default '.'",
                    "glob": "file glob, default '*'",
                    "regex": "boolean, default false",
                    "max_matches": "maximum matches, default 80",
                },
            ),
            self.search_files,
        )
        self._register(
            ToolSpec(
                "run_command",
                "Run a shell command in the workspace with enhanced robustness: supports environment variables, working directory override, graceful timeout (SIGTERM then SIGKILL), UTF-8 error handling, large output (up to 200KB), and configurable safety checks.",
                {
                    "command": "shell command string (can be multi-line or use &&, |, etc.)",
                    "timeout": "seconds before kill, default 30, max 300",
                    "max_output_chars": "combined stdout/stderr cap, default 50000, max 200000",
                    "env": "optional dict of environment variables to set (e.g., {'PATH': '/custom/bin'})",
                    "cwd": "optional working directory relative to workspace (default workspace root)",
                    "allow_dangerous": "boolean, bypass safety checks if true (default false)",
                },
            ),
            self.run_command,
        )
        self._register(
            ToolSpec(
                "apply_patch",
                "Apply a unified diff using git apply.",
                {"patch": "unified diff text"},
            ),
            self.apply_patch,
        )
        # Git tools
        self._register(
            ToolSpec(
                "git_status",
                "Show the working tree status.",
                {},
            ),
            self.git_status,
        )
        self._register(
            ToolSpec(
                "git_diff",
                "Show differences between commits, working tree, etc.",
                {
                    "paths": "optional paths to diff (default empty for all)",
                    "staged": "boolean, diff staged changes only, default false",
                },
            ),
            self.git_diff,
        )
        self._register(
            ToolSpec(
                "git_add",
                "Add file contents to the index.",
                {
                    "paths": "paths to add, default '.'",
                    "all_changes": "boolean, add all changes (including deletions), default false",
                },
            ),
            self.git_add,
        )
        self._register(
            ToolSpec(
                "git_commit",
                "Commit changes to the repository.",
                {
                    "message": "commit message (required)",
                    "all_changes": "boolean, automatically stage all tracked files, default false",
                },
            ),
            self.git_commit,
        )
        self._register(
            ToolSpec(
                "git_pull",
                "Pull changes from a remote repository.",
                {
                    "remote": "remote name, default 'origin'",
                    "branch": "branch name, optional",
                },
            ),
            self.git_pull,
        )
        self._register(
            ToolSpec(
                "git_push",
                "Push changes to a remote repository.",
                {
                    "remote": "remote name, default 'origin'",
                    "branch": "branch name, optional",
                    "force": "boolean, force push, default false",
                },
            ),
            self.git_push,
        )
        self._register(
            ToolSpec(
                "git_log",
                "Show commit logs.",
                {
                    "count": "number of commits to show, default 10, max 100",
                    "oneline": "boolean, show each commit on one line, default true",
                },
            ),
            self.git_log,
        )
        self._register(
            ToolSpec(
                "git_branch",
                "List or show branches.",
                {
                    "list_all": "boolean, list both local and remote branches, default false",
                },
            ),
            self.git_branch,
        )
        self._register(
            ToolSpec(
                "git_checkout",
                "Switch branches or restore working tree files.",
                {
                    "target": "branch name or commit hash to switch to",
                    "new_branch": "optional, create and switch to a new branch",
                },
            ),
            self.git_checkout,
        )

    # ---------- Workspace tools ----------

    def workspace_info(self) -> ToolResult:
        files = []
        for name in ("pyproject.toml", "package.json", "requirements.txt", "README.md", "Makefile", ".git"):
            if (self.workspace / name).exists():
                files.append(name)
        return ToolResult(True, f"Workspace: {self.workspace}\nDetected: {', '.join(files) if files else 'no common project markers'}")

    def list_files(
        self,
        path: str = ".",
        max_depth: int = 2,
        include_hidden: bool = False,
        limit: int = 200,
    ) -> ToolResult:
        root = self._safe_path(path)
        if not root.exists():
            return ToolResult(False, f"Path does not exist: {path}")
        if not root.is_dir():
            return ToolResult(False, f"Path is not a directory: {path}")

        max_depth = max(0, min(int(max_depth), 8))
        limit = max(1, min(int(limit), 1000))
        rows: list[str] = []
        count = 0
        base_depth = len(root.relative_to(self.workspace).parts)

        for current, dirs, files in os.walk(root):
            current_path = Path(current)
            rel_parts = current_path.relative_to(self.workspace).parts
            depth = len(rel_parts) - base_depth
            if depth > max_depth:
                dirs[:] = []
                continue
            dirs[:] = sorted(
                d for d in dirs if self._include_entry(d, include_hidden)
            )
            visible_files = sorted(f for f in files if self._include_entry(f, include_hidden))
            indent = "  " * depth
            rel_dir = self._rel(current_path)
            if depth == 0:
                rows.append(f"{rel_dir}/")
            for dirname in dirs:
                if count >= limit:
                    break
                rows.append(f"{indent}  {dirname}/")
                count += 1
            for filename in visible_files:
                if count >= limit:
                    break
                rows.append(f"{indent}  {filename}")
                count += 1
            if count >= limit:
                rows.append(f"... truncated at {limit} entries")
                break

        return ToolResult(True, "\n".join(rows) if rows else "No files found.")

    def read_file(self, path: str, start_line: int = 1, max_lines: int = 240) -> ToolResult:
        file_path = self._safe_path(path)
        if not file_path.exists():
            return ToolResult(False, f"File does not exist: {path}")
        if not file_path.is_file():
            return ToolResult(False, f"Path is not a file: {path}")
        if self._looks_binary(file_path):
            return ToolResult(False, f"Refusing to read binary file: {path}")

        start_line = max(1, int(start_line))
        max_lines = max(1, min(int(max_lines), 1000))
        text = file_path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        start_idx = start_line - 1
        selected = lines[start_idx : start_idx + max_lines]
        numbered = [f"{idx:>5}: {line}" for idx, line in enumerate(selected, start=start_line)]
        suffix = ""
        if start_idx + max_lines < len(lines):
            suffix = f"\n... {len(lines) - (start_idx + max_lines)} more lines"
        return ToolResult(True, f"{self._rel(file_path)} ({len(lines)} lines)\n" + "\n".join(numbered) + suffix)

    def write_file(self, path: str, content: str, create_dirs: bool = True) -> ToolResult:
        file_path = self._safe_path(path)
        if file_path.exists() and file_path.is_dir():
            return ToolResult(False, f"Path is a directory: {path}")
        if create_dirs:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        elif not file_path.parent.exists():
            return ToolResult(False, f"Parent directory does not exist: {self._rel(file_path.parent)}")
        file_path.write_text(str(content), encoding="utf-8")
        return ToolResult(True, f"Wrote {len(str(content))} characters to {self._rel(file_path)}")

    def edit_file(self, path: str, old: str, new: str, replace_all: bool = False) -> ToolResult:
        file_path = self._safe_path(path)
        if not file_path.exists() or not file_path.is_file():
            return ToolResult(False, f"File does not exist: {path}")
        if self._looks_binary(file_path):
            return ToolResult(False, f"Refusing to edit binary file: {path}")
        text = file_path.read_text(encoding="utf-8", errors="replace")
        old = str(old)
        new = str(new)
        count = text.count(old)
        if count == 0:
            return ToolResult(False, "Old text was not found in file.")
        if count > 1 and not replace_all:
            return ToolResult(False, f"Old text appears {count} times. Set replace_all=true or provide a more specific old string.")
        updated = text.replace(old, new) if replace_all else text.replace(old, new, 1)
        file_path.write_text(updated, encoding="utf-8")
        changed = count if replace_all else 1
        return ToolResult(True, f"Edited {self._rel(file_path)} ({changed} replacement{'s' if changed != 1 else ''}).")

    def mkdir(self, path: str) -> ToolResult:
        dir_path = self._safe_path(path)
        dir_path.mkdir(parents=True, exist_ok=True)
        return ToolResult(True, f"Created directory {self._rel(dir_path)}")

    def delete_path(self, path: str, recursive: bool = False) -> ToolResult:
        target = self._safe_path(path)
        if not target.exists():
            return ToolResult(False, f"Path does not exist: {path}")
        if target == self.workspace:
            return ToolResult(False, "Refusing to delete the workspace root.")
        if target.is_dir():
            if recursive:
                import shutil
                shutil.rmtree(target)
                return ToolResult(True, f"Deleted directory tree {self._rel(target)}")
            target.rmdir()
            return ToolResult(True, f"Deleted empty directory {self._rel(target)}")
        target.unlink()
        return ToolResult(True, f"Deleted file {self._rel(target)}")

    def search_files(
        self,
        query: str,
        path: str = ".",
        glob: str = "*",
        regex: bool = False,
        max_matches: int = 80,
    ) -> ToolResult:
        root = self._safe_path(path)
        if not root.exists() or not root.is_dir():
            return ToolResult(False, f"Search path is not a directory: {path}")
        max_matches = max(1, min(int(max_matches), 500))
        pattern = re.compile(query) if regex else None
        matches: list[str] = []

        for file_path in sorted(root.rglob("*")):
            if len(matches) >= max_matches:
                break
            if not file_path.is_file() or self._should_skip_path(file_path):
                continue
            rel = self._rel(file_path)
            if not fnmatch.fnmatch(rel, glob):
                continue
            if self._looks_binary(file_path):
                continue
            try:
                lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for idx, line in enumerate(lines, start=1):
                found = bool(pattern.search(line)) if pattern else query in line
                if found:
                    matches.append(f"{rel}:{idx}: {line[:300]}")
                    if len(matches) >= max_matches:
                        break

        if not matches:
            return ToolResult(True, "No matches.")
        suffix = "" if len(matches) < max_matches else f"\n... truncated at {max_matches} matches"
        return ToolResult(True, "\n".join(matches) + suffix)

    # ---------- Enhanced run_command ----------

    def run_command(
        self,
        command: str,
        timeout: int = 30,
        max_output_chars: int = 50_000,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        allow_dangerous: bool = False,
    ) -> ToolResult:
        """Run a shell command in the workspace with robust error handling.

        Improvements over original:
        - Handles UTF-8 decode errors gracefully
        - SIGTERM then SIGKILL on timeout
        - Configurable environment variables
        - Configurable working directory
        - Larger output limits (up to 200KB)
        - More precise dangerous command filtering with bypass
        - Returns structured error messages
        - Never crashes the agent
        """
        command = str(command).strip()
        if not command:
            return ToolResult(False, "Command is empty.")

        # Safety check
        if not allow_dangerous:
            dangerous = self._dangerous_command_reason(command)
            if dangerous:
                return ToolResult(False, dangerous)

        # Timeout and output limits
        timeout = max(1, min(int(timeout), 300))  # increased max to 5 minutes
        max_output_chars = max(1000, min(int(max_output_chars), MAX_COMMAND_OUTPUT))

        # Prepare environment: inherit current os.environ plus user overrides
        final_env = os.environ.copy()
        if env:
            final_env.update(env)

        # Determine working directory
        if cwd:
            working_dir = self._safe_path(cwd)
            if not working_dir.exists():
                return ToolResult(False, f"Working directory does not exist: {cwd}")
            if not working_dir.is_dir():
                return ToolResult(False, f"Working directory is not a directory: {cwd}")
        else:
            working_dir = self.workspace

        try:
            # Use Popen for better control
            proc = subprocess.Popen(
                command,
                shell=True,
                cwd=working_dir,
                env=final_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,  # capture as bytes to handle encoding ourselves
                executable='/bin/bash' if os.name != 'nt' else None,  # use bash on Unix for better compatibility
            )

            # Wait with timeout, then send SIGTERM, then SIGKILL
            try:
                stdout_bytes, stderr_bytes = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                # First try SIGTERM
                proc.terminate()
                try:
                    stdout_bytes, stderr_bytes = proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill
                    proc.kill()
                    stdout_bytes, stderr_bytes = proc.communicate()
                return ToolResult(
                    False,
                    f"Command timed out after {timeout}s and was terminated.\n"
                    f"$ {command}\n"
                    f"Partial output:\n{_decode_output(stdout_bytes, max_output_chars)}"
                )

            # Decode with error handling
            stdout = _decode_output(stdout_bytes, max_output_chars)
            stderr = _decode_output(stderr_bytes, max_output_chars)

            # Build result message
            message_parts = [f"$ {command}", f"exit_code: {proc.returncode}"]
            if stdout:
                message_parts.append(f"\nstdout:\n{stdout}")
            if stderr:
                message_parts.append(f"\nstderr:\n{stderr}")
            message = "".join(message_parts)

            return ToolResult(proc.returncode == 0, message)

        except OSError as e:
            return ToolResult(False, f"Failed to execute command (OS error): {e}")
        except Exception as e:
            # Catch-all to prevent agent crash
            return ToolResult(False, f"Unexpected error running command: {type(e).__name__}: {e}")

    def apply_patch(self, patch: str) -> ToolResult:
        patch = str(patch)
        if not patch.strip():
            return ToolResult(False, "Patch is empty.")
        invalid = self._validate_patch_paths(patch)
        if invalid:
            return ToolResult(False, invalid)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write(patch)
            patch_path = handle.name
        try:
            check = subprocess.run(
                ["git", "apply", "--check", patch_path],
                cwd=self.workspace,
                text=True,
                capture_output=True,
                timeout=30,
            )
            if check.returncode != 0:
                return ToolResult(False, "git apply --check failed\n" + _clip(check.stderr or check.stdout, 8000))
            apply = subprocess.run(
                ["git", "apply", patch_path],
                cwd=self.workspace,
                text=True,
                capture_output=True,
                timeout=30,
            )
            if apply.returncode != 0:
                return ToolResult(False, "git apply failed\n" + _clip(apply.stderr or apply.stdout, 8000))
            return ToolResult(True, "Patch applied successfully.")
        finally:
            try:
                os.unlink(patch_path)
            except OSError:
                pass

    # ---------- Git tools ----------

    def _git_command(self, args: list[str], timeout: int = 30) -> tuple[bool, str]:
        """Run a git command and return (success, output)."""
        try:
            proc = subprocess.run(
                ["git"] + args,
                cwd=self.workspace,
                text=True,
                capture_output=True,
                timeout=timeout,
            )
            output = proc.stdout.strip()
            if proc.stderr:
                output += "\n" + proc.stderr.strip()
            return proc.returncode == 0, output
        except subprocess.TimeoutExpired as exc:
            return False, f"Command timed out after {timeout}s: git {' '.join(args)}"
        except FileNotFoundError:
            return False, "Git is not installed or not in PATH."

    def git_status(self) -> ToolResult:
        ok, output = self._git_command(["status", "--short"])
        if not ok:
            return ToolResult(False, f"git status failed: {output}")
        return ToolResult(True, output if output else "Working tree clean.")

    def git_diff(self, paths: str = "", staged: bool = False) -> ToolResult:
        args = ["diff"]
        if staged:
            args.append("--staged")
        if paths:
            args.append(paths)
        ok, output = self._git_command(args, timeout=30)
        if not ok:
            return ToolResult(False, f"git diff failed: {output}")
        if not output:
            return ToolResult(True, "No differences.")
        if len(output) > 12000:
            output = output[:12000] + "\n... (truncated)"
        return ToolResult(True, output)

    def git_add(self, paths: str = ".", all_changes: bool = False) -> ToolResult:
        if all_changes:
            args = ["add", "-A"]
        else:
            args = ["add", paths]
        ok, output = self._git_command(args)
        if not ok:
            return ToolResult(False, f"git add failed: {output}")
        return ToolResult(True, f"Added {paths if not all_changes else 'all changes'}.")

    def git_commit(self, message: str, all_changes: bool = False) -> ToolResult:
        if not message.strip():
            return ToolResult(False, "Commit message cannot be empty.")
        args = ["commit", "-m", message]
        if all_changes:
            args.insert(1, "-a")
        ok, output = self._git_command(args)
        if not ok:
            return ToolResult(False, f"git commit failed: {output}")
        return ToolResult(True, f"Committed: {message}")

    def git_pull(self, remote: str = "origin", branch: str = "") -> ToolResult:
        args = ["pull", remote]
        if branch:
            args.append(branch)
        ok, output = self._git_command(args, timeout=60)
        if not ok:
            return ToolResult(False, f"git pull failed: {output}")
        return ToolResult(True, output if output else "Pull completed.")

    def git_push(self, remote: str = "origin", branch: str = "", force: bool = False) -> ToolResult:
        args = ["push", remote]
        if branch:
            args.append(branch)
        if force:
            args.append("--force")
        ok, output = self._git_command(args, timeout=60)
        if not ok:
            return ToolResult(False, f"git push failed: {output}")
        return ToolResult(True, output if output else "Push completed.")

    def git_log(self, count: int = 10, oneline: bool = True) -> ToolResult:
        count = max(1, min(int(count), 100))
        args = ["log", f"-n{count}"]
        if oneline:
            args.append("--oneline")
        ok, output = self._git_command(args)
        if not ok:
            return ToolResult(False, f"git log failed: {output}")
        if not output:
            return ToolResult(True, "No commits.")
        return ToolResult(True, output)

    def git_branch(self, list_all: bool = False) -> ToolResult:
        args = ["branch"]
        if list_all:
            args.append("-a")
        ok, output = self._git_command(args)
        if not ok:
            return ToolResult(False, f"git branch failed: {output}")
        return ToolResult(True, output if output else "No branches.")

    def git_checkout(self, target: str, new_branch: str = "") -> ToolResult:
        args = ["checkout"]
        if new_branch:
            args.extend(["-b", new_branch])
        else:
            args.append(target)
        ok, output = self._git_command(args)
        if not ok:
            return ToolResult(False, f"git checkout failed: {output}")
        if new_branch:
            return ToolResult(True, f"Created and switched to branch '{new_branch}'.")
        return ToolResult(True, f"Switched to '{target}'.")

    # ---------- Helpers ----------

    def _safe_path(self, path: str | Path) -> Path:
        raw = Path(str(path)).expanduser()
        candidate = raw if raw.is_absolute() else self.workspace / raw
        resolved = candidate.resolve()
        if resolved != self.workspace and self.workspace not in resolved.parents:
            raise ValueError(f"Path escapes workspace: {path}")
        return resolved

    def _rel(self, path: Path) -> str:
        try:
            rel = path.resolve().relative_to(self.workspace)
        except ValueError:
            return str(path)
        return "." if str(rel) == "." else str(rel)

    def _include_entry(self, name: str, include_hidden: bool) -> bool:
        if name in SKIP_DIRS:
            return False
        if not include_hidden and name.startswith("."):
            return False
        return True

    def _should_skip_path(self, path: Path) -> bool:
        rel_parts = path.relative_to(self.workspace).parts
        return any(part in SKIP_DIRS or part.startswith(".") for part in rel_parts[:-1])

    def _looks_binary(self, path: Path) -> bool:
        if path.stat().st_size > TEXT_READ_BYTES:
            return True
        try:
            chunk = path.read_bytes()[:4096]
        except OSError:
            return True
        return b"\0" in chunk

    def _dangerous_command_reason(self, command: str) -> str | None:
        """Block only truly destructive commands. Allow curl|sh but warn? Keep simple for now."""
        # Allow bypass via environment variable
        if os.environ.get("DEEPSEEK_STUDIO_ALLOW_DANGEROUS") == "1":
            return None

        lowered = command.lower()
        # Very dangerous patterns (rm -rf /, dd destructive, format, shutdown)
        blocked_patterns = [
            r"\brm\s+-[^;|&]*r[^;|&]*f[^;|&]*\s+(/|~/|/\*|\.\.)",  # rm -rf / or ~ or ..
            r"\bmkfs\b",
            r"\bdd\s+if=.*of=/dev/",
            r"\bshutdown\b",
            r"\breboot\b",
            r":\s*\(\s*\)\s*\{",  # fork bomb
            r"\bcurl\b.*\|\s*(sh|bash|zsh)",  # curl-pipe-sh is dangerous but not always malicious
            r"\bwget\b.*\|\s*(sh|bash|zsh)",
        ]
        for pattern in blocked_patterns:
            if re.search(pattern, lowered):
                return (
                    "Command blocked by safety guard. If you trust this command, "
                    "set allow_dangerous=true or start with DEEPSEEK_STUDIO_ALLOW_DANGEROUS=1."
                )
        # Block privilege escalation
        try:
            parts = shlex.split(command)
        except ValueError:
            return None
        if parts and parts[0] in {"sudo", "su"}:
            return "Privilege escalation commands (sudo, su) are disabled for safety."
        return None

    def _validate_patch_paths(self, patch: str) -> str | None:
        paths: list[str] = []
        for line in patch.splitlines():
            if line.startswith("diff --git "):
                pieces = line.split()
                paths.extend(pieces[2:4])
            elif line.startswith("--- ") or line.startswith("+++ "):
                paths.append(line.split(maxsplit=1)[1].split("\t", 1)[0])
        for raw in paths:
            if raw == "/dev/null":
                continue
            cleaned = raw
            if cleaned.startswith("a/") or cleaned.startswith("b/"):
                cleaned = cleaned[2:]
            if cleaned.startswith("/") or ".." in Path(cleaned).parts:
                return f"Patch path escapes workspace: {raw}"
        return None


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return text[:limit] + f"\n... (truncated, {omitted} characters omitted)"


def _decode_output(data: bytes | None, max_chars: int) -> str:
    """Safely decode bytes to string, replace invalid chars."""
    if data is None:
        return ""
    # Decode with replacement, then clip
    try:
        decoded = data.decode("utf-8", errors="replace")
    except Exception:
        # Fallback to ascii with replacement
        decoded = data.decode("ascii", errors="replace")
    if len(decoded) > max_chars:
        decoded = decoded[:max_chars] + f"\n... (truncated, {len(decoded) - max_chars} characters omitted)"
    return decoded
