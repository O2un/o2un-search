from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import anchors, env


def _dist(args: argparse.Namespace) -> Path:
    return args.dist or args.blog / "dist" / "client"


def _check_anchors(args: argparse.Namespace) -> int:
    report = anchors.check(args.blog, _dist(args))
    for problem in report.problems:
        print(problem)
    print(
        f"공개 글 {report.checked}편 대조, 초안 {len(report.drafts)}편 제외, "
        f"불일치 {len(report.problems)}건"
    )
    return 0 if report.ok else 1


def _compare_core(args: argparse.Namespace) -> int:
    from . import compare, core

    try:
        rust = core.load("rust")
    except ImportError:
        print("Rust 모듈(o2un_search_core)이 설치되지 않아 대조할 수 없다", file=sys.stderr)
        return 1
    report = compare.run(args.blog, core.load("python"), rust)
    for problem in report.problems:
        print(problem)
    print(
        f"공개 글 {report.posts}편·청크 {report.chunks}개 대조, "
        f"차이 {len(report.problems)}편"
    )
    return 0 if report.ok else 1


def _bench_core(args: argparse.Namespace) -> int:
    from . import bench, core

    if args.repeat < 1:
        print("--repeat 는 1 이상", file=sys.stderr)
        return 1
    try:
        rust = core.load("rust")
    except ImportError:
        print("Rust 모듈(o2un_search_core)이 설치되지 않아 잴 수 없다", file=sys.stderr)
        return 1
    python = core.load("python")
    result = bench.run(bench.load_sources(args.blog), [python, rust], args.repeat)
    print(f"공개 글 {result.posts}편·청크 {result.chunks}개, {result.repeat}바퀴")
    for timing in result.timings:
        print(
            f"  {timing.name:<6} 중앙값 {timing.median * 1000:8.2f} ms"
            f"  (최소 {min(timing.seconds) * 1000:.2f}, 최대 {max(timing.seconds) * 1000:.2f})"
        )
    base, other = result.timings
    print(f"  {base.name} / {other.name} = {base.median / other.median:.1f}배")
    return 0


def _sync(args: argparse.Namespace) -> int:
    from . import sync
    from .store import PgStore

    store = PgStore(env.require("SEARCH_WRITER_URL"))
    try:
        summary = sync.run(args.blog, _dist(args), store, dry_run=args.dry_run)
    finally:
        store.close()
    if args.dry_run:
        print("[dry-run] DB 는 바꾸지 않았다")
    for line in summary.lines():
        print(line)
    return 0


def _embed(args: argparse.Namespace) -> int:
    from . import embed
    from .embedding import make_provider
    from .store import PgStore

    store = PgStore(env.require("SEARCH_WRITER_URL"))
    try:
        summary = embed.run(store, make_provider(), dry_run=args.dry_run, limit=args.limit)
    finally:
        store.close()
    if args.dry_run:
        print("[dry-run] 공급자를 부르지 않았다")
    for line in summary.lines():
        print(line)
    return 1 if summary.rate_limited else 0


def _db_migrate(args: argparse.Namespace) -> int:
    from . import db

    applied = db.migrate(env.require("SEARCH_OWNER_URL"))
    print("\n".join(f"applied {name}" for name in applied) or "up to date")
    return 0


def _db_login(args: argparse.Namespace) -> int:
    from . import db

    url = db.open_login(env.require("SEARCH_OWNER_URL"), args.role)
    env.write(db.ROLES[args.role], url)
    print(f"{args.role} 로그인을 열고 {db.ROLES[args.role]} 를 .env 에 썼습니다.")
    return 0


def _db_check_grants(args: argparse.Namespace) -> int:
    from . import db

    ok = True
    for name, var in db.ROLES.items():
        print(f"[{name}]")
        for query, passed, detail in db.check_grants(env.require(var), db.READABLE[name]):
            ok &= passed
            print(f"  {'OK ' if passed else 'BAD'} {query}: {detail}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    env.load()
    parser = argparse.ArgumentParser(prog="indexer")
    commands = parser.add_subparsers(dest="command", required=True)

    def blog_args(command: argparse.ArgumentParser) -> None:
        command.add_argument("--blog", type=Path, required=True, help="블로그 레포 경로")
        command.add_argument("--dist", type=Path, help="빌드 결과 경로 (기본: {blog}/dist/client)")

    check = commands.add_parser(
        "check-anchors", help="청크 앵커를 블로그 빌드 결과(dist)의 절 id 와 대조한다"
    )
    blog_args(check)
    check.set_defaults(run=_check_anchors)

    compare_cmd = commands.add_parser(
        "compare-core", help="공개 글 전체를 Python·Rust 두 구현으로 잘라 청크·토큰을 대조한다"
    )
    compare_cmd.add_argument("--blog", type=Path, required=True, help="블로그 레포 경로")
    compare_cmd.set_defaults(run=_compare_core)

    bench_cmd = commands.add_parser(
        "bench-core", help="공개 글 전체를 두 구현으로 자르고 토큰화해 한 바퀴당 시간을 잰다"
    )
    bench_cmd.add_argument("--blog", type=Path, required=True, help="블로그 레포 경로")
    bench_cmd.add_argument("--repeat", type=int, default=20, help="잴 바퀴 수 (기본 20)")
    bench_cmd.set_defaults(run=_bench_core)

    sync_cmd = commands.add_parser(
        "sync", help="공개 글 전체를 청크로 잘라 색인과 맞춘다. 임베딩은 하지 않는다"
    )
    blog_args(sync_cmd)
    sync_cmd.add_argument("--dry-run", action="store_true", help="DB 를 읽기만 하고 바꿀 수를 출력한다")
    sync_cmd.set_defaults(run=_sync)

    embed_cmd = commands.add_parser("embed", help="임베딩이 빈 청크를 채운다 (GEMINI_API_KEY)")
    embed_cmd.add_argument("--dry-run", action="store_true", help="채울 청크 수만 출력한다")
    embed_cmd.add_argument(
        "--limit", type=int, help="이번 실행에서 임베딩할 최대 개수. 실제 API 로 검증할 때 쓴다"
    )
    embed_cmd.set_defaults(run=_embed)

    db_cmd = commands.add_parser("db", help="search 스키마와 계정 (SEARCH_OWNER_URL)")
    db_commands = db_cmd.add_subparsers(dest="db_command", required=True)
    db_commands.add_parser("migrate", help="마이그레이션 적용").set_defaults(run=_db_migrate)
    login = db_commands.add_parser("login", help="계정 비밀번호를 정해 로그인을 열고 .env 에 쓴다")
    login.add_argument("role", choices=["search_writer", "search_reader"])
    login.set_defaults(run=_db_login)
    db_commands.add_parser(
        "check-grants", help="두 계정이 search 만 읽고 댓글 테이블은 못 읽는지 확인"
    ).set_defaults(run=_db_check_grants)

    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
