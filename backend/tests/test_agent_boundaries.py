"""Architectural guard: ordinary Python imports from the AI layer cannot reach human writers."""
import ast
from collections import deque
from importlib.util import resolve_name
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
HUMAN_WRITERS = {"app.api.tasks", "app.api.reviews", "app.api.workflow", "app.services.workflow", "app.api.access",
                 "app.api.people", "app.api.responsibilities"}


def _modules():
    modules = {}
    for path in APP.rglob("*.py"):
        name = ".".join(path.relative_to(APP.parent).with_suffix("").parts)
        modules[name.removesuffix(".__init__")] = path
    return modules


def _dependencies(name, path, modules):
    package = name if path.name == "__init__.py" else name.rpartition(".")[0]
    imports = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = resolve_name("." * node.level + (node.module or ""), package)
            # "from package import x" can import a submodule or an attribute from __init__.
            imports.add(module)
            imports.update(f"{module}.{alias.name}" for alias in node.names)
    # Importing a submodule also executes each parent package's __init__.py.
    dependencies = set()
    for imported in imports:
        parts = imported.split(".")
        dependencies.update(".".join(parts[:i]) for i in range(1, len(parts) + 1))
    return sorted(dependencies.intersection(modules) - {name})


def test_ai_cannot_import_task_or_review_writers_even_transitively():
    modules = _modules()
    assert HUMAN_WRITERS <= modules.keys()
    starts = [name for name in modules if name == "app.ai" or name.startswith("app.ai.")]
    assert starts
    queue = deque((name,) for name in starts)
    visited = set()
    while queue:
        chain = queue.popleft()
        name = chain[-1]
        assert name not in HUMAN_WRITERS, "AI imports a human writer: " + " -> ".join(chain)
        if name not in visited:
            visited.add(name)
            for dependency in _dependencies(name, modules[name], modules):
                queue.append((*chain, dependency))
