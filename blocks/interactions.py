"""Shared interactive block patterns."""
from __future__ import annotations

from typing import Dict

from config import Brand


def error_block(message: str = "The AI brain is briefly offline.") -> Dict:
    brand = Brand()
    return {
        "type": "section",
        "text": {"type": "mrkdwn", "text": f":warning: *{message}*"},
        "accessory": {
            "type": "image",
            "image_url": f"https://singlecolorimage.com/get/{brand.RED.strip('#')}/32x32",
            "alt_text": "Error",
        },
    }


def so_what_blocks(summary: Dict) -> Dict:
    """Render a colour-coded So What summary for Slack threads."""
    brand = Brand()
    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*So What? — Key signals*"},
        },
    ]

    if summary.get("summary"):
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": summary.get("summary")},
            }
        )

    if "key_decision" in summary:
        decision_text = "Yes" if summary.get("key_decision") else "No"
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Key decision required:* {decision_text}",
                    }
                ],
            }
        )

    decisions = summary.get("decisions", [])
    actions = summary.get("actions", [])
    assumptions = summary.get("assumptions", [])
    emergent = summary.get("emergent_assumptions", [])

    if decisions:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*Decisions*\n• " + "\n• ".join(decisions)},
            }
        )

    if actions:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*Actions*\n• " + "\n• ".join(actions)},
            }
        )

    if emergent:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*Emergent assumptions*\n• " + "\n• ".join(emergent)},
            }
        )

    if assumptions:
        blocks.append({"type": "divider"})
        category_order = ["opportunity", "capability", "progress"]
        color_lookup = brand.ocp_colors
        for category in category_order:
            category_assumptions = [a for a in assumptions if a.get("category") == category]
            if not category_assumptions:
                continue
            header = category.capitalize()
            emoji = "🔥" if category != "progress" else "🔵"
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*{header}*"},
                    "accessory": {
                        "type": "image",
                        "image_url": f"https://singlecolorimage.com/get/{color_lookup.get(category, brand.NESTA_BLUE).strip('#')}/24x24",
                        "alt_text": f"{header} marker",
                    },
                }
            )
            for assumption in category_assumptions:
                icon = ":snowflake:" if assumption.get("status") == "stale" else ":fire:"
                confidence = assumption.get("confidence_score", 0)
                text = assumption.get("text", "")
                provenance = assumption.get("provenance_source", "")
                blocks.append(
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"{icon} {text}\n{emoji} Confidence: *{confidence}%*",
                        },
                    }
                )
                if provenance:
                    blocks.append(
                        {
                            "type": "context",
                            "elements": [
                                {
                                    "type": "mrkdwn",
                                    "text": f"🤖 Confidence: {confidence}% | Source: {provenance}",
                                }
                            ],
                        }
                    )

    return {"blocks": blocks}
