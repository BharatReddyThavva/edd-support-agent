"""LangGraph support agent: handbook search plus order, refund, and escalation tools."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Annotated, Any, TypedDict

import opik
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from .config import Settings, get_settings, require_env
from .indexing import vector_store
from .orders import load_orders, lookup_order, refund_decision
from .policy import RULES, as_of_long

BASELINE_PROMPT = f"""You are the customer support agent for Alder & Co., a fictional home-goods shop.

Today for every policy window is {as_of_long()}. Do not use any other date.

Tools:
- search_handbook before you state a policy.
- get_order when the customer gives an order id and an email. If it is not found, say the order cannot be found. Do not reveal items, totals, or status.
- check_refund_eligibility before you grant or deny a return, damage claim, cancellation, warranty review, or price adjustment. Pass reason as one of: return, damaged, cancel, warranty, price_adjustment.
- escalate_to_human when the eligibility tool says should_escalate is true, and also when the customer mentions a chargeback, a lawyer, or a consumer forum. Do not escalate a denial.

Rules:
- Quote the handbook_rule and rules returned by tools. Do not invent fees, windows, or amounts.
- You never move money and you never change an order. An eligible outcome still needs escalate_to_human so a specialist executes it.
- Never ask for a card number, UPI PIN, OTP, or password.
- If the handbook and the tools do not contain the answer, say "I do not know" and do not guess.
- Be concise, specific, and professional.
"""

STRICT_PROMPT = BASELINE_PROMPT + "\nAnswer in at most 4 sentences.\n"

SYSTEM_PROMPTS = {
    "baseline": BASELINE_PROMPT,
    "strict": STRICT_PROMPT,
}


class AgentState(TypedDict, total=False):
    messages: Annotated[list[Any], add_messages]
    context: list[str]
    tools_called: list[str]


def _ticket_id(order_id: str, reason: str) -> str:
    digest = hashlib.sha256(f"{order_id}|{reason}".encode()).hexdigest()[:6].upper()
    return f"ESC-{digest}"


def _dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


class SupportAgent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.orders = load_orders(settings.orders_path)
        if settings.gemini_api_key and not os.environ.get("GOOGLE_API_KEY"):
            os.environ["GOOGLE_API_KEY"] = settings.gemini_api_key
        self.graph = self._compile()

    @opik.track(name="search-handbook", type="tool")
    def search_handbook(self, query: str) -> str:
        store = vector_store(self.settings)
        documents = store.similarity_search(query, k=self.settings.retrieval_k)
        passages = [
            {
                "section": document.metadata.get("section"),
                "text": document.page_content,
            }
            for document in documents
        ]
        return _dumps({"passages": passages})

    @opik.track(name="get-order", type="tool")
    def get_order(self, order_id: str, email: str) -> str:
        return _dumps(lookup_order(self.orders, order_id, email))

    @opik.track(name="check-refund-eligibility", type="tool")
    def check_refund_eligibility(self, order_id: str, email: str, reason: str) -> str:
        return _dumps(refund_decision(self.orders, order_id, email, reason))

    @opik.track(name="escalate-to-human", type="tool")
    def escalate_to_human(self, order_id: str, reason: str, summary: str) -> str:
        return _dumps(
            {
                "ticket_id": _ticket_id(order_id or "none", reason),
                "queue": "specialist",
                "summary": summary,
                "handbook_rule": RULES["ESCALATION_TICKET"],
            }
        )

    def _llm(self, *, with_tools: bool) -> Any:
        llm = ChatGoogleGenerativeAI(model=self.settings.chat_model, temperature=0)
        if not with_tools:
            return llm
        return llm.bind_tools(
            [
                StructuredTool.from_function(
                    func=self.search_handbook,
                    name="search_handbook",
                    description="Search the Alder & Co. support handbook. Use before stating a policy.",
                ),
                StructuredTool.from_function(
                    func=self.get_order,
                    name="get_order",
                    description="Look up an order. Requires the order id and the email on the order.",
                ),
                StructuredTool.from_function(
                    func=self.check_refund_eligibility,
                    name="check_refund_eligibility",
                    description=(
                        "Check a return, damaged arrival, cancellation, warranty claim, or price adjustment. "
                        "reason must be return, damaged, cancel, warranty, or price_adjustment."
                    ),
                ),
                StructuredTool.from_function(
                    func=self.escalate_to_human,
                    name="escalate_to_human",
                    description=(
                        "Open a specialist ticket. Use when a check is eligible, or for a chargeback, "
                        "lawyer, or consumer forum."
                    ),
                ),
            ]
        )

    def _call_tool(self, name: str, args: dict[str, Any]) -> str:
        try:
            if name == "search_handbook":
                return self.search_handbook(query=str(args.get("query", "")))
            if name == "get_order":
                return self.get_order(
                    order_id=str(args.get("order_id", "")),
                    email=str(args.get("email", "")),
                )
            if name == "check_refund_eligibility":
                return self.check_refund_eligibility(
                    order_id=str(args.get("order_id", "")),
                    email=str(args.get("email", "")),
                    reason=str(args.get("reason", "")),
                )
            if name == "escalate_to_human":
                return self.escalate_to_human(
                    order_id=str(args.get("order_id", "")),
                    reason=str(args.get("reason", "")),
                    summary=str(args.get("summary", "")),
                )
            return _dumps({"error": f"Unknown tool {name}"})
        except Exception as error:  # tool failures should return to the model, not crash the turn
            return _dumps({"error": f"{type(error).__name__}: {error}"})

    def _compile(self):
        prompt = SYSTEM_PROMPTS[self.settings.prompt_style]
        llm_with_tools = self._llm(with_tools=True)
        llm_final = self._llm(with_tools=False)

        def agent_node(state: AgentState) -> dict[str, Any]:
            rounds = sum(
                1
                for message in state["messages"]
                if isinstance(message, AIMessage) and message.tool_calls
            )
            if rounds >= self.settings.max_tool_rounds:
                response = llm_final.invoke(
                    [
                        SystemMessage(content=prompt),
                        SystemMessage(content="Do not call any more tools. Answer from the tool results you already have."),
                        *state["messages"],
                    ]
                )
            else:
                response = llm_with_tools.invoke([SystemMessage(content=prompt), *state["messages"]])
            return {"messages": [response]}

        def tools_node(state: AgentState) -> dict[str, Any]:
            last = state["messages"][-1]
            context = list(state.get("context", []))
            called = list(state.get("tools_called", []))
            messages: list[ToolMessage] = []
            for call in last.tool_calls:
                name = call["name"]
                called.append(name)
                payload = self._call_tool(name, call.get("args") or {})
                if name == "search_handbook":
                    try:
                        parsed = json.loads(payload)
                    except json.JSONDecodeError:
                        parsed = {}
                    context.extend(
                        passage["text"]
                        for passage in parsed.get("passages", [])
                        if isinstance(passage, dict) and passage.get("text")
                    )
                    if not parsed.get("passages"):
                        context.append(payload)
                else:
                    context.append(f"{name}: {payload}")
                messages.append(ToolMessage(content=payload, tool_call_id=call["id"]))
            return {"messages": messages, "context": context, "tools_called": called}

        def route(state: AgentState) -> str:
            last = state["messages"][-1]
            if isinstance(last, AIMessage) and last.tool_calls:
                return "tools"
            return END

        graph = StateGraph(AgentState)
        graph.add_node("agent", agent_node)
        graph.add_node("tools", tools_node)
        graph.add_edge(START, "agent")
        graph.add_conditional_edges("agent", route, {"tools": "tools", END: END})
        graph.add_edge("tools", "agent")
        return graph.compile()

    def answer(self, question: str) -> dict[str, Any]:
        state = self.graph.invoke(
            {"messages": [HumanMessage(content=question)], "context": [], "tools_called": []}
        )
        answer = ""
        for message in reversed(state["messages"]):
            if isinstance(message, AIMessage) and message.content and not message.tool_calls:
                content = message.content
                answer = content if isinstance(content, str) else json.dumps(content)
                break
        context = list(state.get("context") or [])
        if not context:
            context = ["No handbook passages or tool results were returned."]
        return {
            "answer": answer,
            "context": context,
            "tools_called": list(state.get("tools_called") or []),
        }


@opik.track(name="support-agent", type="agent")
def answer_question(question: str, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    require_env(settings, "gemini_api_key", "qdrant_url")
    if settings.prompt_style not in SYSTEM_PROMPTS:
        raise SystemExit(f"Unknown prompt_style {settings.prompt_style!r}. Use baseline or strict.")
    return SupportAgent(settings).answer(question)
