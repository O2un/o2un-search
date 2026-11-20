"""개발 용어 사전. 기호가 이름의 일부인 용어를 토크나이저가 자르지 않고 토큰 하나로 낸다.

원본은 이 파일이다. Rust 구현은 `crates/search-core/scripts/gen_dev_terms.py` 가 만드는
`crates/search-core/src/dev_terms.rs` 를 쓴다. 목록을 고치면 그 스크립트를 다시 돌린다.

용어는 소문자로 적고 두 글자 이상이다. 한 글자 토큰은 토크나이저가 버린다.
"""

TERMS = (
    "c++",
    "c#",
    "f#",
    "objective-c",
    ".net",
    "asp.net",
    "ado.net",
    "node.js",
    "next.js",
    "nuxt.js",
    "vue.js",
    "react.js",
    "three.js",
    "d3.js",
)
