class ExecutionEngineError(Exception):
    """Base exception for all domain errors."""


class PipelineError(ExecutionEngineError):
    """Raised when tick ingestion pipeline fails unrecoverably."""


class TradeError(ExecutionEngineError):
    """Raised when trade simulation or persistence fails."""


class SpikeDetectionError(ExecutionEngineError):
    """Raised when spike detection encounters an unrecoverable error."""


class NotificationError(ExecutionEngineError):
    """Raised when a notification cannot be delivered."""


class AIServiceError(ExecutionEngineError):
    """Raised when the AI query layer fails."""


class ConfigurationError(ExecutionEngineError):
    """Raised when a required configuration value is missing or invalid."""
