"""
Redundancy & Obsolescence Detector
Finds: unused imports, redundant variables, obsolete strings, duplicate code.

Run: python scripts/redundancy_checker.py [dir]
"""
from __future__ import annotations
import ast
import re
import sys
from pathlib import Path
from typing import Any


class RedundancyChecker(ast.NodeVisitor):
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.source = Path(filepath).read_text(encoding="utf-8", errors="replace")
        self.tree = ast.parse(self.source, filename=filepath)

        self.imports: list[dict[str, Any]] = []  # {name, line, type}
        self.used_names: set[str] = set()
        self.defined_names: set[str] = set()
        self.defined_in_function: set[str] = set()
        self._current_function: str | None = None
        self._in_import: bool = False

        self.redundant_imports: list[dict[str, Any]] = []
        self.unused_variables: list[dict[str, Any]] = []
        self.duplicate_strings: list[dict[str, Any]] = []
        self.dead_code_blocks: list[dict[str, Any]] = []

        self._scan()

    def _scan(self):
        """First pass: collect definitions and usages."""
        for node in ast.walk(self.tree):
            # Collect names used
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                self.used_names.add(node.id)
            elif isinstance(node, ast.Attribute):
                self.used_names.add(node.attr)

            # Collect function-local definitions
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._current_function = node.name
                for child in ast.walk(node):
                    if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                        self.defined_in_function.add(child.id)
                self._current_function = None

        # Second pass: analyze imports
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name.split('.')[0]
                    self.imports.append({"name": name, "line": node.lineno, "full": alias.name, "type": "import"})
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    name = alias.asname or alias.name
                    self.imports.append({
                        "name": name, "line": node.lineno,
                        "full": f"{node.module}.{alias.name}" if node.module else alias.name,
                        "type": "from"
                    })

    def check_unused_imports(self) -> list[dict[str, Any]]:
        """Find imports that are never used."""
        results = []
        for imp in self.imports:
            name = imp["name"]
            # Skip common patterns that ARE used but not detected by AST
            if name in self.used_names:
                continue
            # Check if the full module path is used
            if imp["full"].split('.')[0] in self.used_names:
                continue
            # Check common stdlib imports that are always "used" conceptually
            if name in ["Any", "Optional", "List", "Dict", "Tuple", "Union"]:
                if name in self.used_names:
                    continue
            results.append(imp)
        return results

    def check_unused_variables(self) -> list[dict[str, Any]]:
        """Find variables assigned but never used."""
        results = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                name = node.id
                # Skip dunder names, common patterns
                if name.startswith("__") or name in ["_", "cls", "self"]:
                    continue
                if name not in self.used_names and name not in self.defined_in_function:
                    # Check if it's in a simple assignment that's unused
                    results.append({
                        "name": name,
                        "line": node.lineno,
                        "reason": "assigned but never read"
                    })
        return results[:20]  # Limit to avoid noise

    def check_duplicate_strings(self) -> list[dict[str, Any]]:
        """Find repeated string literals."""
        strings: dict[str, list[int]] = {}
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                s = node.value.strip()
                if len(s) > 20:  # Only check meaningful strings
                    strings.setdefault(s, []).append(node.lineno)

        return [
            {"string": s[:50], "lines": lines, "count": len(lines)}
            for s, lines in strings.items()
            if len(lines) > 2
        ]

    def check_dead_code(self) -> list[dict[str, Any]]:
        """Find unreachable code after return/break/continue."""
        results = []
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                body = node.body
                for i, stmt in enumerate(body[:-1]):
                    if isinstance(stmt, ast.Return):
                        # Check if next statement is reachable
                        if i + 1 < len(body):
                            next_stmt = body[i + 1]
                            if not isinstance(next_stmt, (ast.Return, ast.Raise)):
                                results.append({
                                    "function": node.name,
                                    "line": next_stmt.lineno,
                                    "after": f"return at line {stmt.lineno}"
                                })
        return results

    def analyze(self) -> dict[str, Any]:
        return {
            "file": self.filepath,
            "unused_imports": self.check_unused_imports(),
            "unused_variables": self.check_unused_variables(),
            "duplicate_strings": self.check_duplicate_strings(),
            "dead_code": self.check_dead_code(),
            "total_lines": len(self.source.splitlines()),
        }


def check_file(filepath: Path) -> dict[str, Any]:
    try:
        checker = RedundancyChecker(str(filepath))
        return checker.analyze()
    except SyntaxError as e:
        return {"file": str(filepath), "error": str(e)}


def run_check(root_dir: Path) -> dict[str, Any]:
    print(f"\n{'='*60}")
    print("REDUNDANCY & OBSOLESCENCE CHECK")
    print(f"{'='*60}\n")

    target_dir = root_dir / "src" / "otto" / "orchestration"

    all_results = []
    for py_file in target_dir.rglob("*.py"):
        if "__pycache__" in str(py_file) or py_file.name.startswith("test_"):
            continue
        result = check_file(py_file)
        if "error" not in result:
            all_results.append(result)

    # Aggregate findings
    total_unused_imports = sum(len(r["unused_imports"]) for r in all_results)
    total_unused_vars = sum(len(r["unused_variables"]) for r in all_results)
    total_dead_code = sum(len(r["dead_code"]) for r in all_results)

    print(f"Files scanned: {len(all_results)}")
    print(f"Total lines: {sum(r['total_lines'] for r in all_results)}")
    print(f"\nUnused imports: {total_unused_imports}")
    print(f"Unused variables: {total_unused_vars}")
    print(f"Dead code blocks: {total_dead_code}")

    if total_unused_imports > 0:
        print("\n--- Unused Imports ---")
        for r in all_results:
            if r["unused_imports"]:
                print(f"\n{r['file']}")
                for u in r["unused_imports"][:5]:
                    print(f"  Line {u['line']}: {u['name']}")

    if total_dead_code > 0:
        print("\n--- Dead Code ---")
        for r in all_results:
            if r["dead_code"]:
                print(f"\n{r['file']}")
                for d in r["dead_code"][:3]:
                    print(f"  Line {d['line']}: {d['after']}")

    # Phase 2 specific checks
    print(f"\n{'='*60}")
    print("PHASE 2 SPECIFIC CHECKS")
    print(f"{'='*60}")

    critical_files = [
        "council.py",
        "kairos.py",
        "morpheus.py",
        "kairos_gold.py",
    ]

    issues = []
    for cf in critical_files:
        file_path = target_dir / cf
        if not file_path.exists():
            continue

        content = file_path.read_text(encoding="utf-8")
        lines = content.splitlines()

        # Check for obvious redundancies
        # 1. Duplicate function definitions
        func_names = {}
        for i, line in enumerate(lines):
            if re.match(r'^def |^    def ', line):
                match = re.search(r'def (\w+)', line)
                if match:
                    name = match.group(1)
                    func_names.setdefault(name, []).append(i + 1)

        duplicates = {n: lns for n, lns in func_names.items() if len(lns) > 1}
        if duplicates:
            issues.append(f"{cf}: duplicate function definitions: {duplicates}")

        # 2. Unused variables (simple pattern check)
        for i, line in enumerate(lines):
            if re.match(r'^\s+\w+\s*=\s*[^\s]', line) and "=" in line.split("#")[0]:
                var_match = re.match(r'^\s+(\w+)\s*=', line)
                if var_match:
                    var_name = var_match.group(1)
                    # Check if used later
                    later = "\n".join(lines[i+1:])
                    if var_name not in later:
                        issues.append(f"{cf}:{i+1}: unused variable '{var_name}'")

        # 3. Obsolete TODO comments
        for i, line in enumerate(lines):
            if "TODO" in line or "FIXME" in line or "XXX" in line:
                issues.append(f"{cf}:{i+1}: obsolete TODO/FIXME comment")

    if issues:
        print(f"\nIssues found: {len(issues)}")
        for issue in issues[:20]:
            print(f"  - {issue}")
    else:
        print("\n✓ No issues in Phase 2 files")

    # Summary
    print(f"\n{'='*60}")
    print("VERDICT")
    print(f"{'='*60}")

    total_issues = total_unused_imports + total_unused_vars + total_dead_code + len(issues)

    if total_issues == 0:
        print("\n✓ CLEAN: No redundant or obsolete code detected")
        return {"status": "CLEAN"}
    else:
        print(f"\n✗ {total_issues} issues found:")
        print(f"  - Unused imports: {total_unused_imports}")
        print(f"  - Unused variables: {total_unused_vars}")
        print(f"  - Dead code blocks: {total_dead_code}")
        print(f"  - Phase 2 issues: {len(issues)}")
        return {"status": "ISSUES", "count": total_issues}


if __name__ == "__main__":
    root = Path(__file__).parent.parent
    result = run_check(root)
    sys.exit(0 if result.get("status") == "CLEAN" else 1)
