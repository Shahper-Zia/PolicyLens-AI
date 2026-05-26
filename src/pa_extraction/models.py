"""Shared data models for PA policy extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ParameterRule:
    """Externalized retrieval hints for one output parameter."""

    name: str
    output_field: str
    group: str
    definition: str = ""
    keywords: list[str] = field(default_factory=list)
    section_priorities: list[str] = field(default_factory=list)
    inclusion_signals: list[str] = field(default_factory=list)
    exclusion_signals: list[str] = field(default_factory=list)
    normalization_hints: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RuleBook:
    """Loaded rules plus optional alias metadata."""

    parameters: dict[str, ParameterRule]
    groups: dict[str, list[str]]
    brand_aliases: dict[str, list[str]] = field(default_factory=dict)
    indication_aliases: dict[str, list[str]] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Section:
    """A logical section parsed from a policy document."""

    title: str
    text: str
    start: int
    end: int
    heading_level: int = 0
    section_type: str = "unknown"


@dataclass(frozen=True)
class Chunk:
    """A retrievable chunk with enough metadata to audit why it was selected."""

    text: str
    section_title: str
    section_type: str
    chunk_index: int
    start: int
    end: int
    heading_level: int = 0
    score: float = 0.0
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExtractionContext:
    """The row-specific scope that every extraction must honor."""

    file_name: str
    brand: str
    indication: str
    brand_terms: list[str]
    indication_terms: list[str]
