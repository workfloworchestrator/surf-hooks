import ast
import pytest
from base_exception_hook import BaseExceptionAnalyzer, BaseExceptionIssue


def _analyze(code: str) -> list[BaseExceptionIssue]:
    tree = ast.parse(code)
    analyzer = BaseExceptionAnalyzer()
    analyzer.visit(tree)
    return analyzer.issues


@pytest.mark.parametrize("code,expected_kind", [
    pytest.param("class Foo(BaseException): pass", "subclass", id="subclass"),
    pytest.param("try:\n    pass\nexcept BaseException:\n    pass", "catch", id="catch-direct"),
    pytest.param(
        "try:\n    pass\nexcept (ValueError, BaseException):\n    pass",
        "catch",
        id="catch-in-tuple",
    ),
    pytest.param("raise BaseException('msg')", "raise", id="raise-call"),
    pytest.param("raise BaseException", "raise", id="raise-name"),
])
def test_detects_base_exception(code: str, expected_kind: str):
    issues = _analyze(code)
    assert len(issues) == 1
    assert issues[0].kind == expected_kind


@pytest.mark.parametrize("code", [
    pytest.param("class Foo(Exception): pass", id="subclass-exception"),
    pytest.param("try:\n    pass\nexcept Exception:\n    pass", id="catch-exception"),
    pytest.param("try:\n    pass\nexcept (ValueError, TypeError):\n    pass", id="catch-tuple-safe"),
    pytest.param("raise ValueError('msg')", id="raise-valueerror"),
])
def test_passes_through(code: str):
    assert _analyze(code) == []
