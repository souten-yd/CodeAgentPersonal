import ast
from pathlib import Path


MAIN_PATH = Path(__file__).resolve().parents[1] / "main.py"


def _imported_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            for alias in node.names:
                names.add(alias.name)
    return names


def _annotation_uses_mapping(node: ast.AST) -> bool:
    for subnode in ast.walk(node):
        if isinstance(subnode, ast.Name) and subnode.id == "Mapping":
            return True
    return False


def test_main_is_parseable():
    source = MAIN_PATH.read_text(encoding="utf-8")
    ast.parse(source, filename=str(MAIN_PATH))


def test_mapping_is_imported_when_used_in_annotations():
    source = MAIN_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MAIN_PATH))

    uses_mapping = any(
        _annotation_uses_mapping(node.annotation)
        for node in ast.walk(tree)
        if isinstance(node, ast.arg) and node.annotation is not None
    ) or any(
        _annotation_uses_mapping(node.returns)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is not None
    )

    if uses_mapping:
        imported_typing_names = _imported_names(tree)
        assert "Mapping" in imported_typing_names
