"""Run comparable historical/current/candidate tender matcher probes.

Uses the exact Sept 9 baseline commit (pre-query-gate) for tender20 causal
comparison, and the previous business-demo commit for frozen100 promotion.
Calls the match_batch script in each isolated worktree; Qdrant is read-only.
Never sends any acceptable LD IDs to the model. GOLD stays under .tmp/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
from pathlib import Path

from compare_regression_outputs import compare, evaluate

ROOT = Path(__file__).resolve().parents[1]
HISTORIC_REF = "5768c4591c9a92cc3a9c33338a163b83a15d81d5"
MODERN_REF = "origin/codex/business-demo-oct16"


def git(*argv: str, cwd: Path = ROOT) -> str:
    proc = subprocess.run(["git", *argv],cwd=cwd,text=True,capture_output=True)
    if proc.returncode:
        raise RuntimeError(f"git {argv[0]} failed: {proc.stderr[-700:]}")
    return proc.stdout.strip()


def worktree(ref: str, directory: Path) -> tuple[Path, str]:
    path = directory.resolve()
    if not (path / ".git").exists():
        path.parent.mkdir(parents=True,exist_ok=True)
        git("worktree","add","--detach",str(path),ref)
    actual = git("rev-parse","HEAD",cwd=path)
    expected = git("rev-parse",ref)
    if actual != expected:
        raise ValueError(f"Worktree {path} at {actual[:10]}, expected {expected[:10]}. "
                         "Remove/recreate the test worktree; never replay against a stale commit.")
    return path, actual


def load_cases(cohort: str, historic_dir: Path) -> list[dict]:
    if cohort == "tender20":
        data = json.loads((historic_dir/"data/tender_queries_v1_harness_cases.json").read_text(encoding="utf-8"))
        cases = data["cases"]
        if len(cases) != 20:
            raise ValueError(f"Historical verified tender benchmark changed: {len(cases)} instead of 20")
        return [
            {"id":c["id"],"query":c["query"],"split":c["split"],
             "acceptable_ld_ids":c["known_positive_ids"]}
            for c in cases
        ]
    if cohort == "frozen100":
        # Existing evaluator contains the same frozen population as E08. Do NOT
        # use the old 120-case Sep9 harness here; those are different benchmarks.
        from eval_competitor_analogs import load_embedded_cases
        cases = random.Random(53).sample(load_embedded_cases(),100)
        return [{
            "id":hashlib.sha256(c["query"].encode("utf-8")).hexdigest()[:16],
            "query":c["query"],"split":"FROZEN100",
            "acceptable_ld_ids":c["acceptable_ld_ids"],
        } for c in cases]
    raise ValueError(f"Unknown cohort {cohort}")


def run_branch(name: str, checkout: Path, cases: list[dict], *, csv: Path,
               env: dict[str,str], out: Path) -> list[dict]:
    inputs = out.parent / f"{name}.queries.json"
    inputs.write_text(json.dumps([c["query"] for c in cases],ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    cmd = [sys.executable,str(checkout/"scripts/match_batch.py"),
           "--input",str(inputs),"--csv",str(csv)]
    proc = subprocess.run(cmd,cwd=checkout,env=env,text=True,capture_output=True)
    if proc.returncode:
        raise RuntimeError(f"{name} exit={proc.returncode}. Check local stderr: {proc.stderr[-1000:]}")
    try:
        payload = json.loads(proc.stdout)
    except ValueError as exc:
        raise RuntimeError(f"{name} runner did not emit a clean JSON array; check local stdout logs") from exc
    if not isinstance(payload,list) or len(payload) != len(cases):
        raise ValueError(f"{name} returned {len(payload) if isinstance(payload,list) else type(payload)} items, expected {len(cases)}")
    out.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return payload


def load_environment(filename: Path) -> dict[str,str]:
    from dotenv import dotenv_values
    if not filename.is_file():
        raise ValueError(f"--env-file does not exist: {filename}")
    env = os.environ.copy()
    env.update({key: value for key,value in dotenv_values(filename).items()
                if value is not None})
    needed = ["OPENAI_API_KEY","DEEPSEEK_API_KEY"]
    absent = [name for name in needed if not env.get(name)]
    if absent:
        raise ValueError(f"Missing secrets: {', '.join(absent)}; provide them through --env-file")
    env["MATCH_TRACE_DETAILED_ENABLED"] = "true"
    env["MATCH_TRACE_ENABLED"] = "true"
    return env


def run_comparison(cohort: str, *, historical_checkout: Path | None,
                   current_checkout: Path, candidate_checkout: Path,
                   catalog: Path, env: dict[str,str], output_dir: Path) -> dict:
    if cohort == "tender20" and historical_checkout is None:
        raise ValueError("Tender20 requires historical Sept9 checkout")
    cases=load_cases(cohort,historical_checkout or candidate_checkout)
    cohort_dir=output_dir/cohort
    cohort_dir.mkdir(parents=True,exist_ok=True)
    (cohort_dir/"cases.private.json").write_text(
        json.dumps(cases,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    print(f"Starting {cohort}: {len(cases)} questions; raw prompts only; no GOLD sent to matcher",flush=True)
    runs={}
    checkouts = ({"historic":historical_checkout,"current":current_checkout,"candidate":candidate_checkout}
                 if cohort=="tender20" else
                 {"current":current_checkout,"candidate":candidate_checkout})
    for name,checkout in checkouts.items():
        if checkout is None:
            continue
        result=run_branch(name,checkout,cases,csv=catalog,env=env,
                          out=cohort_dir/f"{name}.raw.private.json")
        runs[name]=evaluate(cases,result)
        print(f"{name}: exact-known-positive {runs[name]['exact_top1_known_positive']}/{len(cases)}, "
              f"sparse refusals {runs[name]['intentional_sparse_refusals']}",flush=True)

    comparisons = {
        "historic_vs_current": compare(runs["historic"],runs["current"])
        if "historic" in runs else None,
        "current_vs_candidate": compare(
            runs["current"],runs["candidate"],frozen_guard=cohort=="frozen100"),
    }
    result={"cohort":cohort,"runs":runs,"comparisons":comparisons}
    (cohort_dir/"report.private.json").write_text(
        json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"cohort":cohort,
                      "current_exact":runs["current"]["exact_top1_known_positive"],
                      "candidate_exact":runs["candidate"]["exact_top1_known_positive"],
                      "current_vs_candidate_gain":comparisons["current_vs_candidate"]["gain"],
                      "lost_previous_passes":len(comparisons["current_vs_candidate"]["regressed_case_ids"]),
                      "strict_frozen_gate":comparisons["current_vs_candidate"]["frozen100_acceptable"],
                      "local_report":str(cohort_dir/"report.private.json")},
                     ensure_ascii=False,indent=2),flush=True)
    return result


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cohort",choices=["tender20","frozen100","both"],default="tender20")
    p.add_argument("--csv",type=Path,required=True,help="Single shared LD catalog CSV for both runs")
    p.add_argument("--env-file",type=Path,required=True,help="One shared environment containing provider keys and Qdrant URL")
    p.add_argument("--historic-ref",default=HISTORIC_REF)
    p.add_argument("--current-ref",default=MODERN_REF)
    p.add_argument("--out",type=Path,default=Path(".tmp/evolution-ab"))
    p.add_argument("--run-live",action="store_true",help="Required: these runs incur embedding+LLM costs")
    args=p.parse_args()
    if not args.run_live:
        p.error("Pass --run-live to explicitly authorize API spend; no calls were made")
    catalog=args.csv.expanduser().resolve()
    if not catalog.is_file():
        p.error(f"Missing catalog CSV: {catalog}")
    env=load_environment(args.env_file.expanduser().resolve())
    out=args.out.expanduser().resolve()
    out.mkdir(parents=True,exist_ok=True)
    candidate_checkout=ROOT.resolve()
    current_checkout,current_sha=worktree(args.current_ref,out/"checkouts"/"current")
    historic_checkout,historic_sha=(worktree(args.historic_ref,out/"checkouts"/"historic")
                                   if args.cohort in ("tender20","both") else (None,None))
    candidate_sha=git("rev-parse","HEAD",cwd=candidate_checkout)
    environment_fingerprint = {
        # Intentionally avoid secret tokens.
        "qdrant_url":env.get("QDRANT_URL", "http://localhost:6333"),
        "qdrant_collection":env.get("QDRANT_COLLECTION_ALIAS", "steel_products_active"),
        "embedding_model":env.get("EMBEDDING_MODEL", "text-embedding-3-small"),
        "deepseek_model":env.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        "catalog_sha256":hashlib.sha256(catalog.read_bytes()).hexdigest(),
        "historic_ref":historic_sha,"current_ref":current_sha,"candidate_ref":candidate_sha,
    }
    (out/"environment_fingerprint.json").write_text(
        json.dumps(environment_fingerprint,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    reports=[]
    for cohort in (["tender20","frozen100"] if args.cohort=="both" else [args.cohort]):
        reports.append(run_comparison(cohort,historical_checkout=historic_checkout,
                     current_checkout=current_checkout,candidate_checkout=candidate_checkout,
                     catalog=catalog,env=env,output_dir=out))
    for report in reports:
        if report["cohort"]=="frozen100" and not report["comparisons"]["current_vs_candidate"]["frozen100_acceptable"]:
            raise SystemExit("REJECT: frozen100 Top-1 decreased or a previously passing case regressed")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
