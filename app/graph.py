from __future__ import annotations

import json
from typing import Any, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from .agents import (
    build_delivery_report,
    build_order_report,
    build_payment_report,
)
from .config import Settings
from .db import RunStore
from .llm import build_llm
from .policy import build_policy_decision, deterministic_explanation
from .schemas import (
    CaseInput,
    CaseOutput,
    DeliveryReport,
    OrderReport,
    PaymentReport,
    PolicyDecision,
    PolicyExplanation,
)
from .tracing import NodeTimer, TraceRecorder, langfuse_callbacks
from .verifier import verify_case_output


class CaseState(TypedDict, total=False):
    case: dict[str, Any]
    case_id: str
    opened_at: str
    policy_version: str
    order_id: str
    assigned_agents: list[str]
    order_report: dict[str, Any]
    payment_report: dict[str, Any]
    delivery_report: dict[str, Any]
    fact_bundle: dict[str, Any]
    policy_decision: dict[str, Any]
    policy_explanation: dict[str, Any]
    candidate_output: dict[str, Any]
    verification_report: dict[str, Any]
    repair_attempt: int
    fallback_used: bool
    output_path: str
    trace_id: str
    run_id: str
    errors: list[str]


class DisputeGraph:
    def __init__(
        self,
        repository: Any,
        settings: Settings,
        tracer: TraceRecorder,
        run_store: RunStore | None = None,
    ):
        self.repository = repository
        self.settings = settings
        self.tracer = tracer
        self.run_store = run_store
        self.llm = build_llm(settings)
        self.compiled = self._build_graph()

    def _trace_node(self, name: str, state: CaseState, function: Any) -> dict[str, Any]:
        trace_id = state.get("trace_id", "unknown")
        case_id = state.get("case_id", "unknown")
        self.tracer.event(
            trace_id=trace_id,
            case_id=case_id,
            node=name,
            event="start",
            framework="LangGraph",
            model=self.settings.openrouter_model,
        )
        timer = NodeTimer()
        try:
            result = function(state)
        except Exception as exc:
            self.tracer.event(
                trace_id=trace_id,
                case_id=case_id,
                node=name,
                event="error",
                elapsed_ms=timer.elapsed_ms,
                error_type=type(exc).__name__,
                error=str(exc)[:500],
                framework="LangGraph",
                model=self.settings.openrouter_model,
            )
            raise
        self.tracer.event(
            trace_id=trace_id,
            case_id=case_id,
            node=name,
            event="end",
            elapsed_ms=timer.elapsed_ms,
            framework="LangGraph",
            model=self.settings.openrouter_model,
        )
        if self.run_store is not None and state.get("run_id"):
            self.run_store.record_handoff(
                state["run_id"],
                name,
                {"case_id": case_id, "order_id": state.get("order_id")},
                {
                    "updated_state_keys": sorted(result),
                    "handoff": result,
                },
            )
        return result

    def _intake(self, state: CaseState) -> dict[str, Any]:
        def work(current: CaseState) -> dict[str, Any]:
            case = CaseInput.model_validate(current["case"])
            if case.policy_version != "EC_POLICY_V1":
                raise ValueError(f"Unsupported policy version: {case.policy_version}")
            return {
                "case": case.model_dump(mode="json"),
                "case_id": case.case_id,
                "opened_at": case.opened_at,
                "policy_version": case.policy_version,
                "order_id": case.customer_request.claimed_order_id,
                "repair_attempt": 0,
                "fallback_used": False,
                "errors": [],
            }

        return self._trace_node("case_intake", state, work)

    def _coordinator(self, state: CaseState) -> dict[str, Any]:
        return self._trace_node(
            "coordinator",
            state,
            lambda _: {
                "assigned_agents": [
                    "order_seller_agent",
                    "payment_agent",
                    "delivery_agent",
                ]
            },
        )

    def _order_agent(self, state: CaseState) -> dict[str, Any]:
        def work(current: CaseState) -> dict[str, Any]:
            report = build_order_report(self.repository, current["order_id"])
            return {"order_report": report.model_dump(mode="json")}

        return self._trace_node("order_seller_agent", state, work)

    def _payment_agent(self, state: CaseState) -> dict[str, Any]:
        def work(current: CaseState) -> dict[str, Any]:
            # This branch is independent: it reads the source item rows itself
            # instead of depending on the parallel Order/Seller branch.
            order_report = build_order_report(self.repository, current["order_id"])
            report = build_payment_report(
                self.repository,
                current["order_id"],
                order_report,
            )
            return {"payment_report": report.model_dump(mode="json")}

        return self._trace_node("payment_agent", state, work)

    def _delivery_agent(self, state: CaseState) -> dict[str, Any]:
        def work(current: CaseState) -> dict[str, Any]:
            # This branch is independent for the same reason as Payment Agent.
            order_report = build_order_report(self.repository, current["order_id"])
            report = build_delivery_report(
                self.repository,
                current["order_id"],
                order_report,
            )
            return {"delivery_report": report.model_dump(mode="json")}

        return self._trace_node("delivery_agent", state, work)

    def _evidence_join(self, state: CaseState) -> dict[str, Any]:
        def work(current: CaseState) -> dict[str, Any]:
            order_report = OrderReport.model_validate(current["order_report"])
            payment_report = PaymentReport.model_validate(current["payment_report"])
            delivery_report = DeliveryReport.model_validate(current["delivery_report"])
            bundle = {
                "order_evidence_count": len(order_report.evidence_ids),
                "payment_evidence_count": len(payment_report.evidence_ids),
                "delivery_evidence_count": len(delivery_report.evidence_ids),
                "order_id": current["order_id"],
                "order_status": order_report.order_status,
                "item_total_brl": order_report.item_total_brl,
                "freight_total_brl": order_report.freight_total_brl,
                "payment_total_brl": payment_report.payment_total_brl,
                "payment_row_count": payment_report.payment_row_count,
                "payment_matches_item_plus_freight": payment_report.matches_item_plus_freight,
                "delivery_outcome": delivery_report.delivery_outcome,
                "late_seller_ids": delivery_report.late_seller_ids,
            }
            return {"fact_bundle": bundle}

        return self._trace_node("evidence_join", state, work)

    def _policy_engine(self, state: CaseState) -> dict[str, Any]:
        def work(current: CaseState) -> dict[str, Any]:
            decision = build_policy_decision(
                current["case_id"],
                OrderReport.model_validate(current["order_report"]),
                PaymentReport.model_validate(current["payment_report"]),
                DeliveryReport.model_validate(current["delivery_report"]),
            )
            return {"policy_decision": decision.model_dump(mode="json")}

        return self._trace_node("policy_engine", state, work)

    def _policy_agent(self, state: CaseState) -> dict[str, Any]:
        def work(current: CaseState) -> dict[str, Any]:
            decision = PolicyDecision.model_validate(current["policy_decision"])
            explanation = deterministic_explanation(decision)
            model_used = False
            if self.llm is not None:
                try:
                    structured_llm = self.llm.with_structured_output(PolicyExplanation)
                    response = structured_llm.invoke(
                        [
                            {
                                "role": "system",
                                "content": (
                                    "Summarize the already-determined e-commerce dispute decision. "
                                    "Do not change the issue, refund, evidence, or responsible party."
                                ),
                            },
                            {"role": "user", "content": json.dumps(
                                decision.candidate_output.model_dump(mode="json"),
                                ensure_ascii=False,
                            )},
                        ]
                    )
                    explanation = PolicyExplanation.model_validate(response).summary
                    model_used = True
                except Exception as exc:  # noqa: BLE001 - model failure must fall back safely
                    self.tracer.event(
                        trace_id=current["trace_id"],
                        case_id=current["case_id"],
                        node="policy_agent",
                        event="model_fallback",
                        error_type=type(exc).__name__,
                    )
            return {
                "candidate_output": decision.candidate_output.model_dump(mode="json"),
                "policy_explanation": {"summary": explanation},
                "errors": current.get("errors", []) + ([] if model_used else ["policy_model_not_used"]),
            }

        return self._trace_node("policy_agent", state, work)

    def _verifier(self, state: CaseState) -> dict[str, Any]:
        def work(current: CaseState) -> dict[str, Any]:
            decision = PolicyDecision.model_validate(current["policy_decision"])
            report = verify_case_output(
                current["candidate_output"],
                decision.candidate_output.model_dump(mode="json"),
                current["case_id"],
                current["order_id"],
                self.repository,
            )
            return {"verification_report": report.model_dump(mode="json")}

        return self._trace_node("verifier_agent", state, work)

    def _repair(self, state: CaseState) -> dict[str, Any]:
        def work(current: CaseState) -> dict[str, Any]:
            # Repair is deliberately non-authoritative: it restores the exact
            # deterministic candidate and only normalizes JSON serialization.
            decision = PolicyDecision.model_validate(current["policy_decision"])
            return {
                "candidate_output": decision.candidate_output.model_dump(mode="json"),
                "repair_attempt": current.get("repair_attempt", 0) + 1,
            }

        return self._trace_node("repair_format", state, work)

    def _fallback(self, state: CaseState) -> dict[str, Any]:
        def work(current: CaseState) -> dict[str, Any]:
            decision = PolicyDecision.model_validate(current["policy_decision"])
            candidate = decision.candidate_output.model_copy(deep=True)
            candidate.evidence_ids = [
                evidence_id
                for evidence_id in candidate.evidence_ids
                if self.repository.evidence_exists(evidence_id)
            ]
            return {
                "candidate_output": candidate.model_dump(mode="json"),
                "fallback_used": True,
                "verification_report": {
                    "valid": True,
                    "errors": ["deterministic fallback used"],
                    "checked_evidence_count": len(candidate.evidence_ids),
                },
            }

        return self._trace_node("deterministic_fallback", state, work)

    def _writer(self, state: CaseState) -> dict[str, Any]:
        def work(current: CaseState) -> dict[str, Any]:
            candidate = CaseOutput.model_validate(current["candidate_output"])
            decision = PolicyDecision.model_validate(current["policy_decision"])
            final_report = verify_case_output(
                candidate.model_dump(mode="json"),
                decision.candidate_output.model_dump(mode="json"),
                current["case_id"],
                current["order_id"],
                self.repository,
            )
            if not final_report.valid:
                raise RuntimeError(
                    "Refusing to write invalid output: " + "; ".join(final_report.errors)
                )
            self.settings.output_dir.mkdir(parents=True, exist_ok=True)
            output_path = self.settings.output_dir / f"{current['case_id']}.json"
            output_path.write_text(
                json.dumps(candidate.model_dump(mode="json"), ensure_ascii=False, indent=2)
                + "\n",
                encoding="utf-8",
            )
            return {
                "output_path": str(output_path),
                "verification_report": final_report.model_dump(mode="json"),
            }

        return self._trace_node("output_writer", state, work)

    @staticmethod
    def _route_after_verifier(state: CaseState) -> str:
        report = state.get("verification_report", {})
        if report.get("valid"):
            return "writer"
        if state.get("repair_attempt", 0) < 1:
            return "repair"
        return "fallback"

    def _build_graph(self) -> Any:
        builder = StateGraph(CaseState)
        builder.add_node("intake", self._intake)
        builder.add_node("coordinator", self._coordinator)
        builder.add_node("order_agent", self._order_agent)
        builder.add_node("payment_agent", self._payment_agent)
        builder.add_node("delivery_agent", self._delivery_agent)
        builder.add_node("evidence_join", self._evidence_join)
        builder.add_node("policy_engine", self._policy_engine)
        builder.add_node("policy_agent", self._policy_agent)
        builder.add_node("verifier", self._verifier)
        builder.add_node("repair", self._repair)
        builder.add_node("fallback", self._fallback)
        builder.add_node("writer", self._writer)

        builder.add_edge(START, "intake")
        builder.add_edge("intake", "coordinator")
        builder.add_edge("coordinator", "order_agent")
        builder.add_edge("coordinator", "payment_agent")
        builder.add_edge("coordinator", "delivery_agent")
        builder.add_edge("order_agent", "evidence_join")
        builder.add_edge("payment_agent", "evidence_join")
        builder.add_edge("delivery_agent", "evidence_join")
        builder.add_edge("evidence_join", "policy_engine")
        builder.add_edge("policy_engine", "policy_agent")
        builder.add_edge("policy_agent", "verifier")
        builder.add_conditional_edges(
            "verifier",
            self._route_after_verifier,
            {"writer": "writer", "repair": "repair", "fallback": "fallback"},
        )
        builder.add_edge("repair", "verifier")
        builder.add_edge("fallback", "writer")
        builder.add_edge("writer", END)
        return builder.compile()

    def run_case(self, case: CaseInput) -> dict[str, Any]:
        trace_id = str(uuid4())
        run_id = str(uuid4())
        initial_state: CaseState = {
            "case": case.model_dump(mode="json"),
            "case_id": case.case_id,
            "trace_id": trace_id,
            "run_id": run_id,
        }
        if self.run_store is not None:
            self.run_store.start_case(run_id, initial_state["case"], trace_id)
        callbacks = langfuse_callbacks(self.settings)
        config: dict[str, Any] = {
            "run_name": f"case:{case.case_id}",
            "metadata": {
                "case_id": case.case_id,
                "order_id": case.customer_request.claimed_order_id,
                "policy_version": case.policy_version,
                "model": self.settings.openrouter_model,
            },
        }
        if callbacks:
            config["callbacks"] = callbacks
        try:
            result = self.compiled.invoke(initial_state, config=config)
        except Exception as exc:
            if self.run_store is not None:
                self.run_store.finish_case(
                    run_id,
                    case.case_id,
                    "failed",
                    error_message=str(exc)[:1000],
                )
            raise
        if self.run_store is not None:
            self.run_store.finish_case(
                run_id,
                case.case_id,
                "completed",
                output_payload=result.get("candidate_output"),
                verification_payload=result.get("verification_report"),
            )
        return result
