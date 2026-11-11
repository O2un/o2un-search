---
title: '각주와 코드'
description: '본문에서 버리는 것과 남기는 것'
pubDate: '2026-11-01'
---

도입부에 각주 표시가 있다[^first].

## 코드 블록

아래 코드 안의 `#` 줄은 제목이 아니다.

```bash
# macOS or Linux
curl -fsSL https://example.com/install.sh | bash

## 이것도 제목이 아니다
```

~~~
## 물결 펜스 안
~~~

## 미디어

::youtube[예고편]{id="A3tAarrM87w"}

::x[게시물]{url="https://x.com/a/status/1"}

![고양이 사진](./cat.webp "캡션 (괄호 포함)")

이미지 뒤 문단[^second]. 링크는 [그대로](https://example.com) 남는다.

:::note[참고]
콜아웃 본문은 남는다.
:::

## 빈 절

## 참고 자료

[^first]: 첫 번째 각주. https://example.com/first
[^second]: 두 번째 각주
    들여쓴 이어지는 줄도 각주다.
