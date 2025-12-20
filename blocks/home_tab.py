"""Slack Home Tab implementing the five-workspace navigation."""
from __future__ import annotations

import datetime as dt
from typing import Dict, List

from config import Brand
from services.chart_service import generate_confidence_ring, generate_gateway_motif


async def build_home_tab(
    project: Dict,
    assumptions: List[Dict[str, object]],
    current_workspace: str = "overview",
) -> Dict:
    """Build the Home tab with navigation-aware workspaces."""

    brand = Brand()
    active_assumptions = [a for a in assumptions if a.get("status") != "archived"]
    confidence_scores = [float(a.get("confidence_score", 0)) for a in active_assumptions]
    chart_url = await generate_confidence_ring(confidence_scores)

    workspace_renderers = {
        "overview": render_overview_workspace,
        "discovery": render_discovery_workspace,
        "roadmap": render_roadmap_workspace,
        "experiments": render_experiments_workspace,
        "team": render_team_workspace,
    }

    workspace_blocks = await workspace_renderers.get(
        current_workspace, render_overview_workspace
    )(project, active_assumptions, chart_url, brand)

    blocks: List[Dict] = [
        {"type": "header", "text": {"type": "plain_text", "text": "Evidently — OCP Dashboard", "emoji": True}},
        navigation_block(current_workspace),
    ]
    blocks.extend(workspace_blocks)
    blocks.append(next_step_footer(current_workspace, len(active_assumptions)))

    return {"type": "home", "blocks": blocks}


def navigation_block(current_workspace: str) -> Dict:
    buttons = [
        ("overview", "🏠 Overview"),
        ("discovery", "💡 Discovery"),
        ("roadmap", "🗺️ Roadmap"),
        ("experiments", "⚗️ Experiments"),
        ("team", "👥 Team"),
    ]

    elements = []
    for value, label in buttons:
        element: Dict[str, object] = {
            "type": "button",
            "text": {"type": "plain_text", "text": label, "emoji": True},
            "action_id": f"nav_{value}",
            "value": value,
        }
        if value == current_workspace:
            element["style"] = "primary"
        elements.append(element)

    return {"type": "actions", "elements": elements}


async def render_overview_workspace(
    project: Dict, assumptions: List[Dict[str, object]], chart_url: str, brand: Brand
) -> List[Dict]:
    inbox = assumptions[:5]
    motif_url = await generate_gateway_motif(project.get("name", "Project"), "Confidence and AI suggestions")

    blocks: List[Dict] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{project.get('name', 'Project')}* — Confidence ring refreshed with Nesta teal.",
            },
            "accessory": {
                "type": "image",
                "image_url": chart_url,
                "alt_text": "Confidence ring",
            },
        },
        {
            "type": "image",
            "title": {"type": "plain_text", "text": "Gateway motif"},
            "image_url": motif_url,
            "alt_text": "Gateway motif",
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Inbox — AI suggestions*"},
            "accessory": {
                "type": "button",
                "text": {"type": "plain_text", "text": "Sync Evidence", "emoji": True},
                "style": "primary",
                "action_id": "sync_documents",
            },
        },
    ]

    if not inbox:
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": "No new AI suggestions yet."}],
            }
        )
    else:
        for assumption in inbox:
            blocks.append(_assumption_row(assumption, brand))

    return blocks


async def render_discovery_workspace(
    project: Dict, assumptions: List[Dict[str, object]], chart_url: str, brand: Brand
) -> List[Dict]:
    del project, chart_url  # unused in this workspace
    opportunity = [a for a in assumptions if a.get("category") == "opportunity"]
    capability = [a for a in assumptions if a.get("category") == "capability"]
    progress = [a for a in assumptions if a.get("category") == "progress"]

    blocks: List[Dict] = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*OCP Canvas*"},
            "accessory": {
                "type": "button",
                "text": {"type": "plain_text", "text": "Add Assumption", "emoji": True},
                "style": "primary",
                "action_id": "add_assumption",
            },
        }
    ]

    blocks.extend(_canvas_column("🟡 Opportunity", opportunity, brand.COLOR_OPPORTUNITY))
    blocks.extend(_canvas_column("🟢 Capability", capability, brand.COLOR_CAPABILITY))
    blocks.extend(_canvas_column("🔵 Progress", progress, brand.COLOR_PROGRESS))

    return blocks


async def render_roadmap_workspace(
    project: Dict, assumptions: List[Dict[str, object]], chart_url: str, brand: Brand
) -> List[Dict]:
    del chart_url, brand
    now_items = [a.get("text", "") for a in assumptions[:3]] or ["Clarify now lane"]
    next_items = [a.get("text", "") for a in assumptions[3:5]] or ["Prioritise next steps"]
    later_items = [a.get("text", "") for a in assumptions[5:7]] or ["Backlog for later"]

    def _lane(title: str, items: List[str]) -> Dict:
        return {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"*{title}*"},
                {
                    "type": "mrkdwn",
                    "text": "\n".join([f"• {item}" for item in items]),
                },
            ],
        }

    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": "*Roadmap — Now / Next / Later*"}},
        _lane("Now", now_items),
        _lane("Next", next_items),
        _lane("Later", later_items),
    ]


async def render_experiments_workspace(
    project: Dict, assumptions: List[Dict[str, object]], chart_url: str, brand: Brand
) -> List[Dict]:
    del project, chart_url, brand
    experiments = [
        {"name": "Field test", "status": "green", "metric": "Engagement steady"},
        {"name": "Prototype feedback", "status": "amber", "metric": "Waiting on 3 interviews"},
    ]

    blocks: List[Dict] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": "*Active experiments*"}},
    ]

    for experiment in experiments:
        indicator = {
            "green": "🟢",
            "amber": "🟡",
            "red": "🔴",
        }.get(experiment.get("status", "green"), "🟢")
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{indicator} *{experiment['name']}*\n{experiment['metric']}",
                },
            }
        )

    return blocks


async def render_team_workspace(
    project: Dict, assumptions: List[Dict[str, object]], chart_url: str, brand: Brand
) -> List[Dict]:
    del project, chart_url, brand
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Decision Room* — silent scoring to avoid anchoring.",
            },
            "accessory": {
                "type": "button",
                "text": {"type": "plain_text", "text": "Start Decision Session", "emoji": True},
                "style": "primary",
                "action_id": "start_decision_session",
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "Use Impact and Uncertainty sliders (1-5). Scores stay private until reveal.",
                }
            ],
        },
    ]


def _assumption_row(assumption: Dict[str, object], brand: Brand) -> Dict:
    last_verified_at = assumption.get("last_verified_at")
    stale_cutoff = dt.datetime.utcnow() - dt.timedelta(days=14)
    is_stale = True
    if last_verified_at:
        try:
            verified_dt = dt.datetime.fromisoformat(str(last_verified_at))
            is_stale = verified_dt < stale_cutoff
        except Exception:
            is_stale = True
    icon = ":snowflake:" if is_stale else ":fire:"
    confidence = assumption.get("confidence_score", 0)
    text = assumption.get("text", "")

    return {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"{icon} {text}\n*Confidence:* {confidence}%",
        },
        "accessory": {
            "type": "button",
            "text": {"type": "plain_text", "text": "Generate Test", "emoji": True},
            "action_id": "generate_test",
            "value": str(text),
        },
    }


def _canvas_column(title: str, items: List[Dict[str, object]], hex_colour: str) -> List[Dict]:
    blocks: List[Dict] = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{title}*"},
            "accessory": {
                "type": "image",
                "image_url": f"https://singlecolorimage.com/get/{hex_colour.strip('#')}/20x20",
                "alt_text": "Colour bar",
            },
        }
    ]
    if not items:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "No assumptions yet."}]})
        return blocks

    for assumption in items:
        blocks.append(_assumption_row(assumption, Brand()))
    return blocks


def next_step_footer(current_workspace: str, inbox_count: int) -> Dict:
    suggestions = {
        "overview": f"Review {inbox_count or 'the'} AI suggestions to unlock discovery.",
        "discovery": "Capture a fresh assumption and categorise it.",
        "roadmap": "Move an assumption to Next to prioritise.",
        "experiments": "Monitor live metrics and set a stop condition.",
        "team": "Start a Decision Room to align scores silently.",
    }
    return {
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": f"*Next step:* {suggestions.get(current_workspace, 'Keep progressing with the workflow.')}",
            }
        ],
    }
