"""LLM seam: rationale-memo generation behind a backend interface.

LLMs never compute money. A backend receives a payload of numbers already
computed by the engine and verbalizes them. Every generated memo passes the
numeric guard: any figure not present in the input payload rejects the memo.

Active backend in the local demo: TemplateMemoBackend (deterministic).
Production path: BedrockBackend (Claude via Amazon Bedrock), same interface.
"""

from shared.bedrock.backends import (
    BedrockBackend,
    MemoResult,
    RationaleBackend,
    TemplateMemoBackend,
)
from shared.bedrock.guard import GuardViolation, numeric_guard
from shared.bedrock.payloads import CompRecord, RationalePayload, ShapDriver

__all__ = [
    "BedrockBackend",
    "CompRecord",
    "GuardViolation",
    "MemoResult",
    "RationaleBackend",
    "RationalePayload",
    "ShapDriver",
    "TemplateMemoBackend",
    "numeric_guard",
]
