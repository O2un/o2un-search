from indexer.slug import Slugger, slugify


def test_slugify_matches_github_slugger() -> None:
    # 기대값은 블로그 빌드 결과(dist)에서 그대로 옮겼다
    assert slugify("① 런타임에서만 드러나는 것") == "-런타임에서만-드러나는-것"
    assert slugify(".NET 10에 없는 API") == "net-10에-없는-api"
    assert slugify("C# Delegate/event와 R3 Subject의 선택 기준") == (
        "c-delegateevent와-r3-subject의-선택-기준"
    )


def test_slugger_numbers_repeats() -> None:
    slugger = Slugger()
    assert [slugger.slug(v) for v in ["예시", "예시", "예시-1", "예시"]] == [
        "예시",
        "예시-1",
        "예시-1-1",
        "예시-2",
    ]
