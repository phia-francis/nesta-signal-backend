"""Shared configuration and Nesta brand tokens for Evidently."""
from dataclasses import dataclass
import os
from typing import Dict


@dataclass(frozen=True)
class Brand:
    """Immutable Nesta palette, typography, and semantic mappings."""

    # Core Palette
    NESTA_BLUE: str = "#0000FF"  # Hero / Digital Only
    NESTA_NAVY: str = "#0F294A"  # Text / Headers
    NESTA_TEAL: str = "#0FA3A4"  # Primary / Success
    NESTA_AMBER: str = "#FFB703"  # CTA / Warning
    NESTA_RED: str = "#EB003B"  # Danger / Off-track
    NESTA_AQUA: str = "#97D9E3"  # Secondary / Backgrounds
    NESTA_PURPLE: str = "#9A1BBE"  # Experiments

    # OCP Semantic Mapping
    COLOR_OPPORTUNITY: str = NESTA_AMBER
    COLOR_CAPABILITY: str = NESTA_TEAL
    COLOR_PROGRESS: str = NESTA_BLUE

    # Fonts (For Image Generation Only)
    FONT_HEADLINE: str = "Zosia Display"
    FONT_BODY: str = "Averta"

    @property
    def ocp_colors(self) -> Dict[str, str]:
        return {
            "opportunity": self.COLOR_OPPORTUNITY,
            "capability": self.COLOR_CAPABILITY,
            "progress": self.COLOR_PROGRESS,
        }


@dataclass
class Settings:
    """Environment-driven application settings."""

    slack_bot_token: str = os.getenv("SLACK_BOT_TOKEN", "")
    slack_app_token: str = os.getenv("SLACK_APP_TOKEN", "")
    slack_signing_secret: str = os.getenv("SLACK_SIGNING_SECRET", "")

    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_key: str = os.getenv("SUPABASE_KEY", "")

    google_credentials: str = os.getenv("GOOGLE_CREDENTIALS", "")

    @property
    def brand(self) -> Brand:
        return Brand()


settings = Settings()
