"""indexer 의 github-slugger 제거 구간 표를 Rust 상수로 옮긴다.

표의 원본은 `indexer/src/indexer/_slug_table.py` 하나다. 그 표가 바뀌면 이 스크립트를 다시 돌린다.

    python crates/search-core/scripts/gen_slug_table.py
"""

import ast
from pathlib import Path

CRATE = Path(__file__).resolve().parent.parent
SOURCE = CRATE.parent.parent / "indexer" / "src" / "indexer" / "_slug_table.py"
TARGET = CRATE / "src" / "slug_table.rs"


def load_ranges() -> list[tuple[int, int]]:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "REMOVED_RANGES":
            return [tuple(pair) for pair in ast.literal_eval(node.value)]
    raise SystemExit(f"REMOVED_RANGES 를 {SOURCE} 에서 찾지 못했다")


def main() -> None:
    ranges = load_ranges()
    lines = [
        "//! github-slugger 2.0.0 이 제목에서 지우는 코드 포인트 구간 (양 끝 포함, 시작값 오름차순).",
        "//!",
        "//! 생성 파일이다. 손으로 고치지 말고 `scripts/gen_slug_table.py` 를 다시 돌린다.",
        "//! 원본: `indexer/src/indexer/_slug_table.py`. github-slugger 는 ISC 라이선스다.",
        "//!",
        "//! 서로게이트 구간(U+D800..U+DFFF)이 걸칠 수 있어 `char` 가 아니라 `u32` 로 둔다.",
        "",
        "#[rustfmt::skip]",
        "pub(crate) const REMOVED_RANGES: &[(u32, u32)] = &[",
        *(f"    (0x{start:X}, 0x{end:X})," for start, end in ranges),
        "];",
        "",
    ]
    TARGET.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"{len(ranges)}개 구간 → {TARGET.relative_to(CRATE)}")


if __name__ == "__main__":
    main()
