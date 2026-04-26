"""WorkflowCompiler: WorkflowDefinition → LangGraph CompiledGraph 동적 컴파일."""
import os

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph_supervisor import create_supervisor

from src.domain.agent_builder.schemas import WorkflowDefinition
from src.domain.llm_model.entity import LlmModel
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.agent_builder.tool_factory import ToolFactory


class WorkflowCompiler:
    """WorkflowDefinition → LangGraph CompiledGraph 동적 컴파일."""

    def __init__(self, tool_factory: ToolFactory, logger: LoggerInterface) -> None:
        self._tool_factory = tool_factory
        self._logger = logger

    def compile(
        self,
        workflow: WorkflowDefinition,
        llm_model: LlmModel,
        request_id: str,
        temperature: float = 0.0,
    ):
        """동적 컴파일: WorkerDefinition 목록 → Supervisor + Worker 그래프."""
        self._logger.info(
            "WorkflowCompiler compile start",
            request_id=request_id,
            worker_count=len(workflow.workers),
            provider=llm_model.provider,
            model_name=llm_model.model_name,
        )
        try:
            llm = self._build_llm(llm_model, temperature)

            worker_agents = []
            for worker_def in workflow.workers:
                tool = self._tool_factory.create(
                    worker_def.tool_id, request_id, tool_config=worker_def.tool_config
                )
                worker_agent = create_react_agent(
                    llm,
                    tools=[tool],
                    name=worker_def.worker_id,
                )
                worker_agents.append(worker_agent)

            supervisor = create_supervisor(
                llm,
                agents=worker_agents,
                system_prompt=workflow.supervisor_prompt,
            )
            graph = supervisor.compile()

            self._logger.info("WorkflowCompiler compile done", request_id=request_id)
            return graph
        except Exception as e:
            self._logger.error(
                "WorkflowCompiler compile failed", exception=e, request_id=request_id
            )
            raise

    def _build_llm(self, llm_model: LlmModel, temperature: float = 0.0) -> BaseChatModel:
        """provider 분기로 LLM 인스턴스 생성."""
        provider = llm_model.provider
        if provider == "openai":
            api_key = os.environ.get(llm_model.api_key_env)
            return ChatOpenAI(
                model=llm_model.model_name, api_key=api_key, temperature=temperature
            )
        if provider == "anthropic":
            api_key = os.environ.get(llm_model.api_key_env)
            return ChatAnthropic(
                model=llm_model.model_name, api_key=api_key, temperature=temperature
            )
        if provider == "ollama":
            return ChatOllama(model=llm_model.model_name, temperature=temperature)
        raise ValueError(f"지원하지 않는 provider: {provider}")
