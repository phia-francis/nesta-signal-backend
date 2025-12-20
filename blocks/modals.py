"""Slack modals for Evidently interactions."""
from __future__ import annotations

from typing import Dict, List

from config import Brand


def generate_test_modal(assumption_text: str) -> Dict:
    brand = Brand()
    return {
        "type": "modal",
        "callback_id": "generate_test_modal",
        "title": {"type": "plain_text", "text": "Generate Test"},
        "submit": {"type": "plain_text", "text": "Send"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Assumption*\n{assumption_text}"},
            },
            {
                "type": "input",
                "block_id": "focus_area",
                "element": {
                    "type": "static_select",
                    "action_id": "focus",
                    "placeholder": {"type": "plain_text", "text": "Select focus"},
                    "options": [
                        {"text": {"type": "plain_text", "text": "Fake Door"}, "value": "fake_door"},
                        {"text": {"type": "plain_text", "text": "Interview"}, "value": "interview"},
                        {"text": {"type": "plain_text", "text": "Prototype"}, "value": "prototype"},
                    ],
                },
                "label": {"type": "plain_text", "text": "Experiment Type"},
            },
            {
                "type": "input",
                "block_id": "custom_prompt",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "prompt",
                    "multiline": True,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Context or constraints for the experiment",
                    },
                },
                "label": {"type": "plain_text", "text": "Details"},
                "optional": True,
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f":bulb: Suggestions use Nesta brand colours like {brand.TEAL} and {brand.NESTA_BLUE}.",
                    }
                ],
            },
        ],
    }


def decision_room_modal(assumptions: List[Dict[str, str]]) -> Dict:
    """Modal to capture Impact and Uncertainty scores for a selected assumption."""

    options = [
        {
            "text": {"type": "plain_text", "text": assumption.get("text", "Assumption")[:75]},
            "value": assumption.get("id", assumption.get("text", "assumption"))[:75],
        }
        for assumption in assumptions
    ] or [
        {
            "text": {"type": "plain_text", "text": "No assumptions yet"},
            "value": "none",
        }
    ]

    score_options = [
        {"text": {"type": "plain_text", "text": str(i)}, "value": str(i)} for i in range(1, 6)
    ]

    return {
        "type": "modal",
        "callback_id": "decision_room_modal",
        "title": {"type": "plain_text", "text": "Decision Room"},
        "submit": {"type": "plain_text", "text": "Save"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Select an assumption to score privately before reveal.",
                },
            },
            {
                "type": "input",
                "block_id": "assumption_id",
                "label": {"type": "plain_text", "text": "Assumption"},
                "element": {
                    "type": "static_select",
                    "action_id": "assumption_select",
                    "placeholder": {"type": "plain_text", "text": "Choose"},
                    "options": options,
                },
            },
            {
                "type": "input",
                "block_id": "impact",
                "label": {"type": "plain_text", "text": "Impact (1-5)"},
                "element": {
                    "type": "static_select",
                    "action_id": "impact_select",
                    "options": score_options,
                    "placeholder": {"type": "plain_text", "text": "Select"},
                },
            },
            {
                "type": "input",
                "block_id": "uncertainty",
                "label": {"type": "plain_text", "text": "Uncertainty (1-5)"},
                "element": {
                    "type": "static_select",
                    "action_id": "uncertainty_select",
                    "options": score_options,
                    "placeholder": {"type": "plain_text", "text": "Select"},
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "Scores remain private until the facilitator reveals them.",
                    }
                ],
            },
        ],
    }
