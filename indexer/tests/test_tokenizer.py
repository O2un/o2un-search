import pytest

from indexer import tokenize


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("검색어", ["검색", "색어"]),
        ("락", []),
        ("Rust로 다시", ["rust", "다시"]),
        ("C#에서는 GPT-4", ["c", "에서", "서는", "gpt", "4"]),
        ("Unity6 2026년", ["unity6", "2026"]),
        ("ㅋㅋ 日本語 café", ["caf"]),
        ("  ", []),
        ("가나 가나", ["가나", "가나"]),
        # 자모로 풀린(NFD) 한글도 음절로 합쳐 자른다
        ("가나", ["가나"]),
    ],
)
def test_tokenize(text: str, expected: list[str]) -> None:
    assert tokenize(text) == expected
