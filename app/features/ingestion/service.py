"""Ingestion orchestration service."""
import logging

from app.features.ingestion.schemas import Tick

logger = logging.getLogger(__name__)


class IngestionService:
    """Orchestrates the ingestion of raw ticks through the processing pipeline."""

    async def process(self, tick: Tick) -> None:
        """Normalise, validate and route a tick through the pipeline."""
        pass

    async def validate_tick(self, tick: Tick) -> bool:
        """Return True if the tick passes sanity checks (non-zero price, valid symbol)."""
        pass
