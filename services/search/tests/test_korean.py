import pytest

import korean


@pytest.mark.parametrize(
    ("eojeol", "expected"),
    [
        ("렌더링이", "렌더링"),
        ("까맣게", "까맣"),
        ("나오는", "나오"),
        ("만들기", "만들"),
        ("정리하는", "정리"),
        ("추천해줘", "추천"),
        ("기능이다", "기능"),
        ("유니티로", "유니티"),
        # 불규칙 활용은 사전 꼴(까맣)이 아니라 원문 위치로 자른다
        ("까매졌다", "까매"),
        # 조사·어미가 없으면 그대로
        ("유니티", "유니티"),
        ("이유", "이유"),
        # 형태소로 나뉘어도 어절 앞부분을 원문 그대로 남긴다
        ("방탈출을", "방탈출"),
        # 뗀 결과가 한 음절이면 어절 그대로
        ("검은", "검은"),
        # 조사뿐이면 단어가 아니다
        ("에서", None),
    ],
)
def test_stem(eojeol: str, expected: str | None) -> None:
    assert korean.stem(eojeol) == expected
