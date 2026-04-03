"""WorkflowCompiler: WorkflowDefinition → LangGraph CompiledGraph 동적 컴파일."""
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph_supervisor import create_supervisor

from src.domain.agent_builder.schemas import WorkflowDefinition
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
        model_name: str,
        api_key: str,
        request_id: str,
    ):
        """동적 컴파일: WorkerDefinition 목록 → Supervisor + Worker 그래프."""
        self._logger.info(
            "WorkflowCompiler compile start",
            request_id=request_id,
            worker_count=len(workflow.workers),
        )
        try:
            llm = ChatOpenAI(model=model_name, api_key=api_key, temperature=0)

            worker_agents = []
            for worker_def in workflow.workers:
                tool = self._tool_factory.create(worker_def.tool_id, request_id)
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
