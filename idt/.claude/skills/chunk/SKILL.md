---
name: chunk
description: 문서 청킹 모듈 TDD 개발. 청킹, 분할, 토큰 전략 구현시 사용.
argument-hint: "[구현 대상: interface | metadata | config | base-chunker | full-token | parent-child | semantic | factory | service | all]"
---

# CHUNK-001: 문서 청킹 모듈

## 핵심 규칙

### Parent-Child 양방향 참조 (필수)
```json
Parent: {"chunk_id": "{doc_id}_p{page}_parent", "children_ids": [...], "parent_id": null}
Child:  {"chunk_id": "{doc_id}_p{page}_c{idx}", "parent_id": "{parent_chunk_id}"}
```
- `children_ids ↔ parent_id` 정합성 검증 필수
- 반환 시 부모 + 자식 모두 포함

## 구현 순서

`$ARGUMENTS` 미지정시 전체 순서 진행.

| Phase | 대상 | 파일 경로 |
|-------|------|-----------|
| 1 | ChunkingStrategyInterface | `src/domain/chunking/interfaces/...` |
| 1 | ChunkMetadata VO | `src/domain/chunking/value_objects/...` |
| 1 | ChunkingConfig VO | `src/domain/chunking/value_objects/...` |
| 1 | ChunkRequest/Response | `src/domain/chunking/schemas/...` |
| 2 | BaseTokenChunker | `src/infrastructure/chunking/...` |
| 3 | FullTokenStrategy | `src/infrastructure/chunking/strategies/...` |
| 3 | ParentChildStrategy | `src/infrastructure/chunking/strategies/...` |
| 3 | SemanticStrategy | `src/infrastructure/chunking/strategies/...` |
| 4 | ChunkingStrategyFactory | `src/infrastructure/chunking/...` |
| 4 | ChunkingService | `src/domain/chunking/services/...` |

## 참조

- 상세 스펙: `src/claude/task/task-chunk.md`
- TDD 사이클: `tdd` 스킬 준수
- 기존 구현: `src/domain/chunking/`, `src/infrastructure/chunking/`

## 진행 보고 형식
```
[Phase N] 컴포넌트명
[RED]      ✗ test_xxx — ImportError
[GREEN]    ✓ test_xxx — PASSED
[REFACTOR] 변경 없음 / 요약
```

## 예제
```bash
/chunk interface      # Phase 1만 구현
/chunk parent-child   # ParentChildStrategy만 구현
/chunk all           # 전체 순서대로 구현
```