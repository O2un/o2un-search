"""개발 용어 사전. 기호가 이름의 일부인 용어를 토크나이저가 자르지 않고 토큰 하나로 낸다.

원본은 이 파일이다. Rust 구현은 `crates/search-core/scripts/gen_dev_terms.py` 가 만드는
`crates/search-core/src/dev_terms.rs` 를 쓴다. 목록을 고치면 그 스크립트를 다시 돌린다.

용어는 소문자로 적고 두 글자 이상이다. 한 글자 토큰은 토크나이저가 버린다.

`SYNONYMS` 는 같은 용어의 여러 표기 묶음이다(3g 단계 3). 검색 서비스가 검색어를 넓힐 때만 쓰고
토크나이저와 Rust 구현은 쓰지 않는다. 묶음마다 맨 앞이 대표 표기이고, 표기는 소문자다.
- 영문만, 한글만인 표기는 검색어의 대안이 된다. 그 표기의 토큰을 모두 가진 청크가 맞는다
- 한글과 영문이 섞인 표기(`c샵`, `챗gpt`)는 검색어에서 알아보는 데만 쓴다. 토크나이저가 한 음절
  한글과 한 글자 영문을 버려 `c샵`은 토큰이 없고, `챗gpt`는 `gpt`만 남아 대안으로 쓰면 너무 넓다
- 다른 낱말과 겹치는 표기(`링크`=LINQ, `노드`=Node.js, `고도`=Godot)와 한 음절 표기(`뷰`, `깃`)는 넣지 않는다
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

SYNONYMS = (
    # 언어
    ("c#", "c샵", "씨샵", "시샵"),
    ("c++", "cpp", "씨쁠쁠", "씨플플", "시플플"),
    (".net", "dotnet", "닷넷"),
    ("javascript", "js", "자바스크립트"),
    ("typescript", "ts", "타입스크립트"),
    ("python", "파이썬", "파이선"),
    ("java", "자바"),
    ("kotlin", "코틀린"),
    ("swift", "스위프트"),
    ("rust", "러스트"),
    ("golang", "go", "고랭"),
    ("ruby", "루비"),
    ("lua", "루아"),
    ("dart", "다트"),
    ("scala", "스칼라"),
    ("haskell", "하스켈"),
    ("objective-c", "objc", "오브젝티브c"),
    ("sql", "에스큐엘"),
    # 게임 엔진·그래픽
    ("unity", "유니티"),
    ("unreal", "언리얼", "ue4", "ue5"),
    ("blender", "블렌더"),
    ("shader", "셰이더", "쉐이더"),
    ("directx", "다이렉트x", "dx11", "dx12"),
    ("vulkan", "벌칸"),
    ("opengl", "오픈gl"),
    ("mono", "모노"),
    # 웹·프레임워크
    ("react", "react.js", "리액트"),
    ("vue", "vue.js"),
    ("next.js", "nextjs", "넥스트js"),
    ("node.js", "nodejs"),
    ("astro", "아스트로"),
    ("svelte", "스벨트"),
    ("angular", "앵귤러"),
    ("django", "장고"),
    ("flask", "플라스크"),
    ("spring", "스프링"),
    ("flutter", "플러터"),
    ("webassembly", "wasm", "웹어셈블리"),
    # 도구·플랫폼
    ("github", "깃허브", "깃헙"),
    ("gitlab", "깃랩"),
    ("docker", "도커"),
    ("kubernetes", "k8s", "쿠버네티스"),
    ("linux", "리눅스"),
    ("windows", "윈도우", "윈도"),
    ("android", "안드로이드"),
    ("vscode", "비주얼스튜디오코드"),
    ("postgresql", "postgres", "포스트그레스"),
    ("redis", "레디스"),
    ("vercel", "버셀"),
    ("json", "제이슨"),
    ("yaml", "yml"),
    # AI
    ("chatgpt", "챗gpt", "챗지피티"),
    ("gpt", "지피티"),
    ("claude", "클로드"),
    ("gemini", "제미나이"),
    ("openai", "오픈ai"),
)
