from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel


class Settings(BaseModel):
    """Runtime settings. Everything is read from the environment so the same
    containers run on a laptop, a regional cloud region or an air-gapped rack."""

    app_name: str = "Rasad"
    database_url: str = os.getenv("RASAD_DATABASE_URL", "sqlite:///./rasad.db")
    # Extraction model provider: "anthropic" during development, "local" for an
    # in-country open-weight model served behind an OpenAI-compatible endpoint.
    model_provider: str = os.getenv("RASAD_MODEL_PROVIDER", "anthropic")
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY")
    anthropic_model: str = os.getenv("RASAD_ANTHROPIC_MODEL", "claude-sonnet-5-5")
    local_model_base_url: str | None = os.getenv("RASAD_LOCAL_MODEL_BASE_URL")
    local_model_name: str = os.getenv("RASAD_LOCAL_MODEL_NAME", "jais-2-70b-chat")
    # Where fetched source documents are cached on disk (never leaves the host).
    data_dir: str = os.getenv("RASAD_DATA_DIR", "./data")
    # Egress allow-list: connectors refuse any host not listed here.
    egress_allowlist: list[str] = [
        h.strip()
        for h in os.getenv(
            "RASAD_EGRESS_ALLOWLIST",
            "ukmto.org,mscio.eu,combinedmaritimeforces.com,portwatch.imf.org,"
            "lmalloyds.com,sanctionslist.ofac.treas.gov,www.gov.uk,assets.publishing.service.gov.uk,"
            "www.state.gov,api.gdeltproject.org,data.gdeltproject.org,qna.org.qa,wam.ae,spa.gov.sa,"
            "www.mediaoffice.abudhabi,tasnimnews.ir,api.congress.gov,api.govinfo.gov",
        ).split(",")
        if h.strip()
    ]
    # Engine defaults
    panel_extremising_exponent: float = float(os.getenv("RASAD_PANEL_EXTREMISE", "1.3"))
    machine_weight: float = float(os.getenv("RASAD_MACHINE_WEIGHT", "0.5"))
    probability_floor: float = 0.02
    probability_ceiling: float = 0.98


@lru_cache
def get_settings() -> Settings:
    return Settings()
