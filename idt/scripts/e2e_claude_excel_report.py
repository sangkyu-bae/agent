"""실 E2E: Claude 에이전트로 여신 현황 엑셀 → 팀장 보고용 엑셀 생성 (claude-agent-e2e-fixes §8.5).

⚠️ 실 LLM·실 DB를 쓴다. 비용이 든다(Opus 5.5 + data_analysis 조합 1회 약 $1~3).
pytest 수집 대상이 아니다. 로컬에서 수동으로만 실행한다.

흐름: 결정적 입력(600행) + 기대값 생성 → 인프로세스 TestClient 기동 →
`[L3]` 테스트 에이전트 생성 → 실행 → 산출 xlsx 다운로드 → 기대값 대조 →
run 단계·ai_llm_call 조회 → 에이전트 soft delete(finally).

사용 (idt/ 에서):
    OUT_DIR=... E2E_MODEL=claude-opus-5-5 E2E_TOOLS=data_analysis,excel_export \\
        python scripts/e2e_claude_excel_report.py .env <out_dir>

- 유틸리티 LLM·근거 판정 모델도 E2E_MODEL 로 덮어쓴다(프로세스 env만, .env 무변경).
- E2E_MODEL 이 llm_model 에 없으면 anthropic provider 로 등록한다(남겨 둠).
- E2E_USER_ID(기본 7)는 로컬 admin 사용자 id.
"""
import asyncio
import json
import os
import random
import re
import sys
import time
from pathlib import Path

MODEL = os.environ.get("E2E_MODEL", "claude-opus-5-5")
TOOLS = os.environ.get("E2E_TOOLS", "data_analysis,excel_export").split(",")
USER_ID = int(os.environ.get("E2E_USER_ID", "7"))
os.environ["UTILITY_LLM_MODEL_NAME"] = MODEL  # .env 보다 우선 (pydantic settings)
os.environ["GROUNDING_JUDGE_MODEL"] = MODEL

from dotenv import load_dotenv  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows cp949 콘솔 이모지

load_dotenv(sys.argv[1])
sys.path.insert(0, os.getcwd())
OUT = Path(sys.argv[2]) / f"out_{MODEL}_{'+'.join(TOOLS)}"
OUT.mkdir(parents=True, exist_ok=True)

import pandas as pd  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from openpyxl import load_workbook  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from src.api.main import app  # noqa: E402
from src.infrastructure.auth.jwt_adapter import JWTAdapter  # noqa: E402
from src.infrastructure.config.auth_config import AuthConfig  # noqa: E402

SYSTEM_PROMPT = """# 역할
너는 저축은행 여신관리팀의 보고서 작성 담당이다. 사용자가 첨부한 여신 현황 엑셀을 분석하고, 팀장 보고용 엑셀 파일을 만든다.

# 작업 순서
1. 첨부 엑셀로 사용자가 요청한 시트 구성대로 Excel 파일 생성 도구를 호출해 파일을 만든다.
   집계·정렬·필터는 도구가 원천 데이터로 직접 계산하므로, 수치를 미리 세지 않는다.
2. 최종 답변에는 시트별로 무엇을 담았는지와 다운로드 링크를 짧게 적는다.

# 원칙
- 수치는 원천 데이터에서 나온 값만 쓴다. 추정하거나 지어내지 않는다.
- 금액은 원 단위, 금리는 %, 날짜는 날짜 형식으로 보이게 한다.
"""

QUERY = (
    "첨부한 여신 현황 엑셀로 팀장 보고용 엑셀 파일을 만들어줘.\n"
    "1) '연체 고객' 시트: 연체일수 30일 이상인 고객만, 연체일수가 큰 순서로. "
    "컬럼은 고객번호, 고객명, 지점, 상품, 대출잔액, 금리, 연체일수, 실행일.\n"
    "2) '지점별 현황' 시트: 지점별 대출 건수, 대출잔액 합계, 평균 금리. 잔액 합계가 큰 순서로.\n"
    "3) '상품별 현황' 시트: 상품별 대출잔액 합계와 최대 연체일수.\n"
    "금액은 원 단위 천 단위 구분, 금리는 % 형식, 날짜는 날짜 형식으로 보기 좋게 만들어줘."
)

BRANCHES = ["강남", "서초", "송파", "분당", "일산"]
PRODUCTS = ["신용대출", "주택담보대출", "사업자대출"]
SURNAMES = "김이박최정강조윤장임"
report: list[str] = []


def log(*parts) -> None:
    line = " ".join(str(p) for p in parts)
    report.append(line)
    print(line)


# ── 1. 입력 + 기대값 ─────────────────────────────────────────────


def _make_row(rng: random.Random, i: int) -> dict:
    balance = rng.randrange(300, 50000) * 10000
    rate = round(rng.uniform(3.0, 12.0), 1)
    overdue = rng.choice([0] * 6 + [rng.randrange(1, 180)])
    return {
        "고객번호": f"C{i:04d}",
        "고객명": f"{rng.choice(SURNAMES)}고객{i}",
        "지점": rng.choice(BRANCHES),
        "상품": rng.choice(PRODUCTS),
        "대출잔액": f"{balance:,}원",
        "금리": f"{rate}%",
        "연체일수": None if i % 50 == 0 else overdue,  # 빈칸 → float64 열
        "실행일": f"{rng.randrange(2021, 2026)}.{rng.randrange(1, 13):02d}.{rng.randrange(1, 29):02d}",
        "_balance": balance,
        "_rate": rate,
    }


def make_input() -> tuple[Path, dict]:
    rng = random.Random(20261119)
    df = pd.DataFrame([_make_row(rng, i) for i in range(1, 601)])
    path = OUT / "loan_status.xlsx"
    df.drop(columns=["_balance", "_rate"]).to_excel(path, index=False, sheet_name="여신현황")
    od = df[df["연체일수"].fillna(-1) >= 30]
    br = df.groupby("지점").agg(건수=("고객번호", "count"), 잔액=("_balance", "sum"), 금리=("_rate", "mean"))
    pr = df.groupby("상품").agg(잔액=("_balance", "sum"), 연체=("연체일수", "max"))
    expected = {
        "overdue_rows": int(len(od)),
        "overdue_max": float(od["연체일수"].max()),
        "branch": {k: [int(v["건수"]), int(v["잔액"]), round(float(v["금리"]) / 100, 6)]
                   for k, v in br.iterrows()},
        "product": {k: [int(v["잔액"]), float(v["연체"])] for k, v in pr.iterrows()},
    }
    (OUT / "expected.json").write_text(json.dumps(expected, ensure_ascii=False, indent=2), encoding="utf-8")
    return path, expected


# ── 2. 실행 ──────────────────────────────────────────────────────


def _ensure_model(c: TestClient, h: dict) -> str:
    body = c.get("/api/v1/llm-models", headers=h, params={"include_inactive": True}).json()
    models = body if isinstance(body, list) else body.get("models", [])
    for m in models:
        if m.get("model_name") == MODEL:
            return m["id"]
    r = c.post("/api/v1/llm-models", headers=h, json={
        "provider": "anthropic", "model_name": MODEL, "display_name": MODEL,
        "description": "E2E 확인용", "api_key_env": "ANTHROPIC_API_KEY",
        "is_active": True, "is_default": False, "supports_vision": True,
    })
    r.raise_for_status()
    return r.json()["id"]


def _create_agent(c: TestClient, h: dict, model_id: str) -> str:
    r = c.post("/api/v1/agents", headers=h, json={
        "user_request": "여신 현황 엑셀을 분석해 팀장 보고용 엑셀을 만드는 에이전트",
        "name": "[L3] 여신 보고서 엑셀 E2E", "llm_model_id": model_id,
        "tool_ids": TOOLS, "system_prompt": SYSTEM_PROMPT, "max_iterations": 10,
    })
    r.raise_for_status()
    return r.json().get("agent_id") or r.json().get("id")


def _run(c: TestClient, h: dict, agent_id: str, input_path: Path) -> dict:
    t0 = time.time()
    r = c.post(f"/api/v1/agents/{agent_id}/run", headers=h, json={
        "query": QUERY, "user_id": str(USER_ID), "persist_conversation": False,
        "attachments": [{"type": "excel", "file_path": str(input_path.resolve()),
                         "user_id": str(USER_ID)}],
    }, timeout=1800)
    run = {"status": r.status_code, "elapsed_s": round(time.time() - t0, 1), "body": r.json()}
    (OUT / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2, default=str),
                                  encoding="utf-8")
    return run


def _download(c: TestClient, h: dict, run: dict) -> list[Path]:
    answer = json.dumps(run["body"], ensure_ascii=False)
    files = []
    for file_id in dict.fromkeys(re.findall(r"/document-extractor/files/([0-9a-f]{32})", answer)):
        d = c.get(f"/api/v1/document-extractor/files/{file_id}", headers=h)
        if d.status_code == 200:
            path = OUT / f"result_{file_id}.xlsx"
            path.write_bytes(d.content)
            files.append(path)
    return files


# ── 3. 검증 ──────────────────────────────────────────────────────


def _num(v):
    try:
        return float(str(v).replace(",", "").replace("원", "").replace("%", ""))
    except (TypeError, ValueError):
        return None


def _close(a, b, tol: float = 1e-3) -> bool:
    return a is not None and b is not None and abs(a - b) <= tol * max(1.0, abs(b))


def _check_overdue(rows: list[tuple], exp: dict) -> bool:
    hdr, data = list(rows[0]), rows[1:]
    ok = len(data) == exp["overdue_rows"]
    log(f"  행수 {len(data)} (기대 {exp['overdue_rows']})", "OK" if ok else "MISMATCH")
    if "연체일수" not in hdr:
        return False
    col = [_num(r[hdr.index("연체일수")]) for r in data]
    ordered = col == sorted(col, reverse=True)
    log(f"  내림차순 {ordered}, 최댓값 {max(c for c in col if c is not None)} (기대 {exp['overdue_max']})")
    return ok and ordered


def _check_group(rows: list[tuple], exp: dict) -> bool:
    all_ok = True
    for r in rows[1:]:
        want = exp.get(r[0])
        got = [_num(v) for v in r[1:1 + len(want or [])]]
        ok = want is not None and all(_close(g, w) for g, w in zip(got, want))
        all_ok &= ok
        log(f"  {r[0]}: 실제 {got} / 기대 {want}", "OK" if ok else "MISMATCH")
    return all_ok and len(rows) - 1 == len(exp)


def verify(files: list[Path], exp: dict) -> bool:
    if not files:
        log("산출 파일 없음 → FAIL")
        return False
    results = []
    for ws in load_workbook(files[0]).worksheets:
        rows = list(ws.iter_rows(values_only=True))
        log(f"[{ws.title}] {len(rows) - 1}행, 서식 {[c.number_format for c in ws[2]] if len(rows) > 1 else []}")
        if len(rows) < 2:
            results.append(False)
        elif "연체" in ws.title:
            results.append(_check_overdue(rows, exp))
        elif "지점" in ws.title:
            results.append(_check_group(rows, exp["branch"]))
        elif "상품" in ws.title:
            results.append(_check_group(rows, exp["product"]))
    return len(results) == 3 and all(results)


async def query_db(run_id: str) -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.connect() as conn:
        steps = (await conn.execute(text(
            "SELECT step_index, node_name, status, output_summary FROM ai_run_step "
            "WHERE run_id=:r ORDER BY step_index"), {"r": run_id})).all()
        log(f"\n단계 {len(steps)}개")
        for s in steps:
            log(f"  #{s[0]} {s[1]} {s[2]} | {(s[3] or '')[:160].replace(chr(10), ' / ')}")
        calls = (await conn.execute(text(
            "SELECT model_name, prompt_tokens, completion_tokens FROM ai_llm_call "
            "WHERE run_id=:r ORDER BY created_at"), {"r": run_id})).all()
        unknown = sum(1 for c in calls if c[0] == "unknown" or not (c[1] or c[2]))
        log(f"\nai_llm_call {len(calls)}건, unknown/0토큰 {unknown}건 (SC-6 {'OK' if calls and not unknown else 'FAIL'})")
        for c in calls:
            log(f"  {c[0]} in={c[1]} out={c[2]}")
    await engine.dispose()


def main() -> None:
    input_path, expected = make_input()
    with TestClient(app, raise_server_exceptions=False) as c:
        h = {"Authorization": f"Bearer {JWTAdapter(AuthConfig()).create_access_token(USER_ID, 'admin')}"}
        agent_id = _create_agent(c, h, _ensure_model(c, h))
        try:
            run = _run(c, h, agent_id, input_path)
            log(f"HTTP {run['status']} / {run['elapsed_s']}s / model {MODEL} / tools {TOOLS}")
            log("답변:", (run["body"].get("answer") or "")[:1500])
            passed = verify(_download(c, h, run), expected)
            log(f"\n산출 엑셀 검증: {'PASS' if passed else 'FAIL'}")
        finally:
            deleted = c.delete(f"/api/v1/agents/{agent_id}", headers=h)
            log("agent deleted", deleted.status_code)
    if run["body"].get("run_id"):
        asyncio.run(query_db(run["body"]["run_id"]))
    (OUT / "report.txt").write_text("\n".join(report), encoding="utf-8")


if __name__ == "__main__":
    main()
