"""샘플 글의 기대 출력(fixture)을 다시 쓴다.

fixture 는 단위 2(Rust 구현)의 정답지다. 규칙을 바꿔 이 스크립트를 돌렸다면 diff 를 사람이
읽고 의도한 변화인지 확인한 뒤에 커밋한다.

    uv run python scripts/update_fixtures.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from indexer import chunk, tokenize  # noqa: E402

SAMPLES = ROOT / "tests" / "samples"
EXPECTED = SAMPLES / "expected"


def expected_for(path: Path) -> dict:
    post_id = f"samples/{path.stem}"
    ext = "mdx" if path.suffix == ".mdx" else "md"
    chunks = chunk(path.read_text(encoding="utf-8"), post_id, ext)
    return {
        "post_id": post_id,
        "ext": ext,
        "chunks": [{**asdict(item), "tokens": tokenize(item.body)} for item in chunks],
    }


def main() -> None:
    EXPECTED.mkdir(exist_ok=True)
    for path in sorted(SAMPLES.glob("*.md*")):
        target = EXPECTED / f"{path.name}.json"
        text = json.dumps(expected_for(path), ensure_ascii=False, indent=2) + "\n"
        target.write_text(text, encoding="utf-8", newline="\n")
        print(target.relative_to(ROOT))


if __name__ == "__main__":
    main()
