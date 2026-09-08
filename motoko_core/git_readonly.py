"""Git inspection without repository or environment-selected executables.

This is a profile for code-owned read commands, not an arbitrary Git runner.
Explicit mutating actions have a separate execution/confirmation contract.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import time


READ_COMMANDS = frozenset({"rev-parse", "show-ref", "status", "diff", "log"})
_CONFIG = (
    "core.hooksPath=/dev/null", "core.fsmonitor=false",
    "core.untrackedCache=false", "core.attributesFile=/dev/null",
    "core.pager=cat", "color.ui=false", "log.showSignature=false",
    "diff.external=", "diff.ignoreSubmodules=all", "submodule.recurse=false",
    "gc.auto=0", "maintenance.auto=false", "protocol.allow=never",
)


def is_read_command(args: list[str]) -> bool:
    return bool(args and (args[0] in READ_COMMANDS or args == ["branch", "--show-current"]))


def _supported_arguments(args: list[str]) -> bool:
    if args in (["branch", "--show-current"], ["rev-parse", "--show-toplevel"],
                ["rev-parse", "--short=12", "HEAD"], ["status", "--porcelain=v1"],
                ["status", "--short", "--branch"],
                ["log", "--oneline", "--decorate", "-n", "12"]):
        return True
    if len(args) == 3 and args[:2] == ["rev-parse", "--verify"]:
        return bool(args[2] and not args[2].startswith("-"))
    if len(args) == 4 and args[:3] == ["show-ref", "--verify", "--quiet"]:
        return args[3].startswith("refs/heads/")
    return bool(args and args[0] == "diff" and args[1:] in (
        ["--stat"], ["--name-status"], ["--cached", "--stat"], ["--cached", "--name-status"],
    ))


def run(args: list[str], *, cwd: pathlib.Path, timeout: float = 20.0) -> subprocess.CompletedProcess:
    if not _supported_arguments(args):
        raise ValueError("unsupported read-only Git command")
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update({
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_ATTR_NOSYSTEM": "1", "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0", "GIT_NO_LAZY_FETCH": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
    })
    command = ["git", "--no-pager"]
    for setting in _CONFIG:
        command.extend(["-c", setting])
    deadline = time.monotonic() + timeout
    kwargs = dict(cwd=str(cwd), env=env, text=True, stdout=subprocess.PIPE,
                  stderr=subprocess.PIPE, check=False)
    if args[0] in {"status", "diff", "log"}:
        # Attributes can select arbitrarily named clean/process filters even
        # during status. Query names using inert config plumbing, then override
        # every configured driver. Includes and worktree config are covered.
        config = subprocess.run(
            [*command, "config", "--includes", "--null", "--name-only", "--get-regexp",
             r"^(filter\..*\.(clean|smudge|process|required)|diff\..*\.(command|textconv))$"],
            timeout=timeout, **kwargs,
        )
        if config.returncode not in (0, 1):
            return config  # Refuse inspection if the safety profile cannot be built.
        for key in sorted(set(config.stdout.split("\0")) - {""}):
            value = "false" if key.lower().endswith(".required") else ""
            command.extend(["-c", f"{key}={value}"])
    operation = list(args)
    if operation[0] in {"diff", "log"}:
        operation[1:1] = ["--no-ext-diff", "--no-textconv", "--ignore-submodules=all"]
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise subprocess.TimeoutExpired(command + operation, timeout)
    return subprocess.run([*command, *operation], timeout=remaining, **kwargs)
