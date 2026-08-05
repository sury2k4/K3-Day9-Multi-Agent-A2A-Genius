"""Delivery timeline specialist."""

from src.agents.base import BaseAgent, Narrative, StructuredLLM
from src.database.repository import OlistRepository
from src.observability.trace_logger import TraceLogger
from src.schemas.agent_messages import AgentTask
from src.schemas.agent_reports import DeliveryReport
from src.tools.delivery_tools import DeliveryTools


class DeliveryAgent(BaseAgent):
    name = "delivery_agent"
    prompt_file = "delivery_agent.md"

    def __init__(self, llm: StructuredLLM, repository: OlistRepository, trace: TraceLogger) -> None:
        super().__init__(llm)
        self._repository = repository
        self._trace = trace

    async def run(self, task: AgentTask) -> DeliveryReport:
        if set(task.allowed_tools) != DeliveryTools.allowed_tools:
            raise ValueError("Delivery agent task has an invalid tool allowlist")
        await self._trace.emit(
            "agent_started", case_id=task.case_id, agent=self.name, task_id=task.task_id
        )
        tools = DeliveryTools(self._repository, self._trace, task.case_id, self.name)
        timeline = await tools.get_order_delivery_timeline(task.order_id)
        items = await tools.get_order_items(task.order_id)
        reviews = await tools.get_order_reviews(task.order_id)
        delivered_late = bool(
            timeline.order_delivered_customer_date
            and timeline.order_delivered_customer_date > timeline.order_estimated_delivery_date
        )
        late_items = [
            item
            for item in items
            if timeline.order_delivered_carrier_date
            and timeline.order_delivered_carrier_date > item.shipping_limit_date
        ]
        response = await self._llm.structured(
            system_prompt=self._prompt,
            user_payload={
                "objective": task.objective,
                "timeline": timeline.model_dump(mode="json"),
                "shipping_limits": [
                    {
                        "item_id": item.order_item_id,
                        "seller_id": item.seller_id,
                        "shipping_limit_date": item.shipping_limit_date,
                    }
                    for item in items
                ],
                "review_count": len(reviews),
            },
            response_model=Narrative,
        )
        late_item_ids = [f"{item.order_id}:{item.order_item_id}" for item in late_items]
        evidence = [f"order:{task.order_id}"] + [f"item:{item_id}" for item_id in late_item_ids]
        report = DeliveryReport(
            task_id=task.task_id,
            timeline=timeline,
            delivered_after_estimate=delivered_late,
            carrier_handoff_after_limit=bool(late_items),
            late_item_ids=late_item_ids,
            late_seller_ids=sorted({item.seller_id for item in late_items}),
            missing_data=["review"] if not reviews else [],
            evidence_candidates=evidence,
            summary=response.value.summary,
            warnings=response.value.warnings,
        )
        await self._trace.emit(
            "agent_completed",
            case_id=task.case_id,
            agent=self.name,
            task_id=task.task_id,
            evidence_ids=evidence,
            model_id="qwen/qwen-2.5-7b-instruct",
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
        )
        return report
