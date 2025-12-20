"""Generate Nesta-branded charts via QuickChart."""
from __future__ import annotations

import json
from typing import Iterable, List
from urllib.parse import quote

import httpx

from config import Brand


async def generate_confidence_ring(confidence_scores: Iterable[float]) -> str:
    """Generate a QuickChart doughnut showing average confidence.

    Falls back to an inline URL if the QuickChart shortener is unavailable.
    """
    scores: List[float] = [float(score) for score in confidence_scores if score is not None]
    average = sum(scores) / len(scores) if scores else 0
    brand = Brand()

    chart_config = _build_ring_payload(average, brand)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://quickchart.io/chart/create", json={"chart": chart_config}
            )
            if response.status_code == 200:
                data = response.json()
                url = data.get("url")
                if url:
                    return url
    except Exception:
        # Silent fallback to inline chart URL
        pass

    encoded_config = quote(json.dumps(chart_config))
    return f"https://quickchart.io/chart?c={encoded_config}"


def _build_ring_payload(average_confidence: float, brand: Brand) -> dict:
    average = max(0, min(100, round(average_confidence, 1)))
    remainder = max(0, 100 - average)
    return {
        "type": "doughnut",
        "data": {
            "datasets": [
                {
                    "data": [average, remainder],
                    "backgroundColor": [brand.NESTA_TEAL, brand.NESTA_NAVY],
                    "borderColor": brand.NESTA_AQUA,
                    "borderWidth": 3,
                    "cutout": "72%",
                }
            ]
        },
        "options": {
            "plugins": {
                "legend": {"display": False},
                "tooltip": {"enabled": False},
                "title": {
                    "display": True,
                    "text": f"Confidence {average}%",
                    "color": brand.NESTA_NAVY,
                    "font": {"size": 18, "family": brand.FONT_BODY, "weight": "bold"},
                },
            },
        },
    }


async def generate_gateway_motif(title: str, subtitle: str = "") -> str:
    """Create a Gateway motif image with a 45-degree fold using QuickChart."""

    brand = Brand()
    chart_config = {
        "type": "bar",
        "data": {
            "labels": [""],
            "datasets": [
                {
                    "data": [100],
                    "backgroundColor": f"{brand.NESTA_NAVY}B3",
                    "borderColor": brand.NESTA_NAVY,
                    "borderWidth": 0,
                    "barPercentage": 1.0,
                    "categoryPercentage": 1.0,
                },
                {
                    "data": [70],
                    "backgroundColor": f"{brand.NESTA_AMBER}CC",
                    "borderColor": brand.NESTA_AMBER,
                    "borderWidth": 0,
                    "barPercentage": 0.9,
                    "categoryPercentage": 1.0,
                },
            ],
        },
        "options": {
            "indexAxis": "y",
            "plugins": {
                "legend": {"display": False},
                "title": {
                    "display": True,
                    "text": title,
                    "color": brand.NESTA_NAVY,
                    "align": "start",
                    "font": {"family": brand.FONT_HEADLINE, "size": 18},
                },
                "subtitle": {
                    "display": bool(subtitle),
                    "text": subtitle,
                    "color": brand.NESTA_TEAL,
                    "align": "start",
                    "font": {"family": brand.FONT_BODY, "size": 12},
                },
            },
            "scales": {
                "x": {"display": False, "max": 110},
                "y": {"display": False},
            },
            "layout": {"padding": 16},
        },
        "plugins": [
            {
                "id": "gateway-mask",
                "beforeDraw": "function(chart, args, options) { const ctx = chart.ctx; const {chartArea} = chart; ctx.save(); ctx.fillStyle = 'rgba(0,0,0,0)'; ctx.beginPath(); ctx.moveTo(chartArea.right, chartArea.top); ctx.lineTo(chartArea.right - 24, chartArea.top); ctx.lineTo(chartArea.right, chartArea.top + 24); ctx.closePath(); ctx.clip(); ctx.restore(); }",
            }
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post("https://quickchart.io/chart/create", json={"chart": chart_config})
            if response.status_code == 200:
                url = response.json().get("url")
                if url:
                    return url
    except Exception:
        pass

    encoded_config = quote(json.dumps(chart_config))
    return f"https://quickchart.io/chart?c={encoded_config}"
