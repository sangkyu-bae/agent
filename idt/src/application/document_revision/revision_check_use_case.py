"""RevisionCheckUseCase — 업로드 전 개정 후보 점검.

Design Ref: document-revision §2.2 · §4.2 #1 · §10.5.
상태를 바꾸지 않는다(판정 로그 1행만 기록). 해시 일치면 파싱 없이 duplicate.
LLM·임베딩·로그 실패는 점검을 막지 않는다 (Plan SC-7, NFR 가용성).
"""
from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from collections.abc import Callable

from src.domain.auth.entities import User
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.document_revision.filename_normalizer import (
    filename_similarity,
    normalize_filename,
)
from src.domain.document_revision.interfaces import (
    CandidateHeadReaderPort,
    DocumentRevisionRepositoryPort,
    HeadSimilaritySearchPort,
    RevisionCheckLogRepositoryPort,
    RevisionJudgePort,
)
from src.domain.document_revision.policy import RevisionPolicy
from src.domain.document_revision.value_objects import (
    CheckSource,
    CheckVerdict,
    DocumentVersion,
    JudgeOutcome,
    LlmStatus,
    RevisionCandidate,
    RevisionCheckLogEntry,
    RevisionCheckResult,
    RevisionScoringConfig,
)
from src.domain.knowledge_base.entities import KnowledgeBase
from src.domain.knowledge_base.interfaces import KnowledgeBaseRepositoryInterface
from src.domain.knowledge_base.policy import KnowledgeBasePolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.parser.exceptions import UnsupportedFileFormatError

_JUDGE_HEAD_CHARS = 1500

# 판정 1건 결과: (판정, 실패 여부). 판정 None + 실패 False = 모델 미설정(skipped)
_JudgeResult = tuple[JudgeOutcome | None, bool]


class RevisionCheckUseCase:
    def __init__(
        self,
        kb_repo: KnowledgeBaseRepositoryInterface,
        policy: KnowledgeBasePolicy,
        dept_repo: DepartmentRepositoryInterface,
        parser,
        revision_repo: DocumentRevisionRepositoryPort,
        check_log_repo: RevisionCheckLogRepositoryPort,
        similarity: HeadSimilaritySearchPort,
        head_reader: CandidateHeadReaderPort,
        judge: RevisionJudgePort,
        config: RevisionScoringConfig,
        logger: LoggerInterface,
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        self._kb_repo = kb_repo
        self._policy = policy
        self._dept_repo = dept_repo
        self._parser = parser
        self._revision_repo = revision_repo
        self._check_log = check_log_repo
        self._similarity = similarity
        self._head_reader = head_reader
        self._judge = judge
        self._cfg = config
        self._logger = logger
        self._new_id = id_factory

    async def execute(
        self,
        kb_id: str,
        user: User,
        file_bytes: bytes,
        filename: str,
        request_id: str,
    ) -> RevisionCheckResult:
        started = time.perf_counter()
        kb = await self._authorize(kb_id, user, request_id)
        check_id = self._new_id()
        file_hash = hashlib.sha256(file_bytes).hexdigest()

        duplicates = await self._revision_repo.find_by_hash(kb.id, file_hash, request_id)
        if duplicates:
            existing = next((d for d in duplicates if d.is_active), duplicates[0])
            result = RevisionCheckResult(
                check_id=check_id, verdict=CheckVerdict.DUPLICATE,
                duplicate_of=existing, candidates=[], suggested_document_id=None,
                llm_status=LlmStatus.SKIPPED, elapsed_ms=_ms(started),
            )
            await self._save_log(kb, user, filename, file_hash, result, 0, request_id)
            return result

        parse_started = time.perf_counter()
        head = await self._parse_head(file_bytes, filename, user, request_id)
        parse_ms = _ms(parse_started)

        active = {
            v.document_id: v
            for v in await self._revision_repo.find_active_by_kb(kb.id, request_id)
        }
        filename_scores = {
            doc_id: filename_similarity(filename, v.filename)
            for doc_id, v in active.items()
        }
        content_scores = await self._content_scores(kb, head, active, request_id)
        picked = RevisionPolicy.select_candidates(
            filename_scores, content_scores, self._cfg
        )
        candidates, llm_status = await self._judge_candidates(
            filename, head, picked, active, request_id
        )
        verdict, suggested = RevisionPolicy.decide_verdict(
            candidates, llm_status, self._cfg
        )
        result = RevisionCheckResult(
            check_id=check_id, verdict=verdict, duplicate_of=None,
            candidates=candidates, suggested_document_id=suggested,
            llm_status=llm_status, elapsed_ms=_ms(started),
        )
        self._logger.info(
            "Revision check completed",
            request_id=request_id, kb_id=kb.id, check_id=check_id,
            verdict=verdict.value, candidates=len(candidates),
            llm_status=llm_status.value, elapsed_ms=result.elapsed_ms,
            parse_ms=parse_ms,
        )
        await self._save_log(kb, user, filename, file_hash, result, parse_ms, request_id)
        return result

    # ── 단계 ──────────────────────────────────────────────
    async def _authorize(
        self, kb_id: str, user: User, request_id: str
    ) -> KnowledgeBase:
        kb = await self._kb_repo.find_by_id(kb_id, request_id)
        if kb is None:
            raise ValueError(f"Knowledge base '{kb_id}' not found")
        dept_ids: list[str] = []
        if user.id is not None:
            depts = await self._dept_repo.find_departments_by_user(user.id, request_id)
            dept_ids = [d.department_id for d in depts]
        if not self._policy.can_write(user, kb, dept_ids):
            raise PermissionError(f"No write access to knowledge base '{kb_id}'")
        return kb

    async def _parse_head(
        self, file_bytes: bytes, filename: str, user: User, request_id: str
    ) -> str:
        """앞부분 텍스트. 미지원 확장자는 업로드와 같이 422, 그 밖의 파싱 실패는
        본문 신호 없이 파일명만으로 점검을 이어간다 (Act-1 I3, Plan SC-7)."""
        try:
            parsed = await asyncio.to_thread(
                self._parser.parse_bytes, file_bytes, filename, str(user.id)
            )
        except UnsupportedFileFormatError:
            raise
        except Exception as e:
            self._logger.warning(
                "Revision check parse failed (filename only)",
                request_id=request_id, filename=filename, exception=e,
            )
            return ""
        head = "".join(getattr(d, "page_content", "") or "" for d in parsed)
        return head[: self._cfg.head_chars]

    async def _content_scores(
        self,
        kb: KnowledgeBase,
        head: str,
        active: dict[str, DocumentVersion],
        request_id: str,
    ) -> dict[str, float]:
        if not head or not active:
            return {}
        try:
            scores = await self._similarity.search(
                collection_name=kb.collection_name, kb_id=kb.id,
                head_text=head, request_id=request_id,
            )
        except Exception as e:
            self._logger.warning(
                "Revision content similarity failed (filename only)",
                request_id=request_id, kb_id=kb.id, exception=e,
            )
            return {}
        return {d: s for d, s in scores.items() if d in active}

    async def _judge_candidates(
        self,
        filename: str,
        head: str,
        picked: list[tuple[str, float, float]],
        active: dict[str, DocumentVersion],
        request_id: str,
    ) -> tuple[list[RevisionCandidate], LlmStatus]:
        if not picked:
            return [], LlmStatus.SKIPPED
        to_judge = picked[: self._cfg.llm_top_m]
        judged: list[_JudgeResult] = list(
            await asyncio.gather(
                *(
                    self._judge_one(filename, head, active[doc_id], request_id)
                    for doc_id, _, _ in to_judge
                )
            )
        )
        candidates = []
        for i, (doc_id, fname, content) in enumerate(picked):
            outcome = judged[i][0] if i < len(judged) else None
            v = active[doc_id]
            candidates.append(
                RevisionCandidate(
                    document_id=doc_id, filename=v.filename, version_no=v.version_no,
                    version_label=v.version_label, filename_score=fname,
                    content_score=content,
                    combined_score=RevisionPolicy.combined_score(fname, content, self._cfg),
                    llm_verdict=outcome.verdict if outcome else None,
                    llm_reason=outcome.reason if outcome else None,
                )
            )
        if any(failed for _, failed in judged):
            status = LlmStatus.FAILED
        elif any(outcome is not None for outcome, _ in judged):
            status = LlmStatus.OK
        else:
            status = LlmStatus.SKIPPED
        return candidates, status

    async def _judge_one(
        self, filename: str, head: str, candidate: DocumentVersion, request_id: str
    ) -> _JudgeResult:
        try:
            candidate_head = await self._head_reader.read(
                candidate.document_id, _JUDGE_HEAD_CHARS, request_id
            )
            outcome = await asyncio.wait_for(
                self._judge.judge(
                    new_filename=filename, new_head=head[:_JUDGE_HEAD_CHARS],
                    candidate_filename=candidate.filename,
                    candidate_head=candidate_head, request_id=request_id,
                ),
                timeout=self._cfg.llm_timeout_s,
            )
            return outcome, False
        except Exception as e:  # TimeoutError 포함
            self._logger.warning(
                "Revision judge failed (score fallback)",
                request_id=request_id, document_id=candidate.document_id,
                exception=e,
            )
            return None, True

    async def _save_log(
        self,
        kb: KnowledgeBase,
        user: User,
        filename: str,
        file_hash: str,
        result: RevisionCheckResult,
        parse_ms: int,
        request_id: str,
    ) -> None:
        try:
            await self._check_log.save(
                RevisionCheckLogEntry(
                    check_id=result.check_id, kb_id=kb.id, user_id=str(user.id),
                    source=CheckSource.PRECHECK, filename=filename,
                    normalized_name=normalize_filename(filename), file_hash=file_hash,
                    verdict=result.verdict.value,
                    suggested_document_id=result.suggested_document_id,
                    candidates=result.candidates, llm_status=result.llm_status,
                    elapsed_ms=result.elapsed_ms, parse_ms=parse_ms,
                ),
                request_id,
            )
        except Exception as e:
            self._logger.warning(
                "Revision check log save failed",
                request_id=request_id, check_id=result.check_id, exception=e,
            )


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
