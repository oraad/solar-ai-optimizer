"""Local LLM assistant (Ollama) for natural-language explanations + control.

Safety design: the LLM NEVER directly issues inverter writes. Control intents
are extracted by a deterministic keyword parser and returned as a structured
`Override`; the caller decides whether to apply it. The LLM only generates the
prose explanation. If Ollama is disabled/unreachable, a heuristic explanation is
produced from the current decision context so the feature degrades gracefully.
"""

from __future__ import annotations

import logging
import re

import httpx

from ..config import Settings
from ..engine.priorities import system_prompt_priorities
from ..models import Override

log = logging.getLogger("llm.assistant")

SYSTEM_PROMPT_BASE = (
    "You are the assistant for a home solar/battery optimizer running on Home "
    "Assistant. "
)


class Assistant:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def enabled(self) -> bool:
        return self._settings.llm_enabled

    # --------------------------------------------------------- intent parser --
    def parse_intent(self, question: str) -> Override | None:
        """Deterministically map common control phrases to an Override."""
        q = question.lower().strip()
        ov = Override()
        matched = False

        if re.search(r"\b(kill switch|emergency|grid charge at max|charge at max)\b", q):
            return Override(kill_switch=True)
        if re.search(r"\b(force|start).*(grid )?charg", q):
            ov.force_grid_charge = True
            matched = True
        if re.search(r"\b(stop|cancel|release).*(grid )?charg", q):
            ov.force_grid_charge = False
            matched = True
        if re.search(r"\bpause\b", q):
            ov.pause_engine = True
            matched = True
        if re.search(r"\b(resume|unpause|continue)\b", q):
            ov.pause_engine = False
            matched = True
        if re.search(r"\b(live|enable control|go live)\b", q):
            ov.shadow_mode = False
            matched = True
        if re.search(r"\b(shadow|observe only|dry run)\b", q):
            ov.shadow_mode = True
            matched = True
        m = re.search(r"reserve\D{0,12}(\d{1,3})\s*%?", q)
        if m:
            ov.reserve_soc = max(0.0, min(100.0, float(m.group(1))))
            matched = True

        return ov if matched else None

    @staticmethod
    def kill_switch_confirmed(question: str) -> bool:
        """Kill switch writes require an explicit confirmation token in the question."""
        return bool(
            re.search(r"\b(confirm|yes|proceed|engage)\b", question.lower().strip())
        )

    # ------------------------------------------------------------- generate --
    async def answer(self, question: str, context: dict) -> str:
        if self.enabled:
            try:
                return await self._ollama(question, context)
            except Exception as e:  # noqa: BLE001
                log.warning("Ollama failed (%s); using heuristic answer.", e)
        return self._heuristic(question, context)

    async def _ollama(self, question: str, context: dict) -> str:
        from ..config import OptimizationPriority

        order_raw = context.get("priority_order")
        order = None
        if isinstance(order_raw, list):
            try:
                order = [OptimizationPriority(str(x)) for x in order_raw]
            except ValueError:
                order = None
        system = (
            f"{SYSTEM_PROMPT_BASE}{system_prompt_priorities(order)} "
            "Answer concisely and concretely using the provided live context. "
            "If asked to explain a decision, reference the reserve target, SOC, "
            "solar forecast, and grid state."
        )
        prompt = (
            f"{system}\n\nLive context (JSON):\n{context}\n\n"
            f"User: {question}\nAssistant:"
        )
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self._settings.ollama_base_url}/api/generate",
                json={
                    "model": self._settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return str(data.get("response", "")).strip() or self._heuristic(
                question, context
            )

    @staticmethod
    def _heuristic(question: str, context: dict) -> str:
        d = context.get("decision") or {}
        t = context.get("telemetry") or {}
        reserve = (d.get("reserve") or {}).get("target_soc")
        soc = t.get("battery_soc")
        grid = t.get("grid_present")
        risk = d.get("blackout_risk")
        parts = []
        if soc is not None and reserve is not None:
            parts.append(f"Battery is at {soc:.0f}% versus a reserve target of {reserve:.0f}%.")
        parts.append(f"Grid is {'present' if grid else 'absent'}.")
        if risk:
            parts.append(f"Blackout risk is {risk}.")
        rationale = (d.get("reserve") or {}).get("rationale")
        if rationale:
            parts.append(rationale)
        if d.get("summary"):
            parts.append(d["summary"])
        if not parts:
            return "No decision context is available yet."
        return " ".join(parts)
