"""WorkflowCompiler: WorkflowDefinition → Custom StateGraph CompiledGraph 동적 컴파일."""
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import create_react_agent

from src.application.agent_builder.supervisor_hooks import DefaultHooks, SupervisorHooks
from src.application.agent_builder.supervisor_nodes import (
    build_initial_state,
    create_quality_gate_node,
    create_supervisor_node,
    route_after_quality,
    route_to_worker,
)
from src.application.agent_builder.supervisor_state import SupervisorState
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_builder.policies import (
    CircularReferencePolicy,
    NestingDepthPolicy,
    QualityGatePolicy,
)
from src.domain.agent_builder.schemas import SupervisorConfig, WorkerDefinition, WorkflowDefinition
from src.domain.agent_builder.tool_registry import get_tool_meta
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.agent_builder.tool_factory import ToolFactory


class WorkflowCompiler:
    """WorkflowDefinition → Custom StateGraph CompiledGraph 동적 컴파일."""

    def __init__(
        self,
        tool_factory: ToolFactory,
        llm_factory: LLMFactoryInterface,
        logger: LoggerInterface,
        hooks: SupervisorHooks | None = None,
        agent_repository: AgentDefinitionRepositoryInterface | None = None,
        llm_model_repository: LlmModelRepositoryInterface | None = None,
    ) -> None:
        self._tool_factory = tool_factory
        self._llm_factory = llm_factory
        self._logger = logger
        self._hooks = hooks or DefaultHooks()
        self._agent_repository = agent_repository
        self._llm_model_repository = llm_model_repository

    async def compile(
        self,
        workflow: WorkflowDefinition,
        llm_model: LlmModel,
        request_id: str,
        temperature: float = 0.0,
        supervisor_config: SupervisorConfig | None = None,
        depth: int = 0,
        visited: set[str] | None = None,
    ):
        NestingDepthPolicy.validate_depth(depth)

        config = supervisor_config or SupervisorConfig()
        self._logger.info(
            "WorkflowCompiler compile start",
            request_id=request_id,
            worker_count=len(workflow.workers),
            provider=llm_model.provider,
            model_name=llm_model.model_name,
            depth=depth,
        )
        try:
            llm = self._llm_factory.create(llm_model, temperature)
            policy = QualityGatePolicy()

            worker_map: dict[str, object] = {}
            has_search_workers = False

            for worker_def in workflow.workers:
                if worker_def.worker_type == "sub_agent":
                    sub_node = await self._compile_sub_agent(
                        worker_def=worker_def,
                        llm_model=llm_model,
                        request_id=request_id,
                        temperature=temperature,
                        supervisor_config=config,
                        depth=depth + 1,
                        visited=visited or set(),
                    )
                    worker_map[worker_def.worker_id] = sub_node
                else:
                    if worker_def.tool_id.startswith("mcp_"):
                        tool = await self._tool_factory.create_async(
                            worker_def.tool_id, request_id,
                            tool_config=worker_def.tool_config,
                        )
                    else:
                        tool = self._tool_factory.create(
                            worker_def.tool_id, request_id,
                            tool_config=worker_def.tool_config,
                        )
                    category = self._resolve_category(worker_def)

                    if category == "search":
                        worker_map[worker_def.worker_id] = self._create_search_node(
                            worker_def.worker_id, tool,
                        )
                        has_search_workers = True
                    else:
                        worker_agent = create_react_agent(
                            llm, tools=[tool], name=worker_def.worker_id,
                        )
                        worker_map[worker_def.worker_id] = worker_agent

            workers_for_supervisor = list(workflow.workers)
            if has_search_workers:
                workers_for_supervisor.append(
                    WorkerDefinition(
                        tool_id="__virtual__",
                        worker_id="answer_agent",
                        description="검색 결과를 종합하여 최종 답변을 생성합니다. 모든 검색이 완료된 후 호출하세요.",
                        sort_order=9999,
                    )
                )

            supervisor_fn = create_supervisor_node(
                llm=llm,
                workers=workers_for_supervisor,
                supervisor_prompt=workflow.supervisor_prompt,
                hooks=self._hooks,
                logger=self._logger,
            )
            quality_gate_fn = create_quality_gate_node(
                policy=policy, logger=self._logger,
            )

            graph = StateGraph(SupervisorState)
            graph.add_node("supervisor", supervisor_fn)
            graph.add_node("quality_gate", quality_gate_fn)

            for worker_id, worker_agent in worker_map.items():
                if isinstance(worker_agent, type(lambda: None)):
                    graph.add_node(worker_id, worker_agent)
                else:
                    graph.add_node(
                        worker_id,
                        self._wrap_worker(worker_id, worker_agent),
                    )

            if has_search_workers:
                graph.add_node(
                    "answer_agent",
                    self._create_answer_node(llm, workflow.supervisor_prompt),
                )

            graph.set_entry_point("supervisor")

            route_map = {wid: wid for wid in worker_map}
            if has_search_workers:
                route_map["answer_agent"] = "answer_agent"
            route_map["__end__"] = END
            graph.add_conditional_edges("supervisor", route_to_worker, route_map)

            for worker_id in worker_map:
                graph.add_edge(worker_id, "quality_gate")

            if has_search_workers:
                graph.add_edge("answer_agent", END)

            qg_route_map = {"supervisor": "supervisor"}
            for wid in worker_map:
                qg_route_map[wid] = wid
            graph.add_conditional_edges("quality_gate", route_after_quality, qg_route_map)

            compiled = graph.compile()
            self._logger.info("WorkflowCompiler compile done", request_id=request_id)
            return compiled
        except Exception as e:
            self._logger.error(
                "WorkflowCompiler compile failed", exception=e, request_id=request_id,
            )
            raise

    async def _compile_sub_agent(
        self,
        worker_def: WorkerDefinition,
        llm_model: LlmModel,
        request_id: str,
        temperature: float,
        supervisor_config: SupervisorConfig,
        depth: int,
        visited: set[str],
    ):
        if self._agent_repository is None:
            raise ValueError("agent_repository is required for sub_agent compilation")

        ref_id = worker_def.ref_agent_id
        CircularReferencePolicy.validate_no_cycle(ref_id, visited)

        sub_agent = await self._agent_repository.find_by_id(ref_id, request_id)
        if sub_agent is None or sub_agent.status == "deleted":
            raise ValueError(f"서브 에이전트를 찾을 수 없습니다: {ref_id}")

        sub_llm_model = llm_model
        if self._llm_model_repository and sub_agent.llm_model_id != llm_model.id:
            resolved = await self._llm_model_repository.find_by_id(
                sub_agent.llm_model_id, request_id
            )
            if resolved:
                sub_llm_model = resolved

        new_visited = visited | {ref_id}
        sub_workflow = sub_agent.to_workflow_definition()
        sub_graph = await self.compile(
            workflow=sub_workflow,
            llm_model=sub_llm_model,
            request_id=request_id,
            temperature=sub_agent.temperature,
            supervisor_config=supervisor_config,
            depth=depth,
            visited=new_visited,
        )

        return self._wrap_sub_agent(worker_def.worker_id, sub_graph)

    def _resolve_category(self, worker_def: WorkerDefinition) -> str:
        """카테고리 결정: DB 오버라이드 → TOOL_REGISTRY → 기본값 "action"."""
        if worker_def.category is not None:
            return worker_def.category
        try:
            meta = get_tool_meta(worker_def.tool_id)
            return meta.category
        except ValueError:
            return "action"

    def _create_answer_node(self, llm, system_prompt: str):
        """수집된 검색 결과를 종합하여 최종 답변을 생성하는 노드."""
        logger = self._logger

        async def answer_node(state: SupervisorState) -> dict:
            search_results = []
            for msg in state["messages"]:
                content = msg.content if hasattr(msg, "content") else ""
                if hasattr(msg, "name") and msg.name and "검색결과" in content:
                    search_results.append(content)

            if not search_results:
                logger.warning("answer_node: no search results found")
                context = "(검색 결과 없음)"
            else:
                context = "\n\n---\n\n".join(search_results)

            user_query = ""
            for msg in state["messages"]:
                role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "type", "")
                if role in ("user", "human"):
                    content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
                    user_query = content
                    break

            answer_prompt = (
                f"{system_prompt}\n\n"
                f"아래 검색 결과를 바탕으로 사용자의 질문에 정확하게 답변하세요.\n"
                f"검색 결과에 없는 내용은 추측하지 마세요.\n\n"
                f"[수집된 검색 결과]\n{context}"
            )

            messages = [
                {"role": "system", "content": answer_prompt},
                {"role": "user", "content": user_query},
            ]

            logger.info("answer_node executing", search_result_count=len(search_results))

            response = await llm.ainvoke(messages)

            token_delta = len(response.content) // 4 if hasattr(response, "content") else 0

            return {
                "messages": [response],
                "last_worker_id": "answer_agent",
                "token_usage": state["token_usage"] + token_delta,
            }

        return answer_node

    def _create_search_node(self, worker_id: str, tool):
        """검색 도구를 LLM 없이 직접 실행하는 노드."""
        logger = self._logger

        async def search_node(state: SupervisorState) -> dict:
            last_msg = state["messages"][-1]
            query = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

            logger.info("search_node executing", worker_id=worker_id, query_length=len(query))

            try:
                result = await tool.ainvoke({"query": query})
            except Exception as e:
                logger.error("search_node tool failed", worker_id=worker_id, exception=e)
                result = f"검색 실패: {e}"

            result_str = result if isinstance(result, str) else str(result)

            from langchain_core.messages import AIMessage
            result_msg = AIMessage(
                content=f"[{worker_id} 검색결과]\n{result_str}",
                name=worker_id,
            )

            token_delta = len(result_str) // 4

            return {
                "messages": [result_msg],
                "last_worker_id": worker_id,
                "token_usage": state["token_usage"] + token_delta,
            }

        return search_node

    def _wrap_worker(self, worker_id: str, worker_agent):
        async def wrapped(state: SupervisorState) -> dict:
            result = await worker_agent.ainvoke(
                {"messages": state["messages"]}
            )
            new_messages = result.get("messages", [])

            token_delta = sum(
                len(getattr(m, "content", "")) // 4
                for m in new_messages
                if hasattr(m, "content")
            )

            return {
                "messages": new_messages,
                "last_worker_id": worker_id,
                "token_usage": state["token_usage"] + token_delta,
            }

        return wrapped

    def _wrap_sub_agent(self, worker_id: str, sub_graph):
        async def wrapped(state: SupervisorState) -> dict:
            last_msg = state["messages"][-1]
            task_content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

            sub_initial = build_initial_state(
                messages=[{"role": "user", "content": task_content}],
                config=SupervisorConfig(
                    token_limit=state["token_limit"] // 2,
                ),
                available_workers=[],
            )

            result = await sub_graph.ainvoke(sub_initial)
            sub_messages = result.get("messages", [])

            answer_content = ""
            if sub_messages:
                last = sub_messages[-1]
                answer_content = last.content if hasattr(last, "content") else str(last)

            from langchain_core.messages import AIMessage
            answer_msg = AIMessage(content=answer_content, name=worker_id)
            sub_token_usage = result.get("token_usage", 0)

            return {
                "messages": [answer_msg],
                "last_worker_id": worker_id,
                "token_usage": state["token_usage"] + sub_token_usage,
            }

        return wrapped
