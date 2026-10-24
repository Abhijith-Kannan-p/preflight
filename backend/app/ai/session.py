"""Per-review AI session: one gateway, one masker and one call log shared by all AI steps."""

from dataclasses import dataclass, field

from app.ai.gateway import CallLog, Gateway
from app.ai.masking import Masker


@dataclass
class AiSession:
    gateway: Gateway
    masker: Masker
    log: CallLog = field(default_factory=CallLog)

    @property
    def llm_available(self) -> bool:
        return self.gateway.available
