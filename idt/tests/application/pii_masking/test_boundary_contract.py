"""pii-masking-integration 경계 계약 테스트 — Design §8.4 (FR-07).

런타임 조립은 DB·LLM이 필요해, 우회 지점은 소스 계약(AST)으로 고정한다.
새 LLM 생성 지점이 생기면 이 테스트가 실패한다 — 허용 목록에 사유를 적거나 guard를
거치게 고친다.
"""

import ast
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
MAIN = SRC / "api" / "main.py"
_CHAT_MODELS = {"ChatOpenAI", "ChatAnthropic", "ChatOllama"}

# 경로 → (생성 횟수, 사유). 대화 경로는 모두 guard 경유이거나,
# provider 주입 시 쓰지 않는 폴백이다.
ALLOWED_DIRECT_CONSTRUCTION: dict[str, tuple[int, str]] = {
    "infrastructure/llm/llm_factory.py": (
        3,
        "팩토리 본체 — PiiGuardedLLMFactory·compiler가 감싼다",
    ),
    "infrastructure/conversation/langchain_llm.py": (1, "llm_guard 주입 (main.py)"),
    "infrastructure/conversation/langchain_summarizer.py": (
        1,
        "llm_guard 주입 (main.py)",
    ),
    "infrastructure/hallucination/adapter.py": (
        2,
        "provider 미주입 레거시 폴백 — main은 provider 주입",
    ),
    "infrastructure/intent/adapter.py": (1, "provider 미주입 레거시 폴백"),
    "infrastructure/memory/extractor.py": (
        1,
        "from_openai 폴백 — main은 provider 주입",
    ),
    "infrastructure/search_decision/adapter.py": (
        1,
        "provider 미주입 레거시 폴백 — main은 provider 주입",
    ),
    "infrastructure/prompt_composer/adapter.py": (1, "provider 미주입 레거시 폴백"),
    "infrastructure/wiki/feedback_distiller.py": (
        1,
        "from_openai 폴백 — 위키 환류(대화 경로 밖)",
    ),
    "infrastructure/wiki/folder_summary_distiller.py": (
        1,
        "위키 폴더 요약(대화 경로 밖)",
    ),
    "infrastructure/wiki/wiki_distiller.py": (1, "위키 생성(대화 경로 밖)"),
    "infrastructure/eval_testset/qa_generator.py": (1, "평가셋 생성(대화 경로 밖)"),
    "infrastructure/ragas/ragas_adapter.py": (1, "RAGAS 평가(대화 경로 밖)"),
    "infrastructure/ragas/target_executor.py": (
        1,
        "RAGAS 평가 대상 실행(대화 경로 밖)",
    ),
    "infrastructure/multi_query/query_generator_adapter.py": (
        1,
        "독립 API, 대화 경로 미사용",
    ),
    "infrastructure/query_rewrite/adapter.py": (1, "독립 API, 대화 경로 미사용"),
    "infrastructure/research_agent/generator_adapter.py": (
        1,
        "research agent 독립 API",
    ),
    "infrastructure/research_agent/relevance_adapter.py": (
        1,
        "research agent 독립 API",
    ),
    "infrastructure/research_agent/router_adapter.py": (1, "research agent 독립 API"),
    "infrastructure/llm_adapter.py": (1, "레거시 어댑터"),
    "infrastructure/llm/claude_client.py": (1, "독립 Claude 클라이언트 API"),
    "infrastructure/llm/ollama/ollama_client.py": (1, "독립 Ollama 클라이언트 API"),
    "api/main.py": (
        1,
        "에이전트 생성 보조(create_agent_composer_factories) — 대화 경로 밖",
    ),
}


# Check G-1 — main.py 에서 raw `_llm_factory` 를 받는 소비자. 팩토리를 받아
# create() 로 직접 호출하는 우회는 위 직접 생성 검사로 잡히지 않는다.
# 새 소비자는 `_pii_llm_factory` 를 받거나 여기에 사유를 적는다.
ALLOWED_RAW_FACTORY_CONSUMERS: dict[str, str] = {
    "WorkflowCompiler": "D-09 — create_agent 에 프록시를 주면 bind_tools 가 깨진다. "
    "compiler 가 런 scope 로 직접 감싼다",
    "GeneralChatUseCase": "create_agent 체인 맨 앞에 PII 미들웨어 부착",
    "MiddlewareProvider": "폴백 모델 — PII 미들웨어 안쪽에서 호출되어 마스킹된 요청을 받는다",
    "SlotExtractor": "문서 템플릿 추출(빌더 도구, 대화 경로 밖)",
    "AgentSpecInferenceService": "에이전트 자동 생성 보조(대화 경로 밖)",
    "RAGAgentUseCase": "/api/v1/rag-agent 독립 API, 프론트 미사용(대화 경로 밖)",
    "wire_multimodal": "관리자 멀티모달 설정·미리보기(대화 경로 밖)",
    "wire_blueprint": "관리자 블루프린트 추출(문서 인제스트, 대화 경로 밖)",
    "PiiGuardedLLMFactory": "guard 본체 — 감싸는 대상",
}


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"))


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _calls(tree: ast.AST, name: str) -> list[ast.Call]:
    return [
        n for n in ast.walk(tree) if isinstance(n, ast.Call) and _call_name(n) == name
    ]


def _kw(call: ast.Call, arg: str) -> ast.expr | None:
    return next((k.value for k in call.keywords if k.arg == arg), None)


def _is_call_to(expr: ast.expr | None, name: str) -> bool:
    return isinstance(expr, ast.Call) and _call_name(expr) == name


def test_direct_chat_model_construction_matches_allowlist():
    found: Counter = Counter()
    for path in SRC.rglob("*.py"):
        for call in ast.walk(_tree(path)):
            if isinstance(call, ast.Call) and _call_name(call) in _CHAT_MODELS:
                found[path.relative_to(SRC).as_posix()] += 1
    expected = {path: count for path, (count, _) in ALLOWED_DIRECT_CONSTRUCTION.items()}
    assert dict(found) == expected


def test_compiler_create_agent_calls_prepend_pii_middleware():
    tree = _tree(SRC / "application" / "agent_builder" / "workflow_compiler.py")
    calls = _calls(tree, "create_agent")
    assert calls
    for call in calls:
        middleware = _kw(call, "middleware")
        assert middleware is not None
        leftmost = middleware
        while isinstance(leftmost, ast.BinOp):
            leftmost = leftmost.left
        assert _is_call_to(leftmost, "_pii_middleware"), ast.dump(leftmost)
        assert isinstance(_kw(call, "model"), ast.Name)
        assert _kw(call, "model").id == "raw_llm"


def test_general_chat_stream_prepends_pii_middleware():
    tree = _tree(SRC / "application" / "general_chat" / "use_case.py")
    stream = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "stream"
    )
    assert _calls(stream, "_pii_middlewares")


def test_main_wires_guarded_factory_into_utility_providers():
    tree = _tree(MAIN)
    providers = _calls(tree, "UtilityLLMProvider")
    assert len(providers) == 2
    for call in providers:
        value = _kw(call, "llm_factory")
        assert isinstance(value, ast.Name) and value.id == "_pii_llm_factory"


def test_main_guards_conversation_llm_adapters():
    tree = _tree(MAIN)
    for name in ("LangChainSummarizer", "LangChainConversationLLM"):
        calls = _calls(tree, name)
        assert calls, name
        for call in calls:
            guard = _kw(call, "llm_guard")
            assert isinstance(guard, ast.Attribute) and guard.attr == "guard", name


def test_main_wires_pii_inspector_into_every_mcp_loader_and_executor():
    tree = _tree(MAIN)
    for name in ("MCPToolLoader", "McpActionExecutor"):
        calls = _calls(tree, name)
        assert calls, name
        for call in calls:
            assert _is_call_to(_kw(call, "pii_inspector"), "get_pii_inspector"), name


def test_main_wires_masker_into_general_chat():
    tree = _tree(MAIN)
    calls = _calls(tree, "GeneralChatUseCase")
    assert calls and all(
        _is_call_to(_kw(c, "pii_masker"), "get_pii_masker") for c in calls
    )


def _raw_factory_consumers(tree: ast.AST) -> Counter:
    """`_llm_factory` 를 인자(위치·키워드)로 받는 호출 대상 이름별 횟수."""
    found: Counter = Counter()
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        values = list(call.args) + [k.value for k in call.keywords]
        if any(isinstance(v, ast.Name) and v.id == "_llm_factory" for v in values):
            found[_call_name(call)] += 1
    return found


def test_raw_llm_factory_consumers_match_allowlist():
    found = _raw_factory_consumers(_tree(MAIN))
    assert set(found) == set(ALLOWED_RAW_FACTORY_CONSUMERS), (
        "raw _llm_factory 소비자가 바뀌었다 — _pii_llm_factory 를 쓰거나 "
        "ALLOWED_RAW_FACTORY_CONSUMERS 에 사유를 적는다"
    )


def test_raw_factory_check_detects_new_consumer():
    # 변이 — 대화 경로 use case 가 raw 팩토리를 받으면 검출된다.
    tree = ast.parse("NewChatUseCase(llm_factory=_llm_factory)\nf(_llm_factory)")
    assert _raw_factory_consumers(tree) == Counter({"NewChatUseCase": 1, "f": 1})


def test_compiler_keeps_raw_llm_factory():
    # compiler에 guarded 팩토리를 넘기면 create_agent가 프록시를 받아
    # bind_tools가 깨진다.
    tree = _tree(MAIN)
    for call in _calls(tree, "WorkflowCompiler"):
        value = _kw(call, "llm_factory")
        assert isinstance(value, ast.Name) and value.id == "_llm_factory"
