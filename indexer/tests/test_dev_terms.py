import importlib.util
import re
from pathlib import Path

from indexer._dev_terms import SYNONYMS, TERMS

GENERATOR = Path(__file__).resolve().parents[2] / "crates" / "search-core" / "scripts" / "gen_dev_terms.py"


def test_terms_are_lowercase_and_longer_than_one() -> None:
    assert len(set(TERMS)) == len(TERMS)
    for term in TERMS:
        assert term == term.lower() and term.isascii() and len(term) > 1, term


def test_synonym_forms_are_unique_lowercase_and_have_tokens() -> None:
    forms = [form for bundle in SYNONYMS for form in bundle]
    assert len(set(forms)) == len(forms), "한 표기가 두 묶음에 들었다"
    for bundle in SYNONYMS:
        assert len(bundle) > 1, bundle
        for form in bundle:
            assert form == form.lower() and len(form) > 1, form
            hangul = re.fullmatch(r"[가-힣]+", form)
            ascii_ = form.isascii()
            # 한글만인 표기는 두 음절 이상(2-gram 토큰이 있다). 섞인 표기는 검색어 알아보기용이다.
            assert (hangul and len(form) > 1) or ascii_ or re.fullmatch(r"[가-힣a-z0-9]+", form), form


def test_rust_table_is_generated_from_terms() -> None:
    spec = importlib.util.spec_from_file_location("gen_dev_terms", GENERATOR)
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    assert generator.TARGET.read_text(encoding="utf-8") == generator.render(list(TERMS))
