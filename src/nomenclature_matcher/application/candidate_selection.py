from __future__ import annotations

from typing import Any

from ..domain.product import LDProduct
from ..models import SearchCandidate
from ..domain.constraints import (
    QueryConstraints,
    evaluate_product,
    technical_compatibility,
)


class CandidateSelectionService:
    """Deterministic compatibility gate and ranking for a retrieved pool."""

    @staticmethod
    def candidate_as_product(candidate: SearchCandidate) -> LDProduct:
        return LDProduct(
            id=candidate.ld_id,
            name=candidate.name,
            article=candidate.article,
            price=candidate.price,
            dn=candidate.dn,
            pn=candidate.pn,
            joining_type=candidate.joining_type,
            url=candidate.url,
            properties=candidate.properties or [],
        )

    def eligible_candidates(
        self,
        candidates: list[SearchCandidate],
        constraints: dict[str, Any],
    ) -> list[tuple[int, SearchCandidate]]:
        parsed = QueryConstraints.model_validate(constraints)
        return [
            (index, candidate)
            for index, candidate in enumerate(candidates, 1)
            if evaluate_product(self.candidate_as_product(candidate), parsed).matches
        ]

    def technical_prefilter_candidates(
        self,
        candidates: list[SearchCandidate],
        *,
        soft_constraints: dict[str, Any] | None,
        hard_constraints: dict[str, Any] | None,
        limit: int,
    ) -> tuple[list[SearchCandidate], dict[str, Any]]:
        """Apply hard facts, then rank by known soft compatibility and RRF order.

        Missing candidate attributes are neutral. If every candidate conflicts
        with explicit hard constraints, retain the legacy fallback pool for the
        reranker's hard-filter/second-chance decision.
        """
        if not candidates:
            return [], {
                "applied": True,
                "pool_size": 0,
                "hard_eligible_count": 0,
                "selected_ids": [],
                "rows": [],
            }

        parsed_soft = (
            QueryConstraints.model_validate(soft_constraints)
            if soft_constraints is not None
            else None
        )
        parsed_hard = (
            QueryConstraints.model_validate(hard_constraints)
            if hard_constraints is not None
            else None
        )

        rows: list[dict[str, Any]] = []
        hard_eligible: list[tuple[SearchCandidate, dict[str, Any]]] = []
        for original_rank, candidate in enumerate(candidates, 1):
            product = self.candidate_as_product(candidate)
            hard_decision = (
                evaluate_product(product, parsed_hard)
                if parsed_hard is not None
                else None
            )
            hard_ok = hard_decision.matches if hard_decision is not None else True
            compatibility = (
                technical_compatibility(product, parsed_soft)
                if parsed_soft is not None
                else {"matches": 0, "mismatches": 0, "unknown": 0, "checks": {}}
            )
            row = {
                "original_rank": original_rank,
                "ld_id": candidate.ld_id,
                "hard_eligible": hard_ok,
                "matches": compatibility["matches"],
                "mismatches": compatibility["mismatches"],
                "unknown": compatibility["unknown"],
                "checks": compatibility["checks"],
                "rrf_score": candidate.rrf_score,
            }
            rows.append(row)
            if hard_ok:
                hard_eligible.append((candidate, row))

        if not hard_eligible:
            selected = candidates[:limit]
            return selected, {
                "applied": True,
                "pool_size": len(candidates),
                "hard_eligible_count": 0,
                "selected_ids": [candidate.ld_id for candidate in selected],
                "rows": rows,
                "fallback": "no_hard_eligible_candidates",
            }

        ranked = sorted(
            hard_eligible,
            key=lambda item: (
                item[1]["mismatches"],
                -item[1]["matches"],
                item[1]["original_rank"],
            ),
        )
        selected = [candidate for candidate, _ in ranked[:limit]]
        selected_ids = {candidate.ld_id for candidate in selected}
        for row in rows:
            row["selected"] = row["ld_id"] in selected_ids

        return selected, {
            "applied": True,
            "pool_size": len(candidates),
            "hard_eligible_count": len(hard_eligible),
            "selected_ids": [candidate.ld_id for candidate in selected],
            "rows": rows,
        }
