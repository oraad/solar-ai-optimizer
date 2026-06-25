"""Local LLM assistant (Ollama) for natural-language explanations + control."""

from __future__ import annotations

import logging
import re

import httpx

from ..config import Settings
from ..engine.priorities import system_prompt_priorities
from ..i18n import LOCALE_NAMES, get_locale, t
from ..i18n.serialize import msg_text
from ..models import Override

SYSTEM_PROMPT_BASE_KEY = "assistant.system.base"


class Assistant:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def enabled(self) -> bool:
        return self._settings.llm_enabled

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
        locale = get_locale()
        language = LOCALE_NAMES.get(locale, "English")
        system = (
            f"{t(SYSTEM_PROMPT_BASE_KEY, locale=locale)}"
            f"{system_prompt_priorities(order, locale=locale)} "
            f"{t('assistant.system.answer', locale=locale)} "
            f"{t('assistant.prompt.respond_in', {'language': language}, locale=locale)}"
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
        decision = context.get("decision") or {}
        telemetry = context.get("telemetry") or {}
        reserve = (decision.get("reserve") or {}).get("target_soc")
        soc = telemetry.get("battery_soc")
        grid = telemetry.get("grid_present")
        risk = decision.get("blackout_risk")
        parts: list[str] = []
        if soc is not None and reserve is not None:
            parts.append(
                t(
                    "assistant.heuristic.soc_vs_reserve",
                    {"soc": f"{soc:.0f}", "reserve": f"{reserve:.0f}"},
                )
            )
        parts.append(
            t(
                "assistant.heuristic.grid_present"
                if grid
                else "assistant.heuristic.grid_absent"
            )
        )
        if risk:
            parts.append(
                t("assistant.heuristic.blackout_risk", {"risk": str(risk)})
            )
        rationale = (decision.get("reserve") or {}).get("rationale")
        if rationale:
            parts.append(msg_text(rationale))
        summary = decision.get("summary")
        if summary:
            parts.append(msg_text(summary))
        if not parts:
            return t("assistant.heuristic.no_context")
        return " ".join(parts)
