from pathlib import Path

from indexer import db, env


def test_role_url_swaps_credentials_only() -> None:
    owner = "postgresql://neondb_owner:secret@ep-x-pooler.ap.aws.neon.tech/neondb?sslmode=require"
    url = db.role_url(owner, "search_reader", "p/w+=")
    assert url == (
        "postgresql://search_reader:p%2Fw%2B%3D@ep-x-pooler.ap.aws.neon.tech/neondb?sslmode=require"
    )


def test_write_replaces_or_appends(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "vars"
    path.write_text("A=1\nB=2\n", encoding="utf-8")
    monkeypatch.delenv("B", raising=False)
    monkeypatch.delenv("C", raising=False)
    env.write("B", "x", path)
    env.write("C", "y", path)
    assert path.read_text(encoding="utf-8") == "A=1\nB=x\nC=y\n"
