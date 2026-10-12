# 한글 문서 테스트 픽스처 출처 (hwp-parser Design §8.5)

한글 프로그램으로 만든 실제 파일을 쓴다. 모두 허용 라이선스 공개 저장소에서 원본 그대로 가져왔다.
이름만 바꿨고 내용은 수정하지 않았다.

| 파일 | 원본 | 라이선스 | 용도 |
|------|------|---------|------|
| `hwpjs_basics_report.hwp` | [hahnlee/hwp.js](https://github.com/hahnlee/hwp.js) `packages/parser/src/__tests__/data/basicsReport.hwp` | Apache-2.0 | HWP 5.0 압축 문서, 표 행·셀 표기 (F-01, F-02) |
| `rhwp_footnote_textbox.hwp` | [edwardkim/rhwp](https://github.com/edwardkim/rhwp) `fuzz/corpus/parse_hwp/footnote-tbox-01.hwp` | MIT | 글상자 포함, 본문·글상자 안 각주 제외 (F-05) |
| `rhwp_nested_table.hwpx` | [edwardkim/rhwp](https://github.com/edwardkim/rhwp) `fuzz/corpus/parse_hwpx/centered_cell_nested_table.hwpx` | MIT | HWPX 실파일, 중첩 표 평탄화 (F-03) |

라이선스 원문:
- Apache-2.0: https://www.apache.org/licenses/LICENSE-2.0
- MIT (rhwp): https://github.com/edwardkim/rhwp/blob/main/LICENSE

암호·배포용 문서(F-04)는 허용 라이선스 실파일이 없어 저장소에 넣지 않았다.
FileHeader 비트 단위 테스트(`test_hwp5_reader.py::TestParseFileHeader`)로 고정하고,
pyhwp 공개 픽스처(`password-12345.hwp`, `viewtext.hwp`)로 로컬에서 422 거부를 확인했다
(2026-10-09, 분석 문서 §12).
