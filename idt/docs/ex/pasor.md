즉 단순히:

text = page.get_text()

이렇게 끝내면 거의 반드시 망하고, 실무에서는 보통 아래처럼 간다.

PDF
→ 좌표 기반 원자 요소 추출
→ 헤더/푸터/각주/본문/표/그림 영역 분리
→ 컬럼 감지
→ 읽기 순서 재구성
→ 문단/섹션/표 구조화
→ 청킹
→ 품질 점수 기록
→ 실패 시 fallback
1. 먼저 PDF를 “텍스트”가 아니라 “좌표가 있는 요소들”로 봐야 한다

PDF에서 제일 중요한 건 이거야.

텍스트 내용만 추출하지 말고,
각 텍스트가 어디에 있었는지를 같이 저장해야 한다.

예를 들면 내부적으로 이런 형태로 만든다.

{
    "page": 3,
    "text": "대출 금리는 신용등급에 따라 차등 적용된다.",
    "x0": 72.1,
    "y0": 153.4,
    "x1": 412.5,
    "y1": 169.8,
    "block_type": "text",
    "section": "대출 금리 기준"
}

즉 최종 목표는 단순 문자열이 아니라 이런 구조다.

DocumentElement
- page_no
- text
- bbox: x0, y0, x1, y1
- type: title / paragraph / table / footer / footnote / figure_caption
- section_title
- reading_order
- confidence_score

이걸 해놔야 나중에 순서가 깨졌을 때 복원할 수 있다.

2. 전체 해결 전략은 “단일 로직”이 아니라 “단계별 방어”다

PDF는 문서마다 너무 다르기 때문에 완벽한 공통 로직 하나는 거의 불가능하다.

그래서 실무에서는 보통 이렇게 설계한다.

1차: PyMuPDF/pdfplumber 같은 빠른 파서
2차: 좌표 기반 후처리
3차: 표/그림/각주 별도 처리
4차: 품질 점수 계산
5차: 품질 낮으면 Docling / unstructured / OCR / LlamaParse fallback

중요한 건 이거야.

모든 PDF를 한 번에 완벽히 파싱하려 하지 말고,
문제 유형을 감지해서 전략을 바꿔야 한다.
3. 읽기 순서 깨짐 해결: 좌표 기반 재정렬

가장 기본적인 방식은 y좌표 → x좌표 순서로 정렬하는 것이다.

blocks = page.get_text("blocks")

blocks.sort(key=lambda b: (b[1], b[0]))  # y0, x0 기준 정렬

하지만 이건 1단 문서에서는 어느 정도 먹히지만, 2단 컬럼에서는 오히려 망한다.

왜냐면 이렇게 읽어버릴 수 있기 때문이야.

왼쪽 첫 줄 + 오른쪽 첫 줄
왼쪽 둘째 줄 + 오른쪽 둘째 줄
...

그래서 2단 컬럼은 단순 y, x 정렬이 아니라 컬럼을 먼저 나눠야 한다.

4. 2단 컬럼 해결: “컬럼 감지 → 컬럼 내부 정렬 → 병합”

기본 아이디어는 이거다.

1. 페이지에서 본문 영역만 남긴다.
2. x좌표 분포를 본다.
3. 왼쪽 컬럼과 오른쪽 컬럼을 나눈다.
4. 각 컬럼 안에서 y좌표 기준 정렬한다.
5. 왼쪽 전체를 먼저 읽고, 그다음 오른쪽을 읽는다.

단순 버전은 네가 적은 것처럼 가능하다.

blocks = page.get_text("blocks")

page_width = page.rect.width
mid_x = page_width / 2

left_blocks = []
right_blocks = []

for block in blocks:
    x0, y0, x1, y1, text, *_ = block
    center_x = (x0 + x1) / 2

    if center_x < mid_x:
        left_blocks.append(block)
    else:
        right_blocks.append(block)

left_blocks.sort(key=lambda b: b[1])
right_blocks.sort(key=lambda b: b[1])

ordered_blocks = left_blocks + right_blocks

그런데 실무에서는 이걸 그대로 쓰면 부족하다.

왜냐면 논문은 보통 이렇게 생겼기 때문이다.

[제목]        ← 전체 너비
[저자]        ← 전체 너비
[Abstract]   ← 전체 너비 또는 1단
--------------------------------
왼쪽 컬럼      오른쪽 컬럼
왼쪽 컬럼      오른쪽 컬럼
--------------------------------
[표]          ← 전체 너비
--------------------------------
왼쪽 컬럼      오른쪽 컬럼

그래서 실제로는 이렇게 해야 한다.

페이지 전체를 한 번에 왼쪽/오른쪽으로 나누지 말고,
전체 너비 블록을 기준으로 페이지를 구간별로 나눠야 한다.

예를 들면:

Zone 1: 제목/초록 영역 → 1단 처리
Zone 2: 본문 영역 → 2단 처리
Zone 3: 표 영역 → table 처리
Zone 4: 표 아래 본문 → 다시 2단 처리
5. 더 현실적인 2단 컬럼 처리 의사코드

단순화하면 이런 구조가 좋다.

def reorder_page(blocks, page_width, page_height):
    # 1. 헤더/푸터 제거
    body_blocks = remove_header_footer(blocks, page_height)

    # 2. 전체 너비 블록 분리
    full_width_blocks = []
    normal_blocks = []

    for block in body_blocks:
        x0, y0, x1, y1, text, *_ = block
        width = x1 - x0

        if width > page_width * 0.65:
            full_width_blocks.append(block)
        else:
            normal_blocks.append(block)

    # 3. 전체 너비 블록 기준으로 zone 분리
    zones = split_by_full_width_blocks(normal_blocks, full_width_blocks)

    ordered = []

    for zone in zones:
        zone_blocks = zone["blocks"]

        if is_two_column(zone_blocks, page_width):
            left, right = split_columns(zone_blocks, page_width)
            left.sort(key=lambda b: b[1])
            right.sort(key=lambda b: b[1])
            ordered.extend(left)
            ordered.extend(right)
        else:
            zone_blocks.sort(key=lambda b: (b[1], b[0]))
            ordered.extend(zone_blocks)

        # 해당 zone 뒤에 있는 full-width block이 있으면 삽입
        if zone.get("full_width_block"):
            ordered.append(zone["full_width_block"])

    return ordered

핵심은 이거야.

페이지 전체를 일괄 정렬하지 않는다.
영역을 나누고, 각 영역에 맞는 정렬 전략을 쓴다.
6. 헤더/푸터 제거는 “좌표 + 반복 빈도”로 한다

헤더/푸터는 보통 모든 페이지에 반복된다.

예를 들면:

회사명
문서 제목
페이지 번호
Confidential
2025 내부 보고서

이런 것들이 매 페이지마다 들어가면 벡터 DB에서 노이즈가 된다.

해결은 보통 이렇게 한다.

1. 페이지 상단 10% 영역 텍스트 수집
2. 페이지 하단 10% 영역 텍스트 수집
3. 여러 페이지에서 반복되는 문자열 찾기
4. 반복 비율이 높으면 header/footer로 제거

예시 기준:

top_area = page_height * 0.1
bottom_area = page_height * 0.9

판단 예시:

전체 20페이지 중 15페이지 이상 반복됨
→ 헤더/푸터 후보

주의할 점은 페이지 번호는 숫자가 바뀌기 때문에 정규화해야 한다.

"Page 1 of 20"
"Page 2 of 20"
"Page 3 of 20"

이걸 그대로 비교하면 다른 문자열로 보인다.

그래서 이런 식으로 정규화한다.

Page <NUM> of <NUM>
7. 표는 절대 일반 문장처럼 섞으면 안 된다

표가 제일 위험하다.

예를 들어 원본 표가 이렇다고 하자.

등급	금리	한도
A	3.5%	1억
B	5.2%	7천만
C	8.1%	3천만

이걸 일반 텍스트로 뽑으면 이렇게 될 수 있다.

등급 금리 한도 A 3.5% 1억 B 5.2% 7천만 C 8.1% 3천만

이러면 검색도 안 좋고, LLM도 의미를 잘못 이해할 수 있다.

표는 최소 3가지 형태로 저장하는 게 좋다.

1번. 원본 구조 보존용 Markdown
| 등급 | 금리 | 한도 |
|---|---:|---:|
| A | 3.5% | 1억 |
| B | 5.2% | 7천만 |
| C | 8.1% | 3천만 |
2번. 검색용 의미 문장
대출 금리 기준 표에서 A등급의 금리는 3.5%이고 한도는 1억이다.
대출 금리 기준 표에서 B등급의 금리는 5.2%이고 한도는 7천만 원이다.
대출 금리 기준 표에서 C등급의 금리는 8.1%이고 한도는 3천만 원이다.
3번. 메타데이터
{
  "type": "table",
  "section_title": "대출 금리 기준",
  "columns": ["등급", "금리", "한도"],
  "page": 5,
  "source": "loan_policy.pdf"
}

이렇게 저장하면 RAG에서 훨씬 잘 걸린다.

벡터 DB에는 보통 이런 식으로 넣는다.

content:
대출 금리 기준 표.
A등급의 금리는 3.5%이고 한도는 1억이다.
B등급의 금리는 5.2%이고 한도는 7천만 원이다.
C등급의 금리는 8.1%이고 한도는 3천만 원이다.

metadata:
{
  "block_type": "table",
  "section_title": "대출 금리 기준",
  "page": 5
}

즉 표는:

원본 표 보존 + 의미 문장화 + 메타데이터화

이 세 개를 같이 가져가는 게 좋다.

8. 각주는 본문과 분리해야 한다

각주는 보통 페이지 하단에 있다.

문제는 파서가 각주를 본문 중간에 끼워넣는 경우가 많다는 거다.

예를 들어 원래 본문은:

이 모델은 기존 방식보다 높은 정확도를 보였다.

각주는:

1) 실험 환경은 Appendix A 참고.

그런데 파싱 결과가 이렇게 나올 수 있다.

이 모델은 기존 방식보다 높은 정확도를 보였다.
1) 실험 환경은 Appendix A 참고.
다음 장에서는...

이러면 본문 흐름이 깨진다.

대응 방식은 보통 이렇다.

1. 페이지 하단 일정 영역을 footnote zone으로 본다.
2. 작은 폰트 크기 또는 짧은 줄 패턴을 감지한다.
3. 본문 chunk와 분리한다.
4. 각주는 별도 metadata로 연결한다.

예를 들면:

{
  "text": "이 모델은 기존 방식보다 높은 정확도를 보였다.",
  "footnotes": [
    "실험 환경은 Appendix A 참고."
  ]
}

또는 별도 chunk로 저장한다.

{
  "block_type": "footnote",
  "text": "1) 실험 환경은 Appendix A 참고.",
  "page": 3,
  "linked_section": "실험 결과"
}
9. 참고문헌은 대부분 검색 노이즈라 별도 처리하는 게 좋다

RAG에서 참고문헌은 꽤 자주 노이즈가 된다.

예를 들어 사용자가 “대출 심사 기준이 뭐야?”라고 물었는데, 참고문헌에 있는 논문 제목이 검색되는 식이다.

그래서 참고문헌 섹션은 감지해서 별도 처리하는 게 좋다.

감지 키워드:

References
Bibliography
참고문헌
참조
인용문헌

처리 방식:

일반 본문 index에는 넣지 않는다.
필요하면 reference 전용 index 또는 metadata로만 보관한다.

즉:

{
  "block_type": "reference",
  "index_target": false
}

또는 검색 가중치를 낮춘다.

{
  "block_type": "reference",
  "boost": 0.1
}
10. 최종적으로는 “문서 구조 트리”를 만들어야 한다

좋은 전처리 결과는 그냥 문자열 리스트가 아니다.

이런 식이어야 한다.

문서
 ├─ Section: 1. 개요
 │   ├─ Paragraph
 │   ├─ Paragraph
 │   └─ Table
 │
 ├─ Section: 2. 방법론
 │   ├─ Paragraph
 │   ├─ Figure Caption
 │   └─ Paragraph
 │
 ├─ Section: 3. 실험 결과
 │   ├─ Paragraph
 │   └─ Table
 │
 └─ References

그리고 각 노드는 이런 정보를 가진다.

{
  "id": "doc1_page3_block7",
  "text": "대출 금리는 신용등급에 따라 차등 적용된다.",
  "type": "paragraph",
  "section_title": "대출 금리 기준",
  "page": 3,
  "bbox": [72.1, 153.4, 412.5, 169.8],
  "reading_order": 17,
  "source_file": "loan_policy.pdf"
}

이 구조가 있어야 나중에 청킹도 좋아진다.

11. 청킹은 파싱 이후에 해야 한다

중요한 포인트다.

파싱이 엉망이면 청킹도 엉망이다.

순서가 깨진 상태에서 chunk를 만들면 이런 일이 생긴다.

chunk 1:
1. 개요
3. 실험 결과
2. 방법론
4. 결론

그러면 벡터 검색 결과도 이상해진다.

그래서 순서는 반드시:

파싱
→ 레이아웃 복원
→ 구조화
→ 그다음 청킹

이어야 한다.

청킹 기준도 단순 글자 수보다는 이렇게 가는 게 좋다.

1순위: section 단위
2순위: paragraph 단위
3순위: table 단위
4순위: token limit 초과 시 하위 분할

예를 들면:

chunk_id: doc1_section_2_chunk_1
section_title: "2. 방법론"
content:
"본 연구에서는..."

표는 표 단독 chunk로 두는 게 좋다.

chunk_id: doc1_table_3
section_title: "대출 금리 기준"
block_type: "table"
content:
"대출 금리 기준 표에서 A등급의 금리는..."
12. 품질 점수를 반드시 남겨야 한다

PDF 파싱은 100% 성공을 기대하면 안 된다.

그래서 각 페이지나 문서마다 품질 점수를 계산해야 한다.

예를 들면:

- 텍스트 추출량이 너무 적은가?
- 글자 단위로 쪼개졌는가?
- 평균 단어 길이가 이상한가?
- y좌표 순서가 심하게 뒤섞였는가?
- 표 후보가 있는데 표 추출에 실패했는가?
- 헤더/푸터 반복 제거가 되었는가?
- OCR이 필요한 이미지 PDF인가?

예시:

{
  "page": 4,
  "parse_quality": 0.62,
  "issues": [
    "two_column_detected",
    "table_detected",
    "possible_footnote_mixed"
  ],
  "fallback_required": true
}

품질이 낮으면 fallback을 태운다.

PyMuPDF 실패
→ pdfplumber 시도
→ Docling/unstructured 시도
→ OCR 시도
→ 그래도 낮으면 수동 검수 대상
13. 실무용 파이프라인은 이렇게 잡으면 된다

내가 추천하는 구조는 이거야.

PDFParser
 ├─ extract_raw_elements()
 │   └─ blocks / words / images / drawings 추출
 │
 ├─ detect_document_type()
 │   └─ 논문 / 보고서 / 약관 / 스캔본 / 표 중심 문서
 │
 ├─ remove_noise()
 │   └─ header / footer / page number 제거
 │
 ├─ analyze_layout()
 │   └─ 1단 / 2단 / mixed / table-heavy 감지
 │
 ├─ reconstruct_reading_order()
 │   └─ 컬럼 분리, full-width block 처리
 │
 ├─ extract_tables()
 │   └─ markdown + semantic text + metadata
 │
 ├─ structure_sections()
 │   └─ heading, paragraph, table, footnote 연결
 │
 ├─ chunk()
 │   └─ section-aware chunking
 │
 ├─ score_quality()
 │   └─ 파싱 품질 점수 계산
 │
 └─ fallback_if_needed()
14. 가장 현실적인 구현 우선순위

처음부터 완벽한 PDF 파서를 만들려고 하면 늪에 빠진다.

우선순위는 이렇게 잡는 게 좋다.

1단계: 텍스트 PDF 기본 처리
- PyMuPDF blocks/words 추출
- y/x 정렬
- 헤더/푸터 제거
- 기본 문단 병합
2단계: 2단 컬럼 처리
- 컬럼 감지
- full-width block 감지
- 컬럼별 읽기 순서 재구성
3단계: 표 처리
- 표 후보 영역 감지
- markdown 변환
- 행 단위 의미 문장 생성
- 표 전용 chunk 생성
4단계: 섹션 구조화
- heading 감지
- section_title 부여
- chunk metadata 강화
5단계: 품질 점수 + fallback
- 파싱 실패 감지
- OCR 또는 layout-aware parser fallback
- 검수 로그 저장
15. 결론적으로 방안은 이거다

PDF 텍스트 순서 깨짐 문제의 해결책은 단순히 “좋은 라이브러리 하나 쓰기”가 아니다.

실무적인 정답은 이거야.

1. 좌표 기반으로 원자 요소를 추출한다.
2. 헤더/푸터/각주/표/본문 영역을 분리한다.
3. 1단/2단/혼합 레이아웃을 감지한다.
4. 컬럼별로 읽기 순서를 재구성한다.
5. 표는 일반 텍스트가 아니라 구조화 + 의미 문장화한다.
6. 섹션 제목과 metadata를 붙인다.
7. 그 이후에 chunking한다.
8. 품질 점수를 남기고, 낮으면 fallback한다.