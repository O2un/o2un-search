from pathlib import Path

from indexer.corpus import is_published, iter_posts


def _write(root: Path, relative: str, frontmatter: str) -> None:
    path = root / "src" / "content" / "blog" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{frontmatter}\n---\n\n## 절\n\n본문\n", encoding="utf-8")


def test_post_ids_and_drafts(tmp_path: Path) -> None:
    _write(tmp_path, "선택/Loop/index.md", "title: a\ndraft: false")
    _write(tmp_path, "HelloWorld/index.md", "title: b")
    _write(tmp_path, "csharp/coreclr_4_migration/index.md", "title: c")
    _write(tmp_path, "취미/girigo/index.mdx", "title: d")
    _write(tmp_path, "일상/secret/index.md", "title: e\ndraft: true")
    _write(tmp_path, "_wip/index.md", "title: f")
    _write(tmp_path, "뉴스/old/index.md", "title: g\nslug: 뉴스/renamed")

    posts = {post.post_id: post for post in iter_posts(tmp_path)}

    assert set(posts) == {
        "선택/loop",
        "helloworld",
        "csharp/coreclr_4_migration",
        "취미/girigo",
        "일상/secret",
        "_wip",
        "뉴스/renamed",
    }
    assert posts["취미/girigo"].ext == "mdx"
    published = {post_id for post_id, post in posts.items() if is_published(post)}
    assert "일상/secret" not in published
    assert "_wip" not in published
    assert len(published) == 5
