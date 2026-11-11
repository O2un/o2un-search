"""`.env` 를 읽고 쓴다. 이미 설정된 환경 변수는 덮어쓰지 않는다(CI 는 Secrets 로 넣는다)."""

from __future__ import annotations

import os
import re
from pathlib import Path

ENV_FILE = Path(".env")

_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def load(path: Path = ENV_FILE) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _LINE.match(line)
        if match and match.group(1) not in os.environ:
            os.environ[match.group(1)] = match.group(2).strip("\"'")


def require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} 가 없습니다. indexer/.env 에 넣거나 환경 변수로 주세요.")
    return value


def write(name: str, value: str, path: Path = ENV_FILE) -> None:
    """`name=value` 줄을 바꾸거나 덧붙인다. 값은 화면에 내지 않는다."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    entry = f"{name}={value}"
    for index, line in enumerate(lines):
        match = _LINE.match(line)
        if match and match.group(1) == name:
            lines[index] = entry
            break
    else:
        lines.append(entry)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[name] = value
