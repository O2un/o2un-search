from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import anchors


def _check_anchors(args: argparse.Namespace) -> int:
    report = anchors.check(args.blog, args.dist)
    for problem in report.problems:
        print(problem)
    print(
        f"공개 글 {report.checked}편 대조, 초안 {len(report.drafts)}편 제외, "
        f"불일치 {len(report.problems)}건"
    )
    return 0 if report.ok else 1


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="indexer")
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser(
        "check-anchors", help="청크 앵커를 블로그 빌드 결과(dist)의 절 id 와 대조한다"
    )
    check.add_argument("--blog", type=Path, required=True, help="블로그 레포 경로")
    check.add_argument("--dist", type=Path, help="빌드 결과 경로 (기본: {blog}/dist/client)")
    check.set_defaults(run=_check_anchors)

    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
