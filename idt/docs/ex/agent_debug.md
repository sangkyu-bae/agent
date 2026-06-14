LangSmith = 디버깅/관측/평가용
LangGraph Checkpointer = 그래프 실행 상태 복구/재개용
우리 DB = 서비스 원장/업무 데이터/사용자 이력용

LangGraph 공식 문서에서도 checkpointer를 쓰면 각 실행 step마다 graph state가 checkpoint로 저장되고, thread_id를 기준으로 상태를 저장/복구한다고 설명한다. 이건 “그래프 런타임 상태 저장소”에 가깝다.
LangSmith는 trace를 통해 애플리케이션이 input에서 output까지 가는 실행 단계를 run 단위로 시각화하고, 디버깅/평가/모니터링에 쓰는 도구다.

그래서 네가 만드는 사용자 커스텀 에이전트 플랫폼 기준으로는 보통 이렇게 간다.

사용자 질문
  ↓
우리 DB: conversation / message / run 생성
  ↓
LangGraph 실행
  ↓
LangSmith: trace 자동 기록
LangGraph Checkpointer: graph state checkpoint 저장
우리 DB: 의미 있는 step/tool/final answer/error 저장
  ↓
UI: SSE로 진행상태 + 최종 답변 표시
1. 저장 책임 분리
저장 위치	저장 목적	예시
LangSmith	개발자 관측, 디버깅, 평가, 비용/토큰 분석	어느 노드가 느렸는지, 어떤 tool이 호출됐는지, LLM input/output
LangGraph Checkpointer	그래프 실행 상태 저장, resume, interrupt, time travel	thread_id 기준 checkpoint, node state, pending writes
우리 DB	서비스 기능, 사용자 화면, 권한, 감사, 과금, 이력	대화방, 질문/답변, 실행 상태, 선택된 에이전트, tool 실행 결과 요약, 사용자 피드백

핵심은 LangSmith는 서비스 DB가 아니다라는 거다. LangSmith에도 run 구조, input/output, token, cost 같은 데이터가 저장되지만, 그건 관측 플랫폼의 데이터 모델이다. LangSmith 공식 문서도 run을 id, inputs, outputs, run_type, start_time, end_time, error, total_tokens, total_cost 같은 span record로 설명한다.

서비스에서 필요한 건 이런 거다.

"이 사용자가 어떤 에이전트로 어떤 질문을 했고,
어떤 문서를 참고했고,
최종 답변은 무엇이었고,
실패했는지 성공했는지,
다시 열람 가능한지,
권한상 볼 수 있는지"

이건 반드시 우리 DB의 도메인 모델로 가져가야 한다.

2. 추천 테이블 구조 예시

너희 플랫폼 기준이면 최소 이 정도는 잡는 게 좋다.

-- 대화 단위
CREATE TABLE ai_conversation (
    id                  UUID PRIMARY KEY,
    user_id             VARCHAR(100) NOT NULL,
    agent_id            UUID NOT NULL,
    langgraph_thread_id VARCHAR(150) NOT NULL UNIQUE,
    title               TEXT,
    created_at          TIMESTAMP NOT NULL DEFAULT now(),
    updated_at          TIMESTAMP NOT NULL DEFAULT now()
);

-- 사용자/AI 메시지
CREATE TABLE ai_message (
    id              UUID PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES ai_conversation(id),
    role            VARCHAR(20) NOT NULL, -- user / assistant / system
    content         TEXT NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT now()
);

-- 한 번의 LangGraph 실행 단위
CREATE TABLE ai_run (
    id                    UUID PRIMARY KEY,
    conversation_id        UUID NOT NULL REFERENCES ai_conversation(id),
    user_message_id        UUID REFERENCES ai_message(id),
    status                VARCHAR(30) NOT NULL, -- RUNNING / SUCCESS / FAILED / CANCELLED
    langgraph_thread_id    VARCHAR(150) NOT NULL,
    langsmith_trace_id     VARCHAR(150),
    started_at             TIMESTAMP NOT NULL DEFAULT now(),
    ended_at               TIMESTAMP,
    error_message          TEXT
);

-- 의미 있는 노드 실행 기록
CREATE TABLE ai_run_step (
    id          UUID PRIMARY KEY,
    run_id      UUID NOT NULL REFERENCES ai_run(id),
    node_name   VARCHAR(100) NOT NULL,
    status      VARCHAR(30) NOT NULL, -- STARTED / SUCCESS / FAILED
    input_json  JSONB,
    output_json JSONB,
    started_at  TIMESTAMP NOT NULL DEFAULT now(),
    ended_at    TIMESTAMP,
    error_text  TEXT
);

-- Tool 호출 기록
CREATE TABLE ai_tool_call (
    id              UUID PRIMARY KEY,
    run_id          UUID NOT NULL REFERENCES ai_run(id),
    step_id         UUID REFERENCES ai_run_step(id),
    tool_name       VARCHAR(100) NOT NULL,
    arguments_json  JSONB,
    result_summary  TEXT,
    result_json     JSONB,
    latency_ms      INT,
    status          VARCHAR(30) NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT now()
);

-- RAG 검색 근거
CREATE TABLE ai_retrieval_source (
    id              UUID PRIMARY KEY,
    run_id          UUID NOT NULL REFERENCES ai_run(id),
    collection_name VARCHAR(100),
    document_id     VARCHAR(150),
    chunk_id        VARCHAR(150),
    score           NUMERIC(10, 6),
    content_preview TEXT,
    metadata_json   JSONB,
    created_at      TIMESTAMP NOT NULL DEFAULT now()
);

여기서 중요한 건 LangGraph checkpoint 테이블과 서비스 테이블을 섞지 않는 것이다. LangGraph는 production에서 Postgres checkpointer도 제공하고, 공식 문서상 langgraph-checkpoint-postgres는 production 용도에 적합한 checkpointer로 설명된다.
하지만 그 테이블은 “그래프 상태 저장용”이고, ai_conversation, ai_message, ai_run 같은 테이블은 “서비스 도메인용”이다.

3. ID 매핑을 통일하는 게 핵심

추천은 이거다.

conversation_id      = 우리 서비스 대화 ID
langgraph_thread_id  = conversation_id와 같게 두거나, 별도 UUID로 두되 DB에 매핑
run_id               = 질문 1회 실행 ID
langsmith metadata   = thread_id, run_id, user_id, agent_id 넣기

LangSmith도 여러 trace를 하나의 conversation/thread로 묶으려면 metadata에 session_id, thread_id, conversation_id 중 하나를 넣으라고 설명하고, UUID v7 thread id를 권장한다.
LangGraph checkpointer도 thread_id를 기준으로 checkpoint를 저장/복구하므로, 이 값을 우리 DB의 conversation과 강하게 연결해두는 게 좋다.

예시:

conversation_id = "01974f2a-..."  # 우리 DB ai_conversation.id
run_id = "01974f2b-..."           # 우리 DB ai_run.id

config = {
    "configurable": {
        "thread_id": conversation_id
    },
    "metadata": {
        "thread_id": conversation_id,
        "conversation_id": conversation_id,
        "run_id": run_id,
        "user_id": user_id,
        "agent_id": agent_id,
        "environment": "production"
    },
    "tags": ["rag-agent", "production"]
}

이렇게 해두면 나중에 LangSmith에서 trace를 보다가도 “아 이게 우리 DB의 어떤 run이구나” 하고 역추적이 된다. LangSmith 공식 문서도 trace에 metadata와 tags를 붙일 수 있다고 설명한다.

4. 실제 실행 흐름 예시

예를 들어 사용자가 이렇게 물었다고 치자.

"우리 회사 휴가 규정 알려줘"
1단계: API 진입 시 DB insert
conversation = create_conversation_if_absent(
    user_id=user_id,
    agent_id=agent_id,
)

user_message = insert_message(
    conversation_id=conversation.id,
    role="user",
    content=user_input,
)

run = insert_run(
    conversation_id=conversation.id,
    user_message_id=user_message.id,
    status="RUNNING",
    langgraph_thread_id=str(conversation.id),
)

여기까지는 LangGraph 실행 전에 먼저 넣는 게 좋다. 그래야 중간에 LangGraph가 터져도 “사용자가 뭘 요청했고 어디서 실패했는지”가 남는다.

2단계: LangGraph 실행

LangGraph streaming은 updates, values, messages, custom, checkpoints, tasks, debug 같은 stream mode를 제공하고, updates는 각 step 이후 상태 업데이트, messages는 LLM token stream, custom은 node에서 임의로 내보내는 진행 상태에 사용할 수 있다.

async for event in graph.astream(
    {"messages": [{"role": "user", "content": user_input}]},
    config=config,
    stream_mode=["updates", "messages", "custom"],
    version="v2",
):
    event_type = event["type"]

    if event_type == "custom":
        # 예: {"status": "문서 검색 중", "node": "retrieve_policy"}
        await send_sse(event["data"])

    elif event_type == "updates":
        # 노드 단위 업데이트 저장
        for node_name, node_output in event["data"].items():
            insert_run_step(
                run_id=run.id,
                node_name=node_name,
                status="SUCCESS",
                output_json=node_output,
            )

    elif event_type == "messages":
        # 토큰은 매번 DB insert 하지 말고 SSE로만 보내거나 buffer 후 저장
        message_chunk, metadata = event["data"]
        await send_sse({
            "type": "token",
            "content": message_chunk.content
        })

여기서 주의할 점은 LLM token을 매 토큰마다 DB insert 하지 않는 것이다. 그건 DB를 괴롭히는 구조다. 보통은 SSE로 실시간 전송하고, 최종 답변 문자열만 ai_message에 저장한다. 토큰 단위 로그가 정말 필요하면 Redis/buffer에 모았다가 batch insert하는 식이 낫다.

3단계: Tool/RAG 노드에서 의미 있는 데이터 저장

예를 들어 retrieve_policy 노드가 있다고 하면:

def retrieve_policy_node(state, config):
    run_id = config["metadata"]["run_id"]

    results = vector_store.search(
        query=state["messages"][-1].content,
        collection="hr_policy",
        top_k=5
    )

    for r in results:
        insert_retrieval_source(
            run_id=run_id,
            collection_name="hr_policy",
            document_id=r.document_id,
            chunk_id=r.chunk_id,
            score=r.score,
            content_preview=r.content[:500],
            metadata_json=r.metadata,
        )

    return {
        "retrieved_docs": [
            {
                "document_id": r.document_id,
                "chunk_id": r.chunk_id,
                "score": r.score,
                "content": r.content,
            }
            for r in results
        ]
    }

이건 LangSmith에도 trace로 보일 수 있지만, 우리 서비스에서는 “이 답변이 어떤 문서 근거로 나왔는가”를 UI에 보여주거나, 감사/품질평가/피드백에 써야 하므로 DB에 따로 저장하는 게 맞다.

4단계: 최종 답변 저장
try:
    final_answer = collected_answer_text

    assistant_message = insert_message(
        conversation_id=conversation.id,
        role="assistant",
        content=final_answer,
    )

    update_run_success(
        run_id=run.id,
        ended_at=now(),
    )

except Exception as e:
    update_run_failed(
        run_id=run.id,
        error_message=str(e),
        ended_at=now(),
    )
    raise

최종적으로 UI에서 대화 이력을 불러올 때는 LangSmith를 조회하는 게 아니라 우리 DB의 ai_conversation, ai_message를 조회해야 한다.

5. 저장하면 좋은 것 / 저장하지 않는 게 좋은 것
구분	우리 DB 저장 여부	이유
사용자 질문	저장	대화 이력, 재조회, 감사
최종 AI 답변	저장	서비스 핵심 데이터
run 상태	저장	실패/성공/재시도 관리
선택된 agent/tool	저장	분석, 권한, 디버깅
RAG 검색 문서/chunk id	저장	답변 근거, 품질평가
tool input/output 요약	저장	장애 분석, 감사
모든 token	보통 비추천	저장량 과다, 성능 부담
모든 checkpoint state	직접 저장 비추천	LangGraph checkpointer 책임
전체 프롬프트 원문	주의해서 저장	개인정보/내부정보 위험
LangSmith trace 전체 복제	비추천	중복 저장, 비용/복잡도 증가

특히 금융/내부망/사내문서 쪽이면 LangSmith에 민감정보가 흘러가지 않게 조심해야 한다. LangSmith 문서도 sensitive data가 trace에 기록되지 않도록 anonymizer를 적용할 수 있다고 안내한다.

6. 네 플랫폼 기준 최종 권장 구조

너희가 만들려는 구조가:

사용자
  → 커스텀 Agent 선택
  → Agent에 Tool/MCP/RAG Collection 연결
  → Supervisor가 Sub Agent 라우팅
  → 최종 답변

이면 DB 저장은 이렇게 가는 게 좋다.

agent_definition
agent_tool_mapping
agent_collection_mapping
conversation
message
run
run_step
tool_call
retrieval_source
feedback

그리고 LangGraph/LangSmith와는 이렇게 연결한다.

우리 DB conversation.id
        ↓
LangGraph configurable.thread_id
        ↓
LangSmith metadata.thread_id / conversation_id
        ↓
우리 DB run.id = LangSmith metadata.run_id

즉 결론은 이거다.

LangSmith는 “개발자가 보는 블랙박스 기록”이고,
우리 DB는 “서비스가 책임지는 업무 원장”이다.

그래서 LangSmith를 쓰더라도 우리 DB insert는 필요하다.
단, 모든 LangGraph 내부 상태를 복제하지 말고,
사용자/서비스/운영/감사에 의미 있는 이벤트만 저장하는 게 맞다.