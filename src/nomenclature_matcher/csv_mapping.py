"""Opt-in offline competitor -> LD mapping backend.

Mappings are candidate evidence, not independent product catalog or GOLD.
No similarity-only auto-accept: an exact source article or complete source name is
required. Explicit product constraints are enforced on BOTH sides.
"""
from __future__ import annotations

import csv
import hashlib
import re
from collections import defaultdict
from pathlib import Path


_DN = re.compile(r"(?<!\w)(?:ду|дн|dn|dy|du)\s*[-:]?\s*(\d{1,4})(?!\d)", re.I)
_PN = re.compile(r"(?<!\w)(?:ру|pn)\s*[-:]?\s*(\d+(?:[.,]\d+)?)\s*(мпа|mpa)?", re.I)
_LD_ID = re.compile(r"/products/(\d+)--")
_ARTICLE_PART = re.compile(r"[0-9a-zа-яё]+(?:[./_\-][0-9a-zа-яё]+)*", re.I)


def _text(value):
    return " ".join(str(value or "").casefold().replace("ё", "е").split())


def _number(value):
    try:
        return float(str(value or "").replace(",", "."))
    except ValueError:
        return None


def _identity(value):
    return re.sub(r"[^0-9a-zа-я]", "", _text(value))


def _codes(query):
    tokens = _ARTICLE_PART.findall(_text(query))
    result = set()
    for i in range(len(tokens)):
        for n in range(1, min(4, len(tokens)-i)+1):
            code = _identity(" ".join(tokens[i:i+n]))
            if len(code) >= 5 and (any(x.isdigit() for x in code)):
                result.add(code)
    return result


def _connection(query):
    value = _text(query)
    parts = []
    for regex, kind in ((r"штуцер", "штуцерное"), (r"межфланц", "межфланцевое"),
                        (r"фланц|фланец|ф/ф", "фланцевое"), (r"привар|под\s*сварку", "приварное"),
                        (r"резьб|муфт", "резьбовое")):
        if re.search(regex, value):
            parts.append(kind)
    return set(parts)


def _control(query):
    v = _text(query)
    if "электропривод" in v:
        return "электропривод"
    if "редуктор" in v:
        return "редуктор"
    if re.search(r"ручн|рычаг|бабочк", v):
        return "ручное"
    return None


def _medium(query):
    v = _text(query)
    if re.search(r"(?<!\w)газ(?:а|овый|овая)?(?!\w)", v):
        return "газ"
    if re.search(r"(?<!\w)(?:вода|воды|жидкость|теплоноситель)(?!\w)", v):
        return "жидкость"
    return None


def _thread(query):
    v = _text(query)
    if re.search(r"(?:вн|вр)\s*[/\-]\s*(?:нр|нар)", v) or re.search(r"внутрен\w*\s*/\s*наружн", v):
        return "внутренняя/наружная"
    if re.search(r"(?:нр|нар)\s*[/\-]\s*(?:вр|вн)", v):
        return "наружная/внутренняя"
    if re.search(r"(?:вр|вн)\s*[/\-]\s*(?:вр|вн)", v):
        return "внутренняя"
    if re.search(r"(?:нр|нар)\s*[/\-]\s*(?:нр|нар)", v):
        return "наружная"
    return None


def _facts(row, prefix):
    if prefix == "c":
        return dict(dn=_number(row.get("c_dn")), pn=_number(row.get("c_pn")),
                    connection="резьбовое", thread=_text(row.get("c_thread_type")),
                    control=_control(row.get("c_name")), medium=_medium(row.get("c_name")),
                    material="латунь")
    if prefix == "bf":
        return dict(dn=_number(row.get("steel_dn")), pn=_number(row.get("steel_pn")),
                    connection=_text(row.get("steel_connection")), thread=None,
                    control=_text(row.get("steel_control")), medium=None,
                    material=_text(row.get("steel_material")))
    return dict(dn=_number(row.get("steel_dn")), pn=_number(row.get("steel_pn_bar")),
                connection=_text(row.get("steel_connection")), thread=None,
                control=_text(row.get("steel_control")), medium=_text(row.get("steel_medium")),
                material=_text(row.get("steel_body_material")))


def _compatible(query, src):
    dm = _DN.findall(query)
    if dm:
        if len(set(dm)) > 1 or src["dn"] is None or int(src["dn"]) != int(dm[0]):
            return False
    pm = _PN.findall(query)
    if pm:
        if len(set(pm)) > 1:
            return False
        v, unit = pm[0]
        pn = _number(v) * (10 if unit else 1)
        if src["pn"] is None or src["pn"] < pn:
            return False
    cn = _connection(query)
    if cn and not any(s in src["connection"] for s in cn):
        return False
    ctrl = _control(query)
    if ctrl:
        actual = src["control"]
        if ctrl == "ручное":
            if not (any(x in actual for x in ("ручн", "рычаг", "бабочк"))):
                return False
        elif ctrl == "редуктор":
            if "редуктор" not in actual:
                return False
        elif "электропривод" not in actual:
            return False
    med = _medium(query)
    if med and med != src["medium"]:
        return False
    thread = _thread(query)
    if thread and thread != src["thread"]:
        return False
    if "09г2с" in _text(query) and "09г2с" not in src["material"]:
        return False
    if "12х18н10т" in _text(query) and "12х18н10т" not in src["material"]:
        return False
    return True


def _valid_mapped_pair(item):
    """A source/target pair must not contradict its explicit technical fields."""
    source, target = item["source_facts"], item["target_facts"]
    if source["dn"] is None or target["dn"] is None or int(source["dn"]) != int(target["dn"]):
        return False
    if source["pn"] is None or target["pn"] is None or target["pn"] + 1e-9 < source["pn"]:
        return False
    left, right = source["connection"], target["connection"]
    if left and right and not (
        left == right or left in right or right in left
    ):
        return False
    if source["medium"] and target["medium"] and source["medium"] != target["medium"]:
        return False
    if source["thread"] and target["thread"] and source["thread"] != target["thread"]:
        return False
    # Unknown optional facts are not proof of equivalence, but a known conflict is fatal.
    return True


class CsvMappingIndex:
    """Read three files, index source identities, reject fuzzy-only matches."""
    FILES = ("competitor_ld_mapping.csv", "butterfly_mapping_results.csv", "mapping_results.csv")

    def __init__(self, directory):
        self.root = Path(directory)
        self.by_article = defaultdict(list)
        self.by_name = defaultdict(list)
        self.rows_by_file = {}
        self._load()

    def _load(self):
        for filename in self.FILES:
            path = self.root / filename
            if not path.is_file():
                raise FileNotFoundError(f"Missing CSV mapping: {path}")
            with path.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle, delimiter=";" if filename.startswith("butterfly") else ",")
                rows = 0
                for r in reader:
                    rows += 1
                    if filename.startswith("competitor"):
                        article, source_name = r["competitor_article"], r["c_name"]
                        ld_article, ld_name, url = r["ld_article"], r["name"], r.get("url")
                        src = _facts(r,"c")
                        ld_dn, ld_pn, joining = r["dn"],r["pn"],"резьбовое"
                        target_medium, target_control = None, _control(ld_name)
                        target_thread = _text(r.get("thread_type"))
                        target_material = "латунь"
                    elif filename.startswith("butterfly"):
                        article, source_name = r["steel_marking"], r["steel_marking"]
                        ld_article = ld_name = r["ld_marking"]
                        url = ""
                        src = _facts(r,"bf")
                        ld_dn, ld_pn, joining = r["ld_dn"],r["ld_pn"],r["ld_connection"]
                        target_medium = None
                        target_control = _text(r.get("ld_control"))
                        target_thread = None
                        target_material = _text(r.get("ld_material"))
                    else:
                        article, source_name = r["steel_article"], r["steel_name"]
                        ld_article, ld_name, url = r["ld_article"],r["ld_name"],r["ld_url"]
                        src = _facts(r,"steel")
                        ld_dn, ld_pn, joining = r["ld_dn"],r["ld_pn_mpa"],r["ld_connection"]
                        target_medium = _text(r.get("ld_medium"))
                        target_control = _text(r.get("ld_control"))
                        target_thread = None
                        target_material = _text(ld_name)
                    if not article or not ld_article or not source_name:
                        continue
                    item = {"source_file":filename,"source_article":article,
                            "source_name":source_name,"ld_article":ld_article,
                            "ld_name":ld_name,"ld_url":url or "", "ld_dn":_number(ld_dn),
                            "ld_pn":_number(ld_pn),"ld_connection":joining,
                            "source_facts":src,
                            "target_facts":dict(dn=_number(ld_dn),pn=_number(ld_pn),
                                connection=_text(joining),thread=target_thread,
                                control=target_control,medium=target_medium,
                                material=target_material)}
                    self.by_name[_text(source_name)].append(item)
                    code = _identity(article)
                    if len(code)>=5 and any(c.isdigit() for c in code):
                        self.by_article[code].append(item)
                self.rows_by_file[filename] = rows

    def identity_for(self, source):
        """Recover exact indexed article from original tender line for UI corrections."""
        candidates = sorted(
            (key for key in _codes(source) if key in self.by_article),
            key=len, reverse=True,
        )
        if candidates:
            return candidates[0]
        compact = _identity(source)
        candidates = [
            code for code in self.by_article
            if len(code) >= 12 and code in compact
        ]
        return max(candidates, key=len) if candidates else None

    def search(self, query, limit=10):
        normalized = _text(query)
        if not normalized:
            return []
        exact_name = self.by_name.get(normalized, [])
        if exact_name:
            matches = exact_name
            evidence = "exact_name"
        else:
            candidates=[]
            for key in _codes(query):
                candidates.extend(self.by_article.get(key, []))
            # Some valid product markings include parentheses and many segments.
            # Do not downgrade these to partial/family tokens.
            if not candidates:
                compact_query = _identity(query)
                for code, mapped in self.by_article.items():
                    if len(code) >= 12 and code in compact_query:
                        candidates.extend(mapped)
            matches = candidates
            evidence = "exact_article"
        accepted={}
        for item in matches:
            if not (_valid_mapped_pair(item)
                    and _compatible(query,item["source_facts"])
                    and _compatible(query,item["target_facts"])):
                continue
            # Precomputed mapping rows are not verification of special executions.
            source_name = _text(item["source_name"])
            ld_name = _text(item["ld_name"])
            if "p235gh" in item["source_facts"]["material"]:
                continue  # different material standard: needs engineering review
            if "регулирующ" in source_name and "регулирующ" not in ld_name:
                continue
            if "стандартнопроход" in source_name and "полнопроход" in ld_name:
                continue
            if "полнопроход" in source_name and "стандартнопроход" in ld_name:
                continue
            key=(item["ld_article"],item["ld_name"])
            if key not in accepted:
                accepted[key] = {**item,"evidence": evidence}
        return sorted(accepted.values(),key=lambda x:(x["source_file"],x["ld_article"],x["ld_name"]))[:limit]


class CsvMappingMatcher:
    """Adapter for production.match_products, without Qdrant/OpenAI/DeepSeek."""
    def __init__(self, settings):
        self.settings = settings
        self.index = CsvMappingIndex(settings.csv_mapping_dir)

    def match_one_hybrid_with_rerank(self, query):
        from .models import MatchResult, SearchCandidate, SelectedMatch
        from .product_safety import missing_required_valve_fields, missing_required_flange_fields
        from .query_signals import (
            explicit_dn_from_query, explicit_pn_mpa_from_query,
            explicit_joining_type_from_query, explicit_thread_type_from_query,
            explicit_working_medium_from_query,
        )
        from .query_constraints import canonical_product_type, canonical_material
        query = " ".join(query.split())
        missing = [*missing_required_valve_fields(query), *missing_required_flange_fields(query)]
        if missing:
            return MatchResult(
                query=query, status="INSUFFICIENT_PARAMETERS",
                reason="INSUFFICIENT_PARAMETERS: " + ", ".join(missing),
                query_interpretation={"csv_backend": True, "missing_fields": missing},
            )
        facts = {
            "product_type": canonical_product_type(query),
            "dn": explicit_dn_from_query(query),
            "pn_min_mpa": explicit_pn_mpa_from_query(query),
            "joining_type": explicit_joining_type_from_query(query),
            "thread_type": explicit_thread_type_from_query(query),
            "working_medium": explicit_working_medium_from_query(query),
            "body_material": canonical_material(query),
        }
        facts = {k: v for k, v in facts.items() if v not in (None, "other")}
        hits=self.index.search(query,limit=10)
        # Catalog-backed facts from CSV are hints, not user-explicit hard gates.
        if hits:
            from .query_constraints import canonical_control, canonical_joining_type, canonical_material
            observed = hits[0]["source_facts"]
            inferred = {
                "product_type": canonical_product_type(hits[0]["source_name"]),
                "dn": int(observed["dn"]) if observed["dn"] is not None else None,
                "pn_min_mpa": observed["pn"] / 10 if observed["pn"] is not None else None,
                "joining_type": canonical_joining_type(observed["connection"]),
                "body_material": canonical_material(observed["material"]),
                "control": canonical_control(observed["control"]),
            }
            inferred = {k: v for k, v in inferred.items() if v not in (None, "other")}
        else:
            inferred = {}
        candidates=[]
        selected=[]
        for i,item in enumerate(hits,1):
            url=item["ld_url"]
            m=_LD_ID.search(url)
            ld_id=int(m.group(1)) if m else int(hashlib.sha256(item["ld_article"].encode()).hexdigest()[:12],16)
            candidate=SearchCandidate(
                ld_id=ld_id,name=item["ld_name"],article=item["ld_article"],
                score=1.0, dn=item["ld_dn"],pn=item["ld_pn"],
                joining_type=item["ld_connection"],url=url or None,
                retrieval_sources=["csv_mapping:"+item["source_file"]])
            candidates.append(candidate)
            if i == 1:
                selected.append(SelectedMatch(
                    candidate_id=i, article=candidate.article, name=candidate.name,
                    llm_confidence=None,
                    reason="Кандидат по артикулу/маппингу; требуется проверка",
                    ld_id=ld_id, dn=candidate.dn, pn=candidate.pn,
                    joining_type=candidate.joining_type, url=candidate.url,
                ))
        return MatchResult(query=query,status="MATCHED" if candidates else "NOT_FOUND",
            score=1.0 if candidates else None,ld_product=candidates[0] if candidates else None,
            candidates=candidates,selected=selected,
            reason=("CSV_MAPPING_MULTIPLE_ALTERNATIVES" if len(candidates)>1
                    else "CSV_MAPPING_EXACT" if candidates else "CSV_MAPPING_NO_VERIFIED_IDENTITY"),
            query_interpretation={
                "csv_backend": True,
                "csv_sources": self.index.rows_by_file,
                "mapping_source": hits[0]["source_file"] if hits else None,
                "constraints": {**inferred, **facts},
                "hard_constraints": facts,
                "multiple_alternatives_need_review": len(candidates) > 1,
            })
