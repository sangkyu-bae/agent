"""워커 산출물 AIMessage.name 이 64자 상한을 거치지 않고 나가는 지점을 막는 가드.

fix-worker-id-name-length: worker_id는 agent_tool에 이미 65자로 저장된 행이 있어
생성 상한만으로는 부족하다. 산출물 메시지를 만드는 모든 지점이 clamp_llm_name을
거쳐야 기존 에이전트도 재저장 없이 동작한다.
"""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src"
# 여러 줄 호출도 잡도록 호출 괄호에 기대지 않는다. 문서열은 `name=<worker_id>` 로 쓴다.
RAW_NAME = re.compile(r"\bname=worker_id\b")


def test_no_worker_output_message_bypasses_clamp():
    offenders = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for m in RAW_NAME.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            offenders.append(f"{path.relative_to(SRC.parent)}:{line}")
    assert not offenders, (
        "AIMessage(name=worker_id) 직접 사용 금지 — "
        "name=clamp_llm_name(worker_id) 로 감싸세요:\n" + "\n".join(offenders)
    )
