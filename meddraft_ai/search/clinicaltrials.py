"""ClinicalTrials.gov v2 client (medical-clinicaltrials skill — code layer).

Extends the repo's existing free-text ``search_clinicaltrials_gov`` helper with
the skill's two missing capabilities:

  * Advanced filtered search — condition / intervention / phase / status
    (``ctg_search_studies`` / ``ctg_search_by_condition`` /
    ``ctg_search_by_intervention``).
  * Full study retrieval by NCT ID (``ctg_get_study``).

Public API, no key required. All functions are offline-safe: network failures
return ``{"success": False, ...}`` instead of raising.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any, Optional

logger = logging.getLogger(__name__)

CTG_API = "https://clinicaltrials.gov/api/v2/studies"
USER_AGENT = "MedDraft_AI/1.0 (mailto:researcher@meddraft.ai)"

# Compact default field set — keeps responses small and evidence-ready.
DEFAULT_FIELDS = "|".join([
    "NCTId",
    "BriefTitle",
    "OverallStatus",
    "Phase",
    "StudyType",
    "Condition",
    "InterventionName",
    "StartDate",
    "CompletionDate",
])

_PHASE_ALIASES = {
    "early phase 1": "EARLY_PHASE1", "early-phase-1": "EARLY_PHASE1", "phase 0": "EARLY_PHASE1",
    "phase 1": "PHASE1", "phase i": "PHASE1",
    "phase 2": "PHASE2", "phase ii": "PHASE2",
    "phase 3": "PHASE3", "phase iii": "PHASE3",
    "phase 4": "PHASE4", "phase iv": "PHASE4",
    "not applicable": "NA", "n/a": "NA",
}

_STATUS_ALIASES = {
    "recruiting": "RECRUITING",
    "active not recruiting": "ACTIVE_NOT_RECRUITING",
    "active, not recruiting": "ACTIVE_NOT_RECRUITING",
    "completed": "COMPLETED",
    "not yet recruiting": "NOT_YET_RECRUITING",
    "suspended": "SUSPENDED",
    "terminated": "TERMINATED",
    "withdrawn": "WITHDRAWN",
    "enrolling by invitation": "ENROLLING_BY_INVITATION",
}

# Topic signals that justify an automatic ClinicalTrials.gov lookup in Phase 1.
TRIAL_TOPIC_SIGNALS = [
    "trial", "trials", "phase 1", "phase 2", "phase 3", "phase 4",
    "randomized", "randomised", "placebo", "recruiting", "intervention",
    "drug efficacy", "treatment outcome", "clinical outcome", "nct",
]


def normalize_phase(raw: str) -> str:
    """Map user-friendly phase text to a ClinicalTrials.gov filter value."""
    if not raw:
        return ""
    key = raw.strip().lower().replace("_", " ")
    if raw.strip().upper().replace(" ", "") in (
        "EARLY_PHASE1", "PHASE1", "PHASE2", "PHASE3", "PHASE4", "NA",
        "EARLYPHASE1",
    ):
        return raw.strip().upper().replace(" ", "")
    return _PHASE_ALIASES.get(key, "")


def normalize_status(raw: str) -> str:
    """Map user-friendly status text to a ClinicalTrials.gov filter value."""
    if not raw:
        return ""
    key = raw.strip().lower().replace("_", " ")
    candidate = raw.strip().upper().replace(" ", "_")
    if candidate in _STATUS_ALIASES.values():
        return candidate
    return _STATUS_ALIASES.get(key, "")


def should_include_trials(topic: str) -> bool:
    """Heuristic gate for the automatic Phase 1 trials lookup."""
    if not topic:
        return False
    lowered = topic.lower()
    if re.search(r"\bnct\d{6,8}\b", lowered):
        return True
    return any(signal in lowered for signal in TRIAL_TOPIC_SIGNALS)


def _http_get_json(url: str, timeout: int = 20) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _normalize_study(study: dict[str, Any]) -> dict[str, Any]:
    proto = study.get("protocolSection", {}) if isinstance(study, dict) else {}
    ident = proto.get("identificationModule", {})
    status = proto.get("statusModule", {})
    cond_mod = proto.get("conditionsModule", {})
    arms = proto.get("armsInterventionsModule", {})
    desc = proto.get("descriptionModule", {})
    phases = status.get("phases") or ([status["phase"]] if status.get("phase") else [])
    nct_id = ident.get("nctId", "")
    return {
        "nct_id": nct_id,
        "title": ident.get("briefTitle", "") or ident.get("officialTitle", ""),
        "status": status.get("overallStatus", ""),
        "phase": ", ".join(p for p in phases if p),
        "study_type": proto.get("designModule", {}).get("studyType", ""),
        "conditions": cond_mod.get("conditions", []),
        "interventions": [
            f"{i.get('type', '')}: {i.get('name', '')}".strip(": ")
            for i in arms.get("interventions", [])
        ],
        "start_date": (status.get("startDateStruct") or {}).get("date", ""),
        "completion_date": (status.get("completionDateStruct") or {}).get("date", ""),
        "summary": (desc.get("briefSummary") or "")[:1200],
        "url": f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else "",
        "source": "ClinicalTrials.gov",
    }


def search_studies(
    condition: str = "",
    intervention: str = "",
    phase: str = "",
    status: str = "",
    term: str = "",
    limit: int = 10,
) -> dict[str, Any]:
    """Filtered trial search (``ctg_search_studies``).

    Any combination of filters may be given; all are optional.
    """
    params: dict[str, str] = {
        "format": "json",
        "pageSize": str(max(1, min(limit, 50))),
        "fields": DEFAULT_FIELDS,
    }
    if condition:
        params["query.cond"] = condition
    if intervention:
        params["query.intr"] = intervention
    if term:
        params["query.term"] = term
    norm_phase = normalize_phase(phase)
    if phase and not norm_phase:
        return {"success": False, "error": f"Unknown phase filter: {phase!r}. Use e.g. 'Phase 3'.", "count": 0, "results": []}
    if norm_phase:
        params["filter.phase"] = norm_phase
    norm_status = normalize_status(status)
    if status and not norm_status:
        return {"success": False, "error": f"Unknown status filter: {status!r}. Use e.g. 'Recruiting'.", "count": 0, "results": []}
    if norm_status:
        params["filter.overallStatus"] = norm_status

    url = f"{CTG_API}?{urllib.parse.urlencode(params)}"
    try:
        data = _http_get_json(url)
    except Exception as exc:
        logger.warning("ClinicalTrials.gov search failed: %s", exc)
        return {"success": False, "error": str(exc), "count": 0, "results": []}
    studies = data.get("studies", [])
    results = [_normalize_study(s) for s in studies]
    return {"success": True, "count": len(results), "total": data.get("totalCount", len(results)), "results": results}


def search_by_condition(condition: str, limit: int = 10, **filters: Any) -> dict[str, Any]:
    """Search trials by disease/condition (``ctg_search_by_condition``)."""
    return search_studies(condition=condition, limit=limit, **filters)


def search_by_intervention(intervention: str, limit: int = 10, **filters: Any) -> dict[str, Any]:
    """Search trials by treatment/intervention (``ctg_search_by_intervention``)."""
    return search_studies(intervention=intervention, limit=limit, **filters)


_NCT_RE = re.compile(r"^NCT\d{6,8}$", re.IGNORECASE)


def get_study(nct_id: str) -> dict[str, Any]:
    """Full study record by NCT ID (``ctg_get_study``)."""
    raw = (nct_id or "").strip()
    if not _NCT_RE.match(raw):
        return {"success": False, "error": f"Invalid NCT ID: {nct_id!r}. Expected e.g. 'NCT04368728'.", "study": {}}
    url = f"{CTG_API}/{raw.upper()}"
    try:
        data = _http_get_json(url)
    except Exception as exc:
        logger.warning("ClinicalTrials.gov fetch failed for %s: %s", raw, exc)
        return {"success": False, "error": str(exc), "study": {}}
    study = _normalize_study(data)
    proto = data.get("protocolSection", {})
    outcomes = proto.get("outcomesModule", {})
    elig = proto.get("eligibilityModule", {})
    sponsor_mod = proto.get("sponsorCollaboratorsModule", {})
    contacts = proto.get("contactsLocationsModule", {})
    lead = sponsor_mod.get("leadSponsor", {})
    study.update({
        "primary_outcomes": [
            o.get("measure", "") for o in outcomes.get("primaryOutcomes", [])
        ],
        "secondary_outcomes": [
            o.get("measure", "") for o in outcomes.get("secondaryOutcomes", [])
        ],
        "eligibility": (elig.get("eligibilityCriteria") or "")[:2000],
        "minimum_age": elig.get("minimumAge", ""),
        "maximum_age": elig.get("maximumAge", ""),
        "sex": elig.get("sex", ""),
        "lead_sponsor": lead.get("name", ""),
        "locations": [
            {
                "facility": loc.get("facility", ""),
                "city": loc.get("city", ""),
                "country": loc.get("country", ""),
                "status": loc.get("status", ""),
            }
            for loc in (contacts.get("locations") or [])[:10]
        ],
    })
    return {"success": True, "study": study}


def get_study_metadata() -> dict[str, Any]:
    """Available filter vocabularies (``ctg_get_study_metadata``)."""
    return {
        "success": True,
        "phases": ["EARLY_PHASE1", "PHASE1", "PHASE2", "PHASE3", "PHASE4", "NA"],
        "statuses": sorted(set(_STATUS_ALIASES.values())),
        "filter_params": ["query.cond", "query.intr", "query.term", "filter.phase", "filter.overallStatus", "pageSize"],
    }
