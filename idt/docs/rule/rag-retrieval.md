# RAG & Document Rules

> 원본: CLAUDE.md §8

---

## 검색 규칙

- Retrieval은 **Child-first**
- 기본 top-k = 10 (configurable)
- LLM 기반 true/false 문서 압축 수행
- 불충분 시 **Parent Page Requery** 필수
- Parent/Child 메타데이터 누락 ❌
