"""indexer 의 개발 용어 사전을 Rust 상수로 옮긴다.

사전의 원본은 `indexer/src/indexer/_dev_terms.py` 하나다. 그 목록이 바뀌면 이 스크립트를 다시 돌린다.

    python crates/search-core/scripts/gen_dev_terms.py
"""

import ast
from pathlib import Path

CRATE = Path(__file__).resolve().parent.parent
SOURCE = CRATE.parent.parent / "indexer" / "src" / "indexer" / "_dev_terms.py"
TARGET = CRATE / "src" / "dev_terms.rs"


def load_terms() -> list[str]:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "TERMS" for t in node.targets):
            return list(ast.literal_eval(node.value))
    raise SystemExit(f"TERMS 를 {SOURCE} 에서 찾지 못했다")


def render(terms: list[str]) -> str:
    longest_first = sorted(terms, key=lambda term: (-len(term), term))
    lines = [
        "//! 개발 용어 사전. 긴 용어부터 적는다(토크나이저가 처음 맞는 것을 쓴다).",
        "//!",
        "//! 생성 파일이다. 손으로 고치지 말고 `scripts/gen_dev_terms.py` 를 다시 돌린다.",
        "//! 원본: `indexer/src/indexer/_dev_terms.py`.",
        "",
        "#[rustfmt::skip]",
        "pub(crate) const TERMS: &[&str] = &[",
        *(f'    "{term}",' for term in longest_first),
        "];",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    terms = load_terms()
    TARGET.write_text(render(terms), encoding="utf-8", newline="\n")
    print(f"{len(terms)}개 용어 → {TARGET.relative_to(CRATE)}")


if __name__ == "__main__":
    main()
