from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, RetryPolicy, interrupt
from typing_extensions import TypedDict

from zubepredict_core.shared.schemas import TaskDecision


class WorkflowState(TypedDict, total=False):
    experiment_id: str
    owner_id: str
    job_id: str
    phase: str
    profile: dict[str, Any]
    configuration: dict[str, Any]
    task_override: dict[str, Any] | None
    decision: dict[str, Any]
    plan: dict[str, Any]
    clarification: dict[str, Any] | None
    result: dict[str, Any]
    completed: bool


class ExperimentWorkflowContext(Protocol):
    def check_cancelled(self) -> None: ...

    def progress(self, phase: str, value: int, message: str) -> None: ...

    def profile(self) -> dict[str, Any]: ...

    def decide(
        self,
        configuration: dict[str, Any],
        task_override: dict[str, Any] | None,
    ) -> TaskDecision: ...

    def validate_plan(
        self,
        decision: TaskDecision,
        configuration: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any] | None]: ...

    def train_and_persist(
        self,
        decision: TaskDecision,
        configuration: dict[str, Any],
    ) -> dict[str, Any]: ...

    def finalize(self, result: dict[str, Any]) -> dict[str, Any]: ...


class WorkflowTransientError(RuntimeError):
    """A safe-to-retry error before model training side effects begin."""


@dataclass(frozen=True)
class WorkflowExecution:
    state: WorkflowState
    interrupted: bool
    clarification: dict[str, Any] | None = None


def _validated_resume(state: WorkflowState, response: Any) -> WorkflowState:
    if not isinstance(response, dict):
        raise ValueError("Workflow clarification responses must be JSON objects.")
    configuration_update = response.get("configuration", {})
    if not isinstance(configuration_update, dict):
        raise ValueError("Clarification configuration must be a JSON object.")
    configuration = {**state.get("configuration", {}), **configuration_update}
    task_override: dict[str, Any] | None = state.get("task_override")
    if "task_type" in response or "target_column" in response:
        if response.get("confirmed_by_user") is not True:
            raise ValueError("A task clarification must be explicitly confirmed by the user.")
        task_override = {
            "task_type": response.get("task_type"),
            "target_column": response.get("target_column"),
            "confirmed_by_user": True,
        }
    return {
        "configuration": configuration,
        "task_override": task_override,
        "clarification": None,
        "phase": "clarification_received",
    }


def build_experiment_graph(
    context: ExperimentWorkflowContext,
    checkpointer: BaseCheckpointSaver[Any],
) -> Any:
    retry_policy = RetryPolicy(
        initial_interval=0.5,
        backoff_factor=2,
        max_interval=2,
        max_attempts=2,
        jitter=False,
        retry_on=WorkflowTransientError,
    )

    def profile_node(_state: WorkflowState) -> WorkflowState:
        context.check_cancelled()
        context.progress("profiling", 10, "Profiling the owned dataset")
        profile = context.profile()
        context.check_cancelled()
        return {"phase": "profiled", "profile": profile}

    def decision_node(state: WorkflowState) -> WorkflowState:
        context.check_cancelled()
        context.progress("profiling", 20, "Resolving the deterministic task decision")
        decision = context.decide(
            state.get("configuration", {}), state.get("task_override")
        )
        clarification = None
        if decision.requires_clarification:
            clarification = {
                "kind": "task_decision",
                "question": decision.clarification_question,
                "required_fields": ["task_type", "target_column", "confirmed_by_user"],
                "decision_evidence": decision.model_dump(mode="json"),
            }
        return {
            "phase": "decision_ready",
            "decision": decision.model_dump(mode="json"),
            "clarification": clarification,
        }

    def clarification_node(state: WorkflowState) -> WorkflowState:
        clarification = state.get("clarification")
        if clarification is None:
            raise ValueError("The workflow reached clarification without a question.")
        response = interrupt(clarification)
        return _validated_resume(state, response)

    def plan_node(state: WorkflowState) -> WorkflowState:
        context.check_cancelled()
        context.progress("profiling", 24, "Validating the experiment plan")
        decision = TaskDecision.model_validate(state["decision"])
        plan, clarification = context.validate_plan(
            decision, state.get("configuration", {})
        )
        return {
            "phase": "plan_ready" if clarification is None else "plan_needs_clarification",
            "plan": plan,
            "clarification": clarification,
        }

    def training_node(state: WorkflowState) -> WorkflowState:
        context.check_cancelled()
        context.progress("training", 25, "Starting the deterministic model workflow")
        result = context.train_and_persist(
            TaskDecision.model_validate(state["decision"]),
            state.get("configuration", {}),
        )
        context.check_cancelled()
        return {"phase": "result_persisted", "result": result}

    def finalize_node(state: WorkflowState) -> WorkflowState:
        context.check_cancelled()
        result = context.finalize(state["result"])
        return {"phase": "completed", "result": result, "completed": True}

    def after_decision(state: WorkflowState) -> str:
        return "clarify" if state.get("clarification") else "plan"

    def after_plan(state: WorkflowState) -> str:
        return "clarify" if state.get("clarification") else "train"

    builder = StateGraph(WorkflowState)
    builder.add_node(
        "profile",
        cast(Any, profile_node),
        retry_policy=retry_policy,
        metadata={"owner": "deterministic_python"},
    )
    builder.add_node(
        "decide",
        cast(Any, decision_node),
        retry_policy=retry_policy,
        metadata={"owner": "deterministic_python"},
    )
    builder.add_node(
        "clarify",
        cast(Any, clarification_node),
        metadata={"owner": "human_interrupt"},
    )
    builder.add_node(
        "plan",
        cast(Any, plan_node),
        retry_policy=retry_policy,
        metadata={"owner": "deterministic_python"},
    )
    builder.add_node(
        "train",
        cast(Any, training_node),
        metadata={"owner": "deterministic_python", "idempotent_boundary": True},
    )
    builder.add_node(
        "finalize",
        cast(Any, finalize_node),
        metadata={"owner": "deterministic_python", "idempotent_boundary": True},
    )
    builder.add_edge(START, "profile")
    builder.add_edge("profile", "decide")
    builder.add_conditional_edges(
        "decide", after_decision, {"clarify": "clarify", "plan": "plan"}
    )
    builder.add_edge("clarify", "decide")
    builder.add_conditional_edges(
        "plan", after_plan, {"clarify": "clarify", "train": "train"}
    )
    builder.add_edge("train", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer)


def run_experiment_graph(
    graph: Any,
    initial_state: WorkflowState,
    *,
    thread_id: str,
    resume_payload: dict[str, Any] | None = None,
) -> WorkflowExecution:
    config: RunnableConfig = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 20,
    }
    existing = cast(WorkflowState, graph.get_state(config).values)
    if existing.get("completed"):
        return WorkflowExecution(state=existing, interrupted=False)
    invocation: WorkflowState | Command
    invocation = (
        Command(resume=resume_payload) if resume_payload is not None else initial_state
    )
    result = cast(dict[str, Any], graph.invoke(invocation, config=config))
    interrupts = result.get("__interrupt__", ())
    if interrupts:
        clarification = cast(dict[str, Any], interrupts[0].value)
        state = cast(
            WorkflowState,
            {key: value for key, value in result.items() if key != "__interrupt__"},
        )
        return WorkflowExecution(state=state, interrupted=True, clarification=clarification)
    return WorkflowExecution(state=cast(WorkflowState, result), interrupted=False)
