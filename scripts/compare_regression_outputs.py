"""Offline, gold-aware diagnosis for A/B matcher output; never send GOLD to an LLM.

Inputs are raw match_batch JSON arrays from the SAME query list, environment,
catalog, and Qdrant snapshot. Outputs include case-level GOLD and belong in .tmp/.
A known-positive list is not an exhaustive list of technically valid LD products.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from nomenclature_matcher.query_signals import (
    explicit_dn_from_query, explicit_pn_mpa_from_query,
    explicit_technical_signal_count, has_product_identity,
)


def _ids(items: object) -> set[int]:
    answer: set[int] = set()
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict):
            item = item.get("ld_id")
        try:
            if item is not None:
                answer.add(int(item))
        except (TypeError, ValueError):
            pass
    return answer


def predicted_ld_id(response: dict) -> int | None:
    if response.get("status") != "MATCHED":
        return None
    selected = (response.get("debug") or {}).get("selected") or []
    ids = _ids(selected[:1])
    return next(iter(ids), None)


def allowed_sparse_refusal(query: str, response: dict) -> bool:
    """Audit only; does not change the matching gate.

    A generic type and a single DN alone are insufficient, regardless of
    whether a historical human reviewer could find an arbitrary catalog item.
    """
    debug = response.get("debug") or {}
    reason = str(debug.get("reason") or "")
    interpretation = debug.get("query_interpretation") or {}
    return (
        response.get("status") == "NOT_FOUND"
        and str(reason).startswith("QUERY_REJECTED")
        and not has_product_identity(query)
        and explicit_technical_signal_count(query) <= 1
        # The legacy technical-signal regex does not count joined "PN16"
        # notation. DN50 PN16 is a sufficiently specified query, never sparse.
        and not (explicit_dn_from_query(query) is not None
                 and explicit_pn_mpa_from_query(query) is not None)
        and (
            "Недостаточно различающих характеристик" in reason
            or "Недостаточно" in str(interpretation.get("reason", ""))
        )
    )


def stage_of_failure(response: dict, acceptable: set[int]) -> str:
    """Use candidate funnel evidence only, not guessed missing-stage causes."""
    status = response.get("status")
    debug = response.get("debug") or {}
    reason = str(debug.get("reason") or "")
    if status == "RERANK_FAILED":
        return "PIPELINE_ERROR"
    if reason.startswith("QUERY_REJECTED"):
        return "QUERY_GATE"
    trace = (debug.get("query_interpretation") or {}).get("retrieval_trace") or {}
    prefilter = trace.get("technical_prefilter") or {}
    if trace:
        wide = _ids(prefilter.get("rows") or (trace.get("retriever") or {}).get("rrf_pool") or [])
        short = _ids(trace.get("initial_candidate_ids") or [])
        eligible = _ids(trace.get("rerank_candidate_ids") or [])
        second_chance = _ids(trace.get("second_chance_candidate_ids") or [])
        if wide and not (wide & acceptable):
            if second_chance & acceptable:
                return "SECOND_CHANCE_NOT_SELECTED"
            return "RETRIEVAL_MISS"
        if wide & acceptable and short and not (short & acceptable):
            return "TECHNICAL_PREFILTER_DROP"
        if short & acceptable and not (eligible & acceptable):
            return "HARD_FILTER_DROP"
        if eligible & acceptable:
            return "RERANK_NOT_SELECTED"
        if (short or eligible) and not (short & acceptable or eligible & acceptable):
            return "RERANK_POOL_MISS"
        if trace.get("failure_stage"):
            return str(trace["failure_stage"]).upper()
    candidates = _ids(debug.get("candidates") or [])
    if candidates & acceptable:
        return "LEGACY_RERANK_NOT_SELECTED" if not trace else "RERANK_NOT_SELECTED"
    if status == "NOT_FOUND" and not candidates:
        return "NO_CANDIDATES_OR_UNTRACED_FILTER"
    if candidates:
        return "RETRIEVAL_MISS_OR_MISSING_GOLD"
    return "UNKNOWN"


def technical_rejection_evidence(response: dict, acceptable: set[int]) -> list[dict]:
    """Explain which known-positive products were pruned (locally, never to LLM).

    Hard filter decisions are from catalog facts. Soft mismatches suggest a
    cause but do not on their own prove a hard constraint failure.
    """
    trace = (((response.get("debug") or {}).get("query_interpretation") or {})
             .get("retrieval_trace") or {})
    rows = (trace.get("technical_prefilter") or {}).get("rows") or []
    evidence = []
    for row in rows:
        if not (_ids([row]) & acceptable):
            continue
        checks = row.get("checks") or {}
        evidence.append({
            "ld_id":row.get("ld_id"),
            "wide_rrf_rank":row.get("original_rank"),
            "hard_eligible":row.get("hard_eligible"),
            "soft_conflicts":{field:description for field,description in checks.items()
                              if str(description).startswith("mismatch:")},
            "selected_by_prefilter":row.get("selected"),
        })
    return evidence


def classify(case: dict, response: dict) -> dict:
    acceptable = _ids(case.get("acceptable_ld_ids") or case.get("known_positive_ids") or [])
    found = predicted_ld_id(response)
    status = response.get("status", "UNKNOWN")
    if not acceptable:
        verdict = "NO_POSITIVE_LABEL"
    elif found in acceptable:
        verdict = "EXACT_PASS"
    elif allowed_sparse_refusal(case["query"], response):
        verdict = "INTENTIONAL_SPARSE_REFUSAL"
    elif status == "MATCHED":
        verdict = "OTHER_LD_REQUIRES_REVIEW"
    elif status == "NOT_FOUND":
        verdict = "NOT_FOUND_WITH_KNOWN_POSITIVE"
    else:
        verdict = "PIPELINE_ERROR"
    return {
        "id": case.get("id"),
        "query": case["query"],
        "split": case.get("split"),
        "status": status,
        "returned_ld_id": found,
        "known_positive_ids": sorted(acceptable),
        "verdict": verdict,
        "failure_stage": "SUCCESS" if verdict == "EXACT_PASS" else
                         "POLICY_REFUSAL" if verdict == "INTENTIONAL_SPARSE_REFUSAL" else
                         stage_of_failure(response, acceptable),
        "debug_reason": str((response.get("debug") or {}).get("reason") or ""),
        "gold_candidate_filter_evidence": technical_rejection_evidence(response, acceptable),
        "constraint_source": (response.get("debug") or {}).get("query_interpretation"),
    }


def evaluate(cases: list[dict], response_rows: list[dict]) -> dict:
    if len(cases) != len(response_rows):
        raise ValueError(f"Unequal query counts: {len(cases)} vs {len(response_rows)}")
    scored = []
    for case, response in zip(cases, response_rows, strict=True):
        if case["query"] != response.get("query"):
            raise ValueError("Order or text of queries differs; refusing a misleading evaluation")
        scored.append(classify(case, response))
    counts = Counter(row["verdict"] for row in scored)
    stages = Counter(row["failure_stage"] for row in scored)
    return {
        "n": len(scored),
        "exact_top1_known_positive": sum(row["verdict"] == "EXACT_PASS" for row in scored),
        "intentional_sparse_refusals": counts["INTENTIONAL_SPARSE_REFUSAL"],
        "other_ld_unreviewed": counts["OTHER_LD_REQUIRES_REVIEW"],
        "counts": dict(counts),
        "failure_stages": dict(stages),
        "rows": scored,
    }


def compare(old: dict, new: dict, *, frozen_guard: bool = False) -> dict:
    if old["n"] != new["n"] or [
        (x["id"], x["query"]) for x in old["rows"]
    ] != [
        (x["id"], x["query"]) for x in new["rows"]
    ]:
        raise ValueError("Cohort mismatch: cannot compare different queries")
    transitions = Counter()
    regressions = []
    gains = []
    for prev, curr in zip(old["rows"], new["rows"], strict=True):
        transitions[f'{prev["verdict"]} -> {curr["verdict"]}'] += 1
        if prev["verdict"] == "EXACT_PASS" and curr["verdict"] != "EXACT_PASS":
            regressions.append(curr["id"])
        if prev["verdict"] != "EXACT_PASS" and curr["verdict"] == "EXACT_PASS":
            gains.append(curr["id"])
    guarded = (new["exact_top1_known_positive"] >= old["exact_top1_known_positive"]
               and not regressions)
    return {
        "old_exact": old["exact_top1_known_positive"],
        "new_exact": new["exact_top1_known_positive"],
        "gain": new["exact_top1_known_positive"] - old["exact_top1_known_positive"],
        "improved_case_ids": gains,
        "regressed_case_ids": regressions,
        "transitions": dict(transitions),
        "frozen100_acceptable": guarded if frozen_guard else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True, type=Path,
                        help="JSON list of cases with query and known-positive IDs")
    parser.add_argument("--before", required=True, type=Path,
                        help="match_batch.py JSON list (with debug)")
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=Path(".tmp/regression_comparison.json"))
    parser.add_argument("--strict-frozen100", action="store_true")
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    before = evaluate(cases, json.loads(args.before.read_text(encoding="utf-8")))
    after = evaluate(cases, json.loads(args.after.read_text(encoding="utf-8")))
    verdict = compare(before, after, frozen_guard=args.strict_frozen100)
    result = {"baseline": before, "candidate": after, "comparison": verdict}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "baseline": {k: v for k,v in before.items() if k != "rows"},
        "candidate": {k: v for k,v in after.items() if k != "rows"},
        "comparison": {k: v for k,v in verdict.items() if k not in ("transitions", "improved_case_ids", "regressed_case_ids")},
        "local_report": str(args.out),
    },ensure_ascii=False,indent=2))
    if args.strict_frozen100 and not verdict["frozen100_acceptable"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
