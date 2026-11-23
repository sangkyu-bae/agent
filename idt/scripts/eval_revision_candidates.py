"""document-revision SC-3 평가 — 개정 후보 사전 점검의 top-1 정확도·무관 문서 오제안율.

Design Ref: document-revision §8.5. 합성 픽스처(tests/fixtures/document_revision/revision_pairs.json)로
일회용 KB 를 만들어 base 문서를 적재하고, probe 마다 POST .../revision-check 를 실행한다.
실 Qdrant·ES·MySQL·임베딩·보조 LLM 을 쓰는 인프로세스 실행이며, 끝나면 KB·컬렉션을 지운다.

사용법 (idt/.env 가 있는 디렉터리에서):
    python scripts/eval_revision_candidates.py [--out result.json] [--user-id 7]
판정 기준(Plan SC-3): 개정 probe top-1 정확도 ≥ 90%, 무관 probe 오제안율 ≤ 5%.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

IDT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(IDT))
FIXTURE = IDT / "tests" / "fixtures" / "document_revision" / "revision_pairs.json"


def make_pdf(paragraphs: list[str]) -> bytes:
    import fitz  # PyMuPDF — 한글은 내장 CJK 글꼴(korea)

    doc = fitz.open()
    page = doc.new_page()
    y = 60
    for para in paragraphs:
        for i in range(0, len(para), 38):
            page.insert_text((50, y), para[i : i + 38], fontname="korea", fontsize=11)
            y += 18
            if y > 780:
                page, y = doc.new_page(), 60
        y += 8
    return doc.tobytes()


def judge(expect: str, base_ids: dict[str, str], result: dict) -> bool:
    if expect == "duplicate":
        return result.get("verdict") == "duplicate"
    if expect == "new":
        return result.get("verdict") == "new"
    return (
        result.get("verdict") == "revision_candidate"
        and result.get("suggested_document_id") == base_ids[expect]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="")
    parser.add_argument("--user-id", type=int, default=7)
    args = parser.parse_args()

    from dotenv import load_dotenv

    load_dotenv(Path.cwd() / ".env")
    from fastapi.testclient import TestClient

    from src.api.main import app
    from src.infrastructure.auth.jwt_adapter import JWTAdapter
    from src.infrastructure.config.auth_config import AuthConfig

    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    base_bytes = {k: make_pdf(v["paragraphs"]) for k, v in fixture["base"].items()}
    rows: list[dict] = []
    kb_id = collection = None

    with TestClient(app, raise_server_exceptions=False) as client:
        token = JWTAdapter(AuthConfig()).create_access_token(args.user_id, "admin")
        h = {"Authorization": f"Bearer {token}"}
        base = "/api/v1/knowledge-bases"
        try:
            keys = list(fixture["base"])
            first = keys[0]
            r = client.post(
                f"{base}/quick", headers=h,
                data={"name": f"[EVAL] revision {int(time.time())}", "scope": "PERSONAL"},
                files=[("files", (fixture["base"][first]["filename"], base_bytes[first], "application/pdf"))],
            )
            r.raise_for_status()
            q = r.json()
            kb_id, collection = q["kb_id"], q["collection_name"]
            base_ids = {first: q["documents"][0]["document_id"]}
            for key in keys[1:]:
                r = client.post(
                    f"{base}/{kb_id}/documents", headers=h,
                    files={"file": (fixture["base"][key]["filename"], base_bytes[key], "application/pdf")},
                )
                r.raise_for_status()
                base_ids[key] = r.json()["document_id"]

            for probe in fixture["probes"]:
                data = (
                    base_bytes[probe["same_bytes_as"]]
                    if "same_bytes_as" in probe
                    else make_pdf(probe["paragraphs"])
                )
                r = client.post(
                    f"{base}/{kb_id}/documents/revision-check", headers=h,
                    files={"file": (probe["filename"], data, "application/pdf")},
                )
                result = r.json()
                top = (result.get("candidates") or [None])[0]
                rows.append({
                    "probe": probe["name"],
                    "expect": probe["expect"],
                    "status": r.status_code,
                    "verdict": result.get("verdict"),
                    "suggested": next(
                        (k for k, v in base_ids.items() if v == result.get("suggested_document_id")),
                        None,
                    ),
                    "top_candidate": top and {
                        "doc": next((k for k, v in base_ids.items() if v == top["document_id"]), None),
                        "filename": top["filename_score"],
                        "content": top["content_score"],
                        "combined": top["combined_score"],
                        "llm": top["llm_verdict"],
                    },
                    "llm_status": result.get("llm_status"),
                    "elapsed_ms": result.get("elapsed_ms"),
                    "ok": judge(probe["expect"], base_ids, result),
                })
        finally:
            if kb_id:
                listing = client.get(f"{base}/{kb_id}/documents", headers=h, params={"limit": 100})
                for d in listing.json().get("documents", []):
                    client.delete(f"{base}/{kb_id}/documents/{d['document_id']}", headers=h)
                client.delete(f"{base}/{kb_id}", headers=h)
            if collection:
                client.delete(f"/api/v1/collections/{collection}", headers=h)

    revision = [r for r in rows if r["expect"] not in ("new", "duplicate")]
    unrelated = [r for r in rows if r["expect"] == "new"]
    summary = {
        "top1_accuracy": sum(r["ok"] for r in revision) / max(len(revision), 1),
        "false_suggestion_rate": sum(r["verdict"] == "revision_candidate" for r in unrelated)
        / max(len(unrelated), 1),
        "duplicate_ok": all(r["ok"] for r in rows if r["expect"] == "duplicate"),
        "overall": sum(r["ok"] for r in rows) / max(len(rows), 1),
        "probes": rows,
    }
    text = json.dumps(summary, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
