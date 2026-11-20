import pytest

from indexer import tokenize


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("검색어", ["검색", "색어"]),
        ("락", []),
        ("Rust로 다시", ["rust", "다시"]),
        ("C#에서는 GPT-4", ["c#", "에서", "서는", "gpt"]),
        ("Unity6 2026년", ["unity6", "2026"]),
        # 개발 용어 사전
        ("C++26과 C# 그리고 F#", ["c++", "26", "c#", "그리", "리고", "f#"]),
        ("ASP.NET과 .NET, System.NET", ["asp.net", ".net", "system", "net"]),
        ("Node.js나 node.jsx", ["node.js", "node", "jsx"]),
        ("Objective-C로", ["objective-c"]),
        ("abc++ x#", ["abc"]),
        ("유니티C#", ["유니", "니티", "c#"]),
        # 한 글자 영문·숫자는 버린다
        ("C 스타일, 유니티 6, A/B", ["스타", "타일", "유니", "니티"]),
        ("R3 v2", ["r3", "v2"]),
        # ASCII 만 맞춘다: 전각 Ｃ 는 용어가 아니고 기호 뒤라 단어도 아니다
        ("Ｃ#", []),
        ("ㅋㅋ 日本語 café", ["caf"]),
        ("  ", []),
        ("가나 가나", ["가나", "가나"]),
        # 자모로 풀린(NFD) 한글도 음절로 합쳐 자른다
        ("가나", ["가나"]),
    ],
)
def test_tokenize(text: str, expected: list[str]) -> None:
    assert tokenize(text) == expected
