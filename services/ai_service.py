"""Gemini-powered summarisation and assumption extraction."""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

import google.generativeai as genai

from config import settings

SYSTEM_PROMPT = """
You are Evidently, Nesta's Test & Learn assistant. Respond with VALID JSON ONLY in British English.

Output schema (no extra keys):
{
  "summary": string,
  "key_decision": boolean,
  "emergent_assumptions": [string],
  "assumptions": [
    {
      "text": string,
      "category": "opportunity"|"capability"|"progress",
      "confidence_score": number (0-100),
      "status": "active"|"stale"|"archived",
      "last_verified_at": ISO8601 datetime string,
      "provenance_source": string
    }
  ],
  "decisions": [string],
  "actions": [string]
}

Rules:
- If evidence is missing or unclear set status to "stale".
- Always include confidence_score, provenance_source, and last_verified_at for each assumption.
- Do not wrap JSON in prose or code fences.
- If files were provided, incorporate their descriptions when extracting assumptions.
"""


def _configure_client() -> None:
    if settings.gemini_api_key:
        genai.configure(api_key=settings.gemini_api_key)


class AIService:
    """Wrapper around Gemini for structured outputs."""

    def __init__(self) -> None:
        _configure_client()
        self.model = settings.gemini_model

    async def generate_summary(
        self, thread_text: str, attachments: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        prompt = self._build_prompt(thread_text, attachments or [])
        try:
            model = genai.GenerativeModel(self.model, generation_config={"temperature": 0.2})
            response = model.generate_content(prompt)
            text = response.text or "{}"
            return self._safe_json(text)
        except Exception:
            return {"error": "The AI brain is briefly offline."}

    async def extract_assumptions(self, document_text: str) -> List[Dict[str, Any]]:
        prompt = self._build_prompt(document_text, [])
        try:
            model = genai.GenerativeModel(self.model, generation_config={"temperature": 0.15})
            response = model.generate_content(prompt)
            data = self._safe_json(response.text or "{}")
            assumptions = data.get("assumptions", [])
            now_iso = dt.datetime.utcnow().isoformat()
            for assumption in assumptions:
                assumption.setdefault("last_verified_at", now_iso)
                assumption.setdefault("status", "active")
                assumption.setdefault("provenance_source", "Gemini extraction")
            return assumptions
        except Exception:
            return []

    def _build_prompt(self, content: str, attachments: List[Dict[str, Any]]) -> str:
        attachment_lines = []
        for item in attachments:
            descriptor = item.get("text") or item.get("title") or "Attached file"
            attachment_lines.append(
                f"Attachment ({item.get('type','file')}): {descriptor}"
            )
        attachment_text = "\n".join(attachment_lines)
        return f"{SYSTEM_PROMPT}\nContent:\n{content}\n{attachment_text}\nExplain assumptions with provenance and confidence, then return JSON only."

    def _safe_json(self, text: str) -> Dict[str, Any]:
        import json
        import re

        try:
            return json.loads(text)
        except Exception:
            pass

        try:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except Exception:
            return {}
        return {}


aio_service = AIService()
