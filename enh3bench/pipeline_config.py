"""Configuration object for the unified eNH3-Scholar CLI pipeline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PipelineConfig:
    input_dir: str
    markdown_dir: str
    run_name: str
    top_n: int
    max_per_paper: int
    stop_at: str
    skip_conversion: bool
    papers_path: str | None
    converter: str = "auto"
    force_reconvert: bool = False
    clean_markdown: bool = False
