from __future__ import annotations

import argparse
from collections import Counter
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.llm_clients import MockLLMClient, OpenAICompatibleClient  # noqa: E402
from enh3bench.llm_verifier import (  # noqa: E402
    export_llm_verification_results,
    load_claim_rights_records,
    verify_records_with_llm,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify BoundaryLedger records with an optional LLM.")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--model", default=None)
    parser.add_argument("--max-records", type=int, default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key-env", default="auto")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--temperature", type=float, default=0)
    parser.add_argument("--max-tokens", type=int, default=1200)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--only-needs-review", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records = load_claim_rights_records(args.run_name)
    if args.only_needs_review:
        records = sorted(records, key=_review_priority, reverse=True)
    client, model = _client_from_args(args)
    _set_client_defaults(client, args)

    available, message = client.verify_available()
    if not available:
        print("LLM client is not available.")
        print(message)
        print("Set LLM_API_KEY/USTC_API_KEY, LLM_BASE_URL/USTC_BASE_URL, and LLM_MODEL/USTC_MODEL, or use --mock.")
        return 2

    results, failures = verify_records_with_llm(records, client, model=model, max_records=args.max_records, fail_fast=args.fail_fast)
    outputs = export_llm_verification_results(results, failures, args.run_name, model)
    counts = _counts(results, failures)

    print(f"records_loaded: {len(records)}")
    print(f"records_verified: {len(results)}")
    print(f"failures: {len(failures)}")
    print(f"needs_human_review: {counts['needs_human_review']}")
    print(f"boundary_agreement_count: {counts['boundary_agreement']}")
    print(f"llm_more_permissive_count: {counts['llm_more_permissive']}")
    print(f"llm_more_conservative_count: {counts['llm_more_conservative']}")
    print(f"parse_error_count: {counts['parse_error']}")
    print(f"schema_error_count: {counts['schema_error']}")
    print(f"parse_or_schema_error_count: {counts['parse_or_schema_error']}")
    print(f"low_trust_provenance_count: {counts['low_trust_provenance']}")
    print(f"llm_overrode_low_trust_count: {counts['llm_overrode_low_trust']}")
    print(f"trusted_boundary_capped_count: {counts['trusted_boundary_capped']}")
    print(f"JSONL: {outputs['jsonl']}")
    print(f"CSV: {outputs['csv']}")
    print(f"Failures: {outputs['failures_jsonl']}")
    return 1 if args.fail_fast and failures else 0


def _client_from_args(args: argparse.Namespace) -> tuple[Any, str]:
    if args.mock:
        return MockLLMClient(), args.model or "mock"
    api_key = None
    if args.api_key_env and args.api_key_env != "auto":
        api_key = os.environ.get(args.api_key_env)
    client = OpenAICompatibleClient(api_key=api_key, base_url=args.base_url, model=args.model, timeout=args.timeout)
    return client, args.model or client.model or "unknown"


def _set_client_defaults(client: Any, args: argparse.Namespace) -> None:
    client.temperature = args.temperature
    client.max_tokens = args.max_tokens
    client.timeout = args.timeout


def _review_priority(record: dict[str, Any]) -> int:
    score = 0
    if record.get("overclaim_risk_flags"):
        score += 4
    if record.get("is_reject_or_low_trust"):
        score += 4
    if record.get("text_class_provenance_conflict"):
        score += 4
    gates = record.get("validation_gates") if isinstance(record.get("validation_gates"), dict) else {}
    if any(value != "yes" for value in gates.values()):
        score += 2
    if record.get("missing_boundary_fields"):
        score += 1
    return score


def _counts(results: list[dict[str, Any]], failures: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    counts["failures"] = len(failures)
    for result in results:
        for key in ("needs_human_review", "boundary_agreement", "llm_more_permissive", "llm_more_conservative"):
            if bool(result.get(key)):
                counts[key] += 1
        error = str(result.get("llm_parse_error") or "")
        if error:
            counts["parse_or_schema_error"] += 1
        if error.startswith("json_parse_error:"):
            counts["parse_error"] += 1
        if error.startswith("schema_invalid:"):
            counts["schema_error"] += 1
        flags = _list_values(result.get("llm_audit_flags"))
        if bool(result.get("low_trust_provenance")):
            counts["low_trust_provenance"] += 1
        if "llm_overrode_low_trust_provenance" in flags:
            counts["llm_overrode_low_trust"] += 1
        if "trusted_boundary_capped_by_provenance" in flags:
            counts["trusted_boundary_capped"] += 1
    return counts


def _list_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value.strip():
        stripped = value.strip()
        if stripped.startswith("["):
            try:
                import json

                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        return [part.strip() for part in stripped.split(",") if part.strip()]
    return []


if __name__ == "__main__":
    raise SystemExit(main())
