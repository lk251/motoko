"""Deterministic source-code intelligence for Motoko.

This module is intentionally small and stdlib-only. It gives Motoko a
source-grounded map of her own codebase before any model is asked to reason
about refactors, commands, tests, or ownership boundaries.
"""

from __future__ import annotations

import ast
import pathlib
import re
from dataclasses import dataclass


CODE_INTEL_SCHEMA = "motoko-code-intel-v1"
CODE_QUERY_SCHEMA = "motoko-code-query-v1"


@dataclass(frozen=True)
class CodeSymbol:
    kind: str
    name: str
    qualname: str
    path: str
    line: int
    end_line: int
    doc: str = ""

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "name": self.name,
            "qualname": self.qualname,
            "path": self.path,
            "line": self.line,
            "end_line": self.end_line,
            "doc": self.doc,
        }


@dataclass(frozen=True)
class CodeCall:
    caller: str
    callee: str
    path: str
    line: int

    def to_dict(self) -> dict:
        return {
            "caller": self.caller,
            "callee": self.callee,
            "path": self.path,
            "line": self.line,
        }


def find_motoko_repo_root(start: str | pathlib.Path | None = None) -> pathlib.Path:
    """Find a Motoko checkout without broad filesystem crawling."""

    candidates = []
    if start is not None:
        candidates.append(pathlib.Path(start).expanduser())
    candidates.append(pathlib.Path.cwd())
    candidates.append(pathlib.Path(__file__).resolve().parents[1])
    for candidate in candidates:
        candidate = candidate.resolve()
        for path in [candidate, *candidate.parents]:
            if (path / "motoko").exists() and (path / "motoko_core").is_dir() and (path / "AGENTS.md").exists():
                return path
    return pathlib.Path(__file__).resolve().parents[1]


def code_files(root: str | pathlib.Path) -> list[pathlib.Path]:
    root = pathlib.Path(root).resolve()
    rows = []
    root_script = root / "motoko"
    if root_script.exists():
        rows.append(root_script)
    for folder in ["motoko_core", "tests"]:
        base = root / folder
        if base.is_dir():
            rows.extend(sorted(base.rglob("*.py")))
    return sorted(dict.fromkeys(path.resolve() for path in rows))


def _rel(root: pathlib.Path, path: pathlib.Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _tokenize(text: str) -> set[str]:
    tokens = set(re.findall(r"[a-z0-9_./-]{2,}", str(text or "").lower()))
    split_tokens = set()
    for token in tokens:
        split_tokens.update(part for part in re.split(r"[_./-]+", token) if len(part) >= 2)
    return tokens | split_tokens


def _safe_read(path: pathlib.Path, *, max_bytes: int = 4_000_000) -> str:
    data = path.read_bytes()
    if len(data) > max_bytes:
        data = data[:max_bytes]
    return data.decode("utf-8", errors="replace")


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Lambda):
        return "<lambda>"
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _literal_string(node: ast.AST) -> str:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else ""


def _module_doc(text: str) -> str:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return ""
    return ast.get_docstring(tree) or ""


def _source_segment(text: str, line: int, end_line: int, *, max_chars: int = 2000) -> str:
    lines = text.splitlines()
    start = max(1, int(line or 1))
    end = max(start, int(end_line or start))
    snippet = "\n".join(lines[start - 1 : end])
    return snippet[:max_chars]


def parse_python_symbols(
    path: pathlib.Path, root: pathlib.Path
) -> tuple[list[CodeSymbol], list[dict], list[dict], list[CodeCall], list[dict]]:
    text = _safe_read(path)
    relpath = _rel(root, path)
    try:
        tree = ast.parse(text, filename=relpath)
    except SyntaxError as exc:
        return [], [], [], [], [{"path": relpath, "error": f"SyntaxError: {exc}"}]

    symbols: list[CodeSymbol] = []
    imports: list[dict] = []
    commands: list[dict] = []
    calls: list[CodeCall] = []
    parser_vars: dict[str, dict] = {}

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.class_stack: list[str] = []
            self.function_stack: list[str] = []

        def current_caller(self) -> str:
            return self.function_stack[-1] if self.function_stack else "<module>"

        def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
            for alias in node.names:
                imports.append({"path": relpath, "module": alias.name, "name": alias.asname or alias.name, "line": node.lineno})

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
            module = "." * int(node.level or 0) + str(node.module or "")
            for alias in node.names:
                imports.append({"path": relpath, "module": module, "name": alias.name, "asname": alias.asname or "", "line": node.lineno})

        def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
            qualname = ".".join([*self.class_stack, node.name]) if self.class_stack else node.name
            symbols.append(
                CodeSymbol(
                    kind="class",
                    name=node.name,
                    qualname=qualname,
                    path=relpath,
                    line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                    doc=ast.get_docstring(node) or "",
                )
            )
            self.class_stack.append(node.name)
            self.generic_visit(node)
            self.class_stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            self._function(node, "method" if self.class_stack else "function")

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
            self._function(node, "async_method" if self.class_stack else "async_function")

        def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, kind: str) -> None:
            qualname = ".".join([*self.class_stack, node.name]) if self.class_stack else node.name
            symbols.append(
                CodeSymbol(
                    kind=kind,
                    name=node.name,
                    qualname=qualname,
                    path=relpath,
                    line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                    doc=ast.get_docstring(node) or "",
                )
            )
            self.function_stack.append(qualname)
            self.generic_visit(node)
            self.function_stack.pop()

        def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
            self._maybe_parser_assign(node)
            self.generic_visit(node)

        def _maybe_parser_assign(self, node: ast.Assign) -> None:
            if not isinstance(node.value, ast.Call):
                return
            call_name = _call_name(node.value.func)
            if call_name.endswith(".add_subparsers"):
                receiver = node.value.func.value if isinstance(node.value.func, ast.Attribute) else None
                if isinstance(receiver, ast.Name) and receiver.id in parser_vars:
                    parser_vars[receiver.id]["parent"] = True
                return
            if not call_name.endswith(".add_parser"):
                return
            command = _literal_string(node.value.args[0]) if node.value.args else ""
            if not command:
                return
            for target in node.targets:
                if isinstance(target, ast.Name):
                    parser_vars[target.id] = {"command": command, "path": relpath, "line": node.lineno, "handler": "", "parent": False}
                    commands.append(parser_vars[target.id])

        def visit_Expr(self, node: ast.Expr) -> None:  # noqa: N802
            value = node.value
            if isinstance(value, ast.Call) and _call_name(value.func).endswith(".set_defaults"):
                receiver = value.func.value if isinstance(value.func, ast.Attribute) else None
                if isinstance(receiver, ast.Name) and receiver.id in parser_vars:
                    for keyword in value.keywords:
                        if keyword.arg == "func":
                            parser_vars[receiver.id]["handler"] = _call_name(keyword.value)
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
            callee = _call_name(node.func)
            if callee:
                calls.append(CodeCall(caller=self.current_caller(), callee=callee, path=relpath, line=node.lineno))
            self.generic_visit(node)

    Visitor().visit(tree)
    return symbols, imports, commands, calls, []


def _symbol_indexes(symbols: list[dict]) -> tuple[dict[str, list[dict]], dict[str, dict]]:
    by_name: dict[str, list[dict]] = {}
    by_qualname: dict[str, dict] = {}
    for row in symbols:
        by_name.setdefault(str(row.get("name", "")), []).append(row)
        by_qualname[str(row.get("qualname", ""))] = row
    return by_name, by_qualname


def _resolve_symbol(
    name: str,
    by_name: dict[str, list[dict]],
    by_qualname: dict[str, dict],
    *,
    allow_dotted_tail: bool = True,
) -> dict:
    if not name:
        return {}
    if name in by_qualname:
        return by_qualname[name]
    if "." in name and not allow_dotted_tail:
        return {}
    tail = name.rsplit(".", 1)[-1]
    matches = by_name.get(tail, [])
    if len(matches) == 1:
        return matches[0]
    root_matches = [row for row in matches if row.get("path") == "motoko"]
    if len(root_matches) == 1:
        return root_matches[0]
    return {}


def _build_test_search_rows(tests: list[dict], file_texts: dict[str, str]) -> list[dict]:
    rows = []
    for test in tests:
        source = _source_segment(
            file_texts.get(str(test.get("path", "")), ""),
            int(test.get("line", 1) or 1),
            int(test.get("end_line", test.get("line", 1)) or 1),
        )
        haystack = " ".join(
            [
                str(test.get("name", "")),
                str(test.get("qualname", "")),
                str(test.get("path", "")),
                str(test.get("doc", "")),
                source,
            ]
        )
        row = dict(test)
        row["_source"] = source
        row["_tokens"] = _tokenize(haystack)
        rows.append(row)
    return rows


def _matching_tests_for_command(command: dict, test_search_rows: list[dict], *, limit: int = 5) -> list[dict]:
    command_text = str(command.get("command", ""))
    handler = str(command.get("handler", ""))
    terms = _tokenize(f"{command_text} {handler}")
    if not terms:
        return []
    ranked = []
    for test in test_search_rows:
        source = str(test.get("_source", ""))
        overlap = sorted(terms & set(test.get("_tokens", set())))
        overlap_count = len(overlap)
        if not overlap:
            continue
        score = overlap_count * 20
        if command_text and command_text in source:
            score += 50
        if handler and handler in source:
            score += 40
        item = {
            "name": test.get("name", ""),
            "qualname": test.get("qualname", ""),
            "path": test.get("path", ""),
            "line": test.get("line", 1),
            "score": score,
            "matched_terms": overlap[:8],
        }
        ranked.append(item)
    ranked.sort(key=lambda row: (row["score"], -int(row.get("line", 0) or 0)), reverse=True)
    return ranked[:limit]


def _build_command_traces(commands: list[dict], symbols: list[dict], tests: list[dict], file_texts: dict[str, str]) -> list[dict]:
    by_name, by_qualname = _symbol_indexes(symbols)
    test_search_rows = _build_test_search_rows(tests, file_texts)
    traces = []
    for command in commands:
        if command.get("parent"):
            continue
        handler = str(command.get("handler", "") or "")
        handler_symbol = _resolve_symbol(handler, by_name, by_qualname)
        traces.append(
            {
                "command": command.get("command", ""),
                "command_path": command.get("path", ""),
                "command_line": command.get("line", 1),
                "handler": handler,
                "handler_path": handler_symbol.get("path", ""),
                "handler_line": handler_symbol.get("line", 0),
                "handler_found": bool(handler_symbol) or handler == "<lambda>",
                "tests": _matching_tests_for_command(command, test_search_rows),
            }
        )
    return traces


def _build_call_edges(calls: list[dict], symbols: list[dict], *, limit: int = 800) -> list[dict]:
    by_name, by_qualname = _symbol_indexes(symbols)
    edges = []
    seen = set()
    for call in calls:
        callee = str(call.get("callee", ""))
        target = _resolve_symbol(callee, by_name, by_qualname, allow_dotted_tail=False)
        if not target:
            continue
        key = (call.get("path"), call.get("caller"), callee, target.get("path"), target.get("qualname"))
        if key in seen:
            continue
        seen.add(key)
        edges.append(
            {
                "caller": call.get("caller", ""),
                "callee": callee,
                "path": call.get("path", ""),
                "line": call.get("line", 1),
                "target": target.get("qualname", ""),
                "target_path": target.get("path", ""),
                "target_line": target.get("line", 1),
            }
        )
        if len(edges) >= limit:
            break
    return edges


def _build_root_hotspots(symbols: list[dict], calls: list[dict], *, limit: int = 15) -> list[dict]:
    call_counts: dict[str, int] = {}
    for call in calls:
        if call.get("path") == "motoko":
            call_counts[str(call.get("caller", ""))] = call_counts.get(str(call.get("caller", "")), 0) + 1
    rows = []
    for symbol in symbols:
        if symbol.get("path") != "motoko" or symbol.get("kind") not in {"function", "async_function"}:
            continue
        lines = int(symbol.get("end_line", symbol.get("line", 1)) or 1) - int(symbol.get("line", 1) or 1) + 1
        rows.append(
            {
                "name": symbol.get("name", ""),
                "qualname": symbol.get("qualname", ""),
                "path": symbol.get("path", ""),
                "line": symbol.get("line", 1),
                "lines": lines,
                "calls": call_counts.get(str(symbol.get("qualname", "")), 0),
            }
        )
    rows.sort(key=lambda row: (int(row.get("lines", 0)), int(row.get("calls", 0))), reverse=True)
    return rows[:limit]


def _build_service_boundaries(modules: list[dict], symbols: list[dict], imports: list[dict], call_edges: list[dict]) -> list[dict]:
    public_by_path: dict[str, list[dict]] = {}
    for symbol in symbols:
        path = str(symbol.get("path", ""))
        if not path.startswith("motoko_core/"):
            continue
        if "." in str(symbol.get("qualname", "")):
            continue
        public_by_path.setdefault(path, []).append(symbol)

    root_import_counts: dict[str, int] = {}
    for row in imports:
        if row.get("path") != "motoko":
            continue
        module = str(row.get("module", ""))
        if not module.startswith("motoko_core"):
            continue
        rel = module.replace(".", "/") + ".py"
        if rel.startswith("motoko_core/"):
            root_import_counts[rel] = root_import_counts.get(rel, 0) + 1

    incoming_calls: dict[str, int] = {}
    for edge in call_edges:
        target_path = str(edge.get("target_path", ""))
        if target_path.startswith("motoko_core/"):
            incoming_calls[target_path] = incoming_calls.get(target_path, 0) + 1

    rows = []
    for module in modules:
        path = str(module.get("path", ""))
        if not path.startswith("motoko_core/"):
            continue
        publics = sorted(public_by_path.get(path, []), key=lambda row: int(row.get("line", 0) or 0))
        rows.append(
            {
                "path": path,
                "lines": module.get("lines", 0),
                "doc": module.get("doc", ""),
                "public_symbols": [row.get("qualname", "") for row in publics[:12]],
                "public_symbol_count": len(publics),
                "root_imports": root_import_counts.get(path, 0),
                "incoming_resolved_calls": incoming_calls.get(path, 0),
            }
        )
    rows.sort(
        key=lambda row: (
            int(row.get("root_imports", 0)),
            int(row.get("incoming_resolved_calls", 0)),
            int(row.get("public_symbol_count", 0)),
        ),
        reverse=True,
    )
    return rows


def build_code_map(root: str | pathlib.Path | None = None) -> dict:
    repo_root = find_motoko_repo_root(root)
    files = code_files(repo_root)
    symbols: list[dict] = []
    imports: list[dict] = []
    commands: list[dict] = []
    calls: list[dict] = []
    parse_errors: list[dict] = []
    modules = []
    file_texts: dict[str, str] = {}
    for path in files:
        text = _safe_read(path)
        relpath = _rel(repo_root, path)
        file_texts[relpath] = text
        file_symbols, file_imports, file_commands, file_calls, file_errors = parse_python_symbols(path, repo_root)
        symbols.extend(row.to_dict() for row in file_symbols)
        imports.extend(file_imports)
        commands.extend(file_commands)
        calls.extend(row.to_dict() for row in file_calls)
        parse_errors.extend(file_errors)
        modules.append(
            {
                "path": relpath,
                "lines": text.count("\n") + (1 if text else 0),
                "bytes": len(text.encode("utf-8")),
                "doc": _module_doc(text),
                "symbols": len(file_symbols),
                "commands": len(file_commands),
            }
        )
    tests = [row for row in symbols if row["path"].startswith("tests/") and row["kind"] == "function" and row["name"].startswith("test_")]
    command_traces = _build_command_traces(commands, symbols, tests, file_texts)
    call_edges = _build_call_edges(calls, symbols)
    root_hotspots = _build_root_hotspots(symbols, calls)
    service_boundaries = _build_service_boundaries(modules, symbols, imports, call_edges)
    command_handlers = {row.get("handler", "") for row in commands if row.get("handler")}
    symbol_names = {row.get("name", "") for row in symbols}
    unlinked_commands = [
        row
        for row in commands
        if not row.get("parent")
        and row.get("handler") != "<lambda>"
        and (not row.get("handler") or row.get("handler") not in symbol_names and "." not in row.get("handler", ""))
    ]
    return {
        "schema": CODE_INTEL_SCHEMA,
        "root": str(repo_root),
        "files": modules,
        "symbols": symbols,
        "imports": imports,
        "calls": calls,
        "call_edges": call_edges,
        "commands": commands,
        "command_traces": command_traces,
        "tests": tests,
        "root_hotspots": root_hotspots,
        "service_boundaries": service_boundaries,
        "summary": {
            "files": len(files),
            "symbols": len(symbols),
            "classes": sum(1 for row in symbols if row["kind"] == "class"),
            "functions": sum(1 for row in symbols if row["kind"] in {"function", "async_function"}),
            "methods": sum(1 for row in symbols if row["kind"] in {"method", "async_method"}),
            "commands": len(commands),
            "command_handlers": len(command_handlers),
            "command_traces": len(command_traces),
            "command_traces_with_tests": sum(1 for row in command_traces if row.get("tests")),
            "calls": len(calls),
            "resolved_call_edges": len(call_edges),
            "service_boundaries": len(service_boundaries),
            "tests": len(tests),
            "parse_errors": len(parse_errors),
            "root_script_lines": next((row["lines"] for row in modules if row["path"] == "motoko"), 0),
            "largest_files": sorted(modules, key=lambda row: row["lines"], reverse=True)[:8],
            "unlinked_commands": unlinked_commands[:12],
            "root_hotspots": root_hotspots[:8],
        },
        "parse_errors": parse_errors,
    }


def _score_text(query_terms: set[str], haystack: str) -> tuple[int, list[str]]:
    terms = _tokenize(haystack)
    overlap = sorted(query_terms & terms)
    return len(overlap), overlap


def query_code_map(code_map: dict, query: str, *, limit: int = 12) -> dict:
    query_terms = _tokenize(query)
    if not query_terms:
        query_terms = _tokenize("motoko")

    def rank(rows: list[dict], fields: list[str], *, name_field: str = "name") -> list[dict]:
        ranked = []
        for row in rows:
            haystack = " ".join(str(row.get(field, "")) for field in fields)
            overlap_count, overlap = _score_text(query_terms, haystack)
            if not overlap:
                continue
            score = overlap_count * 20
            name = str(row.get(name_field, ""))
            if name and any(term in _tokenize(name) for term in query_terms):
                score += 40
            path = str(row.get("path", ""))
            if path and any(term in _tokenize(path) for term in query_terms):
                score += 20
            item = dict(row)
            item["score"] = score
            item["matched_terms"] = overlap[:12]
            ranked.append(item)
        ranked.sort(key=lambda row: (row.get("score", 0), -int(row.get("line", 0) or 0)), reverse=True)
        return ranked[: max(0, int(limit or 0))]

    return {
        "schema": CODE_QUERY_SCHEMA,
        "query": str(query or ""),
        "root": code_map.get("root", ""),
        "symbols": rank(code_map.get("symbols", []), ["name", "qualname", "path", "doc"]),
        "commands": rank(code_map.get("commands", []), ["command", "handler", "path"], name_field="command"),
        "command_traces": rank(
            code_map.get("command_traces", []),
            ["command", "handler", "command_path", "handler_path"],
            name_field="command",
        ),
        "call_edges": rank(
            code_map.get("call_edges", []),
            ["caller", "callee", "path", "target", "target_path"],
            name_field="callee",
        ),
        "service_boundaries": rank(
            code_map.get("service_boundaries", []),
            ["path", "doc", "public_symbols"],
            name_field="path",
        ),
        "tests": rank(code_map.get("tests", []), ["name", "qualname", "path", "doc"]),
        "files": rank(code_map.get("files", []), ["path"], name_field="path"),
    }


def format_code_map_report(code_map: dict) -> str:
    summary = code_map.get("summary") if isinstance(code_map.get("summary"), dict) else {}
    lines = [
        "Motoko code map",
        f"schema: {code_map.get('schema', '')}",
        f"root: {code_map.get('root', '')}",
        (
            f"files: {summary.get('files', 0)}  symbols: {summary.get('symbols', 0)}  "
            f"classes: {summary.get('classes', 0)}  functions: {summary.get('functions', 0)}  "
            f"methods: {summary.get('methods', 0)}"
        ),
        (
            f"commands: {summary.get('commands', 0)}  handlers: {summary.get('command_handlers', 0)}  "
            f"traces: {summary.get('command_traces', 0)}  traced tests: {summary.get('command_traces_with_tests', 0)}"
        ),
        (
            f"calls: {summary.get('calls', 0)}  resolved edges: {summary.get('resolved_call_edges', 0)}  "
            f"service boundaries: {summary.get('service_boundaries', 0)}  tests: {summary.get('tests', 0)}"
        ),
        f"root facade: motoko has {summary.get('root_script_lines', 0)} line(s)",
    ]
    if summary.get("largest_files"):
        lines.append("largest files:")
        for row in summary.get("largest_files", [])[:8]:
            lines.append(f"- {row.get('path', '')}: {row.get('lines', 0)} line(s), {row.get('symbols', 0)} symbol(s)")
    if summary.get("root_hotspots"):
        lines.append("root facade hotspots:")
        for row in summary.get("root_hotspots", [])[:8]:
            lines.append(
                f"- {row.get('qualname', '')}: {row.get('lines', 0)} line(s), "
                f"{row.get('calls', 0)} call(s), {row.get('path', '')}:{row.get('line', '')}"
            )
    if code_map.get("service_boundaries"):
        lines.append("service boundaries:")
        for row in code_map.get("service_boundaries", [])[:8]:
            doc = str(row.get("doc", "")).splitlines()[0] if row.get("doc") else ""
            lines.append(
                f"- {row.get('path', '')}: public={row.get('public_symbol_count', 0)} "
                f"root_imports={row.get('root_imports', 0)} incoming={row.get('incoming_resolved_calls', 0)}"
                + (f" - {doc}" if doc else "")
            )
    if code_map.get("command_traces"):
        lines.append("command traces:")
        for row in code_map.get("command_traces", [])[:8]:
            tests = ", ".join(test.get("name", "") for test in row.get("tests", [])[:3]) or "-"
            lines.append(
                f"- {row.get('command', '')}: handler={row.get('handler', '') or '-'} "
                f"at {row.get('handler_path', '') or '?'}:{row.get('handler_line', '') or '?'} tests={tests}"
            )
    if code_map.get("parse_errors"):
        lines.append("parse errors:")
        for row in code_map.get("parse_errors", [])[:5]:
            lines.append(f"- {row.get('path', '')}: {row.get('error', '')}")
    if summary.get("unlinked_commands"):
        lines.append("command handler warnings:")
        for row in summary.get("unlinked_commands", [])[:8]:
            lines.append(f"- {row.get('command', '')}: handler={row.get('handler', '') or '-'} at {row.get('path', '')}:{row.get('line', '')}")
    lines.append("next: use motoko code-query QUERY to locate implementation and tests.")
    return "\n".join(lines)


def _format_rows(title: str, rows: list[dict], *, command: bool = False, trace: bool = False, service: bool = False) -> list[str]:
    lines = [title + ":"]
    if not rows:
        lines.append("- none")
        return lines
    for row in rows:
        if trace:
            label = row.get("command", "")
            detail = f"handler={row.get('handler', '') or '-'} tests={len(row.get('tests', []) or [])}"
            location = f"{row.get('command_path', '')}:{row.get('command_line', 1)}"
        elif service:
            label = row.get("path", "")
            detail = (
                f"public={row.get('public_symbol_count', 0)} "
                f"root_imports={row.get('root_imports', 0)} incoming={row.get('incoming_resolved_calls', 0)}"
            )
            location = row.get("path", "")
        elif command:
            label = row.get("command", "")
            detail = f"handler={row.get('handler', '') or '-'}"
            location = f"{row.get('path', '')}:{row.get('line', 1)}"
        elif "target" in row:
            label = f"{row.get('caller', '')} -> {row.get('target', '')}"
            detail = f"callee={row.get('callee', '')}"
            location = f"{row.get('path', '')}:{row.get('line', 1)}"
        else:
            label = row.get("qualname") or row.get("path") or row.get("name", "")
            detail = row.get("kind", "")
            location = f"{row.get('path', '')}:{row.get('line', 1)}"
        matched = ",".join(row.get("matched_terms", [])[:6]) or "-"
        lines.append(f"- {label}  {location}  score={row.get('score', 0)}  matched={matched}  {detail}".rstrip())
    return lines


def format_code_query_report(result: dict) -> str:
    lines = [
        f"Motoko code query: {result.get('query', '')}",
        f"schema: {result.get('schema', '')}",
        f"root: {result.get('root', '')}",
    ]
    lines.extend(_format_rows("commands", result.get("commands", []), command=True))
    lines.extend(_format_rows("command traces", result.get("command_traces", []), trace=True))
    lines.extend(_format_rows("symbols", result.get("symbols", [])))
    lines.extend(_format_rows("call edges", result.get("call_edges", [])))
    lines.extend(_format_rows("service boundaries", result.get("service_boundaries", []), service=True))
    lines.extend(_format_rows("tests", result.get("tests", [])))
    lines.extend(_format_rows("files", result.get("files", [])))
    return "\n".join(lines)
