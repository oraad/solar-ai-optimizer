"""Local LLM assistant (Ollama) for natural-language explanations + control."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

import httpx

from ..config import Settings
from ..engine.priorities import system_prompt_priorities
from ..i18n import LOCALE_NAMES, get_locale, t
from ..i18n.serialize import msg_text
from ..models import Override

SYSTEM_PROMPT_BASE_KEY = "assistant.system.base"

log = logging.getLogger("assistant")

_KILL_SWITCH_RE = re.compile(
    r"\b(kill switch|emergency|grid charge at max|charge at max)\b"
)
_PAUSE_RULES: tuple[tuple[re.Pattern[str], Callable[[Override], None]], ...] = (
    (re.compile(r"\bpause\b.*\bshed"), lambda ov: setattr(ov, "pause_shedding", True)),
    (re.compile(r"\bpause\b.*\bgrid"), lambda ov: setattr(ov, "pause_grid_charge", True)),
    (re.compile(r"\bpause\b.*\boptim"), lambda ov: setattr(ov, "pause_optimization", True)),
    (re.compile(r"\bpause\b"), lambda ov: setattr(ov, "pause_engine", True)),
)
_RESUME_RULES: tuple[tuple[re.Pattern[str], Callable[[Override], None]], ...] = (
    (re.compile(r"\b(resume|unpause|continue)\b.*\bshed"), lambda ov: setattr(ov, "pause_shedding", False)),
    (re.compile(r"\b(resume|unpause|continue)\b.*\bgrid"), lambda ov: setattr(ov, "pause_grid_charge", False)),
    (re.compile(r"\b(resume|unpause|continue)\b.*\boptim"), lambda ov: setattr(ov, "pause_optimization", False)),
    (re.compile(r"\b(resume|unpause|continue)\b"), lambda ov: setattr(ov, "pause_engine", False)),
)
_INDEPENDENT_RULES: tuple[tuple[re.Pattern[str], Callable[[Override], None]], ...] = (
    (re.compile(r"\b(force|start).*(grid )?charg"), lambda ov: setattr(ov, "force_grid_charge", True)),
    (re.compile(r"\b(stop|cancel|release).*(grid )?charg"), lambda ov: setattr(ov, "force_grid_charge", False)),
    (re.compile(r"\b(live|enable control|go live)\b"), lambda ov: setattr(ov, "shadow_mode", False)),
    (re.compile(r"\b(shadow|observe only|dry run)\b"), lambda ov: setattr(ov, "shadow_mode", True)),
)
_RESERVE_RE = re.compile(r"reserve\D{0,12}(\d{1,3})\s*%?")


def _apply_first_match(
    q: str,
    ov: Override,
    rules: tuple[tuple[re.Pattern[str], Callable[[Override], None]], ...],
) -> bool:
    for pattern, apply in rules:
        if pattern.search(q):
            apply(ov)
            return True
    return False


class Assistant:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def enabled(self) -> bool:
        return self._settings.llm_enabled

    def parse_intent(self, question: str) -> Override | None:
        """Deterministically map common control phrases to an Override."""
        q = question.lower().strip()
        if _KILL_SWITCH_RE.search(q):
            return Override(kill_switch=True)

        ov = Override()
        matched = False
        for pattern, apply in _INDEPENDENT_RULES:
            if pattern.search(q):
                apply(ov)
                matched = True
        if _apply_first_match(q, ov, _PAUSE_RULES):
            matched = True
        if _apply_first_match(q, ov, _RESUME_RULES):
            matched = True
        m = _RESERVE_RE.search(q)
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
