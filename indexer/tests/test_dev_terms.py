import importlib.util
from pathlib import Path

from indexer._dev_terms import TERMS

GENERATOR = Path(__file__).resolve().parents[2] / "crates" / "search-core" / "scripts" / "gen_dev_terms.py"


def test_terms_are_lowercase_and_longer_than_one() -> None:
    assert len(set(TERMS)) == len(TERMS)
    for term in TERMS:
        assert term == term.lower() and term.isascii() and len(term) > 1, term


def test_rust_table_is_generated_from_terms() -> None:
    spec = importlib.util.spec_from_file_location("gen_dev_terms", GENERATOR)
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    assert generator.TARGET.read_text(encoding="utf-8") == generator.render(list(TERMS))
