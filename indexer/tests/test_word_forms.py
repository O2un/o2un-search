import pytest

from indexer.word_forms import index_forms, query_form


@pytest.mark.parametrize(
    ("tokens", "expected"),
    [
        (["shaders"], ["shaders", "shader"]),
        (["rendering", "rendered"], ["rendering", "render", "rendered", "render"]),
        (["unity6"], ["unity6", "unity", "uniti"]),
        (["shader"], ["shader"]),
        # 사전 용어, 한 글자 영문 + 숫자, 숫자, 한글은 그대로
        (["c#", "node.js", "x86", "r3", "2026", "유니"], ["c#", "node.js", "x86", "r3", "2026", "유니"]),
        (["gpt4o"], ["gpt4o"]),
    ],
)
def test_index_forms(tokens: list[str], expected: list[str]) -> None:
    assert index_forms(tokens) == expected


def test_query_form_meets_index_forms() -> None:
    # 검색어 꼴은 그 낱말의 어느 꼴을 쓴 글의 토큰에도 들어 있다.
    for query, written in [("shader", "shaders"), ("shaders", "shader"), ("render", "rendering"), ("unity", "unity6")]:
        assert query_form(query) in index_forms([written]), (query, written)
    assert query_form("unity6") == "unity6"
    assert query_form("c#") == "c#"
