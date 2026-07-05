"""SourceFileArchiver: 원본 문서 임시→영구 승격 (Design D3 2단계).

extract 시 attachment store(TTL 임시)에 저장된 원본을,
에이전트 생성 확정 시 영구 디렉토리로 복사한다. soft-delete 후에도 보관.
"""
import shutil
from pathlib import Path

from src.domain.logging.interfaces.logger_interface import LoggerInterface


class SourceFileArchiver:
    def __init__(
        self, attachment_store, archive_dir: str, logger: LoggerInterface
    ) -> None:
        self._store = attachment_store
        self._archive_dir = Path(archive_dir)
        self._logger = logger

    def promote(
        self, source_file_id: str, template_id: str, request_id: str
    ) -> str:
        """임시 첨부 → {archive_dir}/{template_id}{ext} 복사 후 영구 경로 반환.

        임시 파일 만료(R4) 시 ValueError — 프론트에 재추출 안내.
        """
        stored = self._store.load(source_file_id)
        if stored is None:
            raise ValueError(
                "업로드한 원본 문서를 찾을 수 없습니다(만료). "
                "문서를 다시 업로드해 추출해주세요."
            )
        ext = Path(stored.file_path).suffix
        self._archive_dir.mkdir(parents=True, exist_ok=True)
        dest = self._archive_dir / f"{template_id}{ext}"
        shutil.copyfile(stored.file_path, dest)
        self._logger.info(
            "SourceFileArchiver promoted",
            request_id=request_id,
            source_file_id=source_file_id,
            dest=str(dest),
        )
        return str(dest)
