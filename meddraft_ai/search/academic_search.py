import os
import json
import time
import random
import logging
import urllib.request
import urllib.parse
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from meddraft_ai.core.config import get_config

logger = logging.getLogger(__name__)

SCHOLARLY_AVAILABLE = False
try:
    from scholarly import scholarly, ProxyGenerator
    SCHOLARLY_AVAILABLE = True
except ImportError:
    pass

FINDPAPERS_AVAILABLE = False
try:
    import findpapers
    FINDPAPERS_AVAILABLE = True
except ImportError:
    pass

# ==============================================================================
# 1. PubMed API (NCBI E-utilities) - PRIMARY SOURCE
# ==============================================================================
def search_pubmed_api(query: str, limit: int = 10) -> str:
    """Search PubMed via NCBI E-utilities using NCBI_API_KEY."""
    try:
        config = get_config()
        ncbi_key = config.NCBI_API_KEY or os.getenv('NCBI_API_KEY', '')
        api_key_param = f"&api_key={ncbi_key}" if ncbi_key else ""

        quoted_query = urllib.parse.quote_plus(query)
        search_url = (
            f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            f"?db=pubmed&term={quoted_query}&retmode=json&retmax={limit}{api_key_param}"
        )

        req = urllib.request.Request(search_url, headers={
            'User-Agent': 'MedDraft_AI/1.0 (mailto:researcher@meddraft.ai)'
        })
        with urllib.request.urlopen(req, timeout=15) as response:
            res_data = json.loads(response.read().decode('utf-8'))

        id_list = res_data.get("esearchresult", {}).get("idlist", [])
        if not id_list:
            return json.dumps({"source": "PubMed", "query": query, "count": 0, "results": []}, indent=2, ensure_ascii=False)

        ids_str = ",".join(id_list)
        summary_url = (
            f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
            f"?db=pubmed&id={ids_str}&retmode=json{api_key_param}"
        )

        req2 = urllib.request.Request(summary_url, headers={
            'User-Agent': 'MedDraft_AI/1.0 (mailto:researcher@meddraft.ai)'
        })
        with urllib.request.urlopen(req2, timeout=15) as response2:
            sum_data = json.loads(response2.read().decode('utf-8'))

        results = []
        uid_results = sum_data.get("result", {})
        for uid in id_list:
            info = uid_results.get(uid, {})
            if info:
                title = info.get("title", "Unknown Title")
                pubdate = info.get("pubdate", "Unknown Date")
                source = info.get("source", "Unknown Journal")
                authors = [a.get("name", "") for a in info.get("authors", [])]
                doi = ""
                for articleid in info.get("articleids", []):
                    if articleid.get("idtype") == "doi":
                        doi = articleid.get("value", "")

                results.append({
                    "pmid": uid,
                    "title": title,
                    "authors": ", ".join(authors[:5]) + (" et al." if len(authors) > 5 else ""),
                    "journal": source,
                    "year": pubdate.split(" ")[0] if pubdate else "Unknown",
                    "doi": doi,
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{uid}/"
                })

        return json.dumps({
            "source": "PubMed", "query": query, "count": len(results), "results": results
        }, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"source": "PubMed", "query": query, "error": str(e), "count": 0, "results": []}, indent=2, ensure_ascii=False)


# ==============================================================================
# 2. ScienceDirect API (Elsevier) - PRIMARY SOURCE
# ==============================================================================
def search_sciencedirect_api(query: str, limit: int = 10) -> str:
    """Search ScienceDirect via Elsevier API using SCIENCEDIRECT_API_KEY."""
    try:
        config = get_config()
        api_key = config.SCIENCEDIRECT_API_KEY or os.getenv('SCIENCEDIRECT_API_KEY', '')
        if not api_key:
            return json.dumps({"source": "ScienceDirect", "query": query, "error": "SCIENCEDIRECT_API_KEY not configured", "count": 0, "results": []}, indent=2, ensure_ascii=False)

        quoted_query = urllib.parse.quote_plus(query)
        url = f"https://api.elsevier.com/content/search/sciencedirect?query={quoted_query}&count={limit}"

        req = urllib.request.Request(url, headers={
            'Accept': 'application/json', 'X-ELS-APIKey': api_key, 'User-Agent': 'MedDraft_AI/1.0'
        })
        with urllib.request.urlopen(req, timeout=20) as response:
            data = json.loads(response.read().decode('utf-8'))

        entries = data.get("search-results", {}).get("entry", [])
        results = []
        for entry in entries:
            authors_list = []
            for author in entry.get("authors", {}).get("author", []):
                if isinstance(author, dict):
                    name = author.get("given-name", "") + " " + author.get("surname", "")
                    authors_list.append(name.strip())
            doi = entry.get("doi", "")
            results.append({
                "title": entry.get("dc:title", "Unknown Title"),
                "authors": ", ".join(authors_list[:5]) + (" et al." if len(authors_list) > 5 else ""),
                "journal": entry.get("prism:publicationName", "Unknown Journal"),
                "year": entry.get("prism:coverDate", "")[:4] if entry.get("prism:coverDate") else "Unknown",
                "doi": doi,
                "url": f"https://doi.org/{doi}" if doi else next(
                    (lnk.get("@href", "") for lnk in entry.get("link", []) if isinstance(lnk, dict)),
                    "",
                ),
                "open_access": entry.get("openaccess", ""),
            })

        return json.dumps({"source": "ScienceDirect", "query": query, "count": len(results), "results": results}, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"source": "ScienceDirect", "query": query, "error": str(e), "count": 0, "results": []}, indent=2, ensure_ascii=False)


# ==============================================================================
# 3. Google Scholar (scholarly / stealth browser fallback) - PRIMARY SOURCE
# ==============================================================================
def search_google_scholar_api(query: str, limit: int = 10, use_proxy: bool = True) -> str:
    """Search Google Scholar using the scholarly library with optional proxy."""
    if not SCHOLARLY_AVAILABLE:
        return json.dumps({"source": "Google Scholar", "query": query, "error": "scholarly library not installed.", "count": 0, "results": []}, indent=2, ensure_ascii=False)
    try:
        if use_proxy:
            try:
                pg = ProxyGenerator()
                pg.FreeProxies()
                scholarly.use_proxy(pg)
            except Exception:
                pass
        scholarly.settings.set_lang("en")
        results = []
        search_query = scholarly.search_pubs(query)
        for i, result in enumerate(search_query):
            if i >= limit:
                break
            bib = result.get('bib', {})
            results.append({
                "title": bib.get('title', ''),
                "authors": ', '.join(bib.get('author', [])),
                "year": bib.get('pub_year', ''),
                "venue": bib.get('venue', ''),
                "abstract": (bib.get('abstract', '') or '')[:500],
                "citations": result.get('num_citations', 0),
                "url": result.get('pub_url', ''),
                "eprint_url": result.get('eprint_url', ''),
            })
            time.sleep(random.uniform(2, 4))
        return json.dumps({"source": "Google Scholar", "query": query, "count": len(results), "results": results}, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"source": "Google Scholar", "query": query, "error": str(e), "count": 0, "results": []}, indent=2, ensure_ascii=False)


# ==============================================================================
# 4. CrossRef REST API
# ==============================================================================
def search_crossref_api(query: str, limit: int = 10) -> str:
    """Search CrossRef REST API directly."""
    try:
        quoted_query = urllib.parse.quote_plus(query)
        url = f"https://api.crossref.org/works?query={quoted_query}&rows={limit}"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'MedDraft_AI/1.0 (mailto:researcher@meddraft.ai)'
        })
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        items = data.get("message", {}).get("items", [])
        results = []
        for item in items:
            title = " ".join(item.get("title", []))
            authors_raw = item.get("author") or []
            authors = []
            for a in authors_raw:
                given = a.get("given", "")
                family = a.get("family", "")
                authors.append(f"{given} {family}".strip())
            
            journal = " ".join(item.get("container-title", []))
            published = item.get("published-print", {}) or item.get("published-online", {})
            date_parts = published.get("date-parts", [["Unknown"]])
            year = str(date_parts[0][0]) if date_parts and date_parts[0] else "Unknown"

            results.append({
                "title": title,
                "authors": ", ".join(authors[:5]) + (" et al." if len(authors) > 5 else ""),
                "journal": journal,
                "year": year,
                "doi": item.get("DOI", ""),
                "url": item.get("URL", f"https://doi.org/{item.get('DOI', '')}")
            })

        return json.dumps({"source": "CrossRef", "query": query, "count": len(results), "results": results}, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"source": "CrossRef", "query": query, "error": str(e), "count": 0, "results": []}, indent=2, ensure_ascii=False)


# ==============================================================================
# 5. Semantic Scholar Graph API
# ==============================================================================
def search_semantic_scholar_api(query: str, limit: int = 10) -> str:
    """Search Semantic Scholar via Graph API."""
    try:
        quoted_query = urllib.parse.quote_plus(query)
        fields = "title,authors,year,venue,externalIds,abstract,citationCount,isOpenAccess,openAccessPdf"
        url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={quoted_query}&limit={limit}&fields={fields}"
        req = urllib.request.Request(url, headers={'User-Agent': 'MedDraft_AI/1.0'})
        
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        papers = data.get("data", [])
        results = []
        for p in papers:
            authors = [a.get("name", "") for a in p.get("authors", [])]
            ext_ids = p.get("externalIds", {})
            doi = ext_ids.get("DOI", "")
            pmid = ext_ids.get("PubMed", "")
            oa_info = p.get("openAccessPdf", {}) or {}
            
            results.append({
                "title": p.get("title", ""),
                "authors": ", ".join(authors[:5]) + (" et al." if len(authors) > 5 else ""),
                "year": str(p.get("year", "")),
                "journal": p.get("venue", ""),
                "doi": doi,
                "pmid": pmid,
                "abstract": (p.get("abstract") or "")[:500],
                "citations": p.get("citationCount", 0),
                "is_oa": p.get("isOpenAccess", False),
                "pdf_url": oa_info.get("url"),
                "url": f"https://www.semanticscholar.org/paper/{p.get('paperId')}"
            })
        return json.dumps({"source": "Semantic Scholar", "query": query, "count": len(results), "results": results}, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"source": "Semantic Scholar", "query": query, "error": str(e), "count": 0, "results": []}, indent=2, ensure_ascii=False)


# ==============================================================================
# 6. Europe PMC REST API
# ==============================================================================
def search_europe_pmc(query: str, limit: int = 10) -> str:
    """Search Europe PMC REST API."""
    try:
        quoted_query = urllib.parse.quote_plus(query)
        url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={quoted_query}&format=json&pageSize={limit}"
        req = urllib.request.Request(url, headers={'User-Agent': 'MedDraft_AI/1.0'})
        
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        items = data.get("resultList", {}).get("result", [])
        results = []
        for item in items:
            results.append({
                "title": item.get("title", ""),
                "authors": item.get("authorString", ""),
                "journal": item.get("journalTitle", ""),
                "year": str(item.get("pubYear", "")),
                "doi": item.get("doi", ""),
                "pmid": item.get("pmid", ""),
                "pmcid": item.get("pmcid", ""),
                "abstract": (item.get("abstractText") or "")[:500],
                "is_oa": item.get("isOpenAccess") == "Y",
                "url": f"https://europepmc.org/article/{item.get('source', 'MED')}/{item.get('id')}"
            })
        return json.dumps({"source": "Europe PMC", "query": query, "count": len(results), "results": results}, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"source": "Europe PMC", "query": query, "error": str(e), "count": 0, "results": []}, indent=2, ensure_ascii=False)


# ==============================================================================
# 7. ClinicalTrials.gov v2 API
# ==============================================================================
def search_clinicaltrials_gov(query: str, limit: int = 10) -> str:
    """Search ClinicalTrials.gov v2 API."""
    try:
        quoted_query = urllib.parse.quote_plus(query)
        url = f"https://clinicaltrials.gov/api/v2/studies?query.term={quoted_query}&pageSize={limit}"
        req = urllib.request.Request(url, headers={'User-Agent': 'MedDraft_AI/1.0'})
        
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        studies = data.get("studies", [])
        results = []
        for s in studies:
            protocol = s.get("protocolSection", {})
            id_module = protocol.get("identificationModule", {})
            status_module = protocol.get("statusModule", {})
            nct_id = id_module.get("nctId", "")
            title = id_module.get("briefTitle", "")
            
            results.append({
                "nct_id": nct_id,
                "title": title,
                "status": status_module.get("overallStatus", ""),
                "year": status_module.get("startDateStruct", {}).get("date", "")[:4],
                "journal": "ClinicalTrials.gov",
                "url": f"https://clinicaltrials.gov/study/{nct_id}"
            })
        return json.dumps({"source": "ClinicalTrials.gov", "query": query, "count": len(results), "results": results}, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"source": "ClinicalTrials.gov", "query": query, "error": str(e), "count": 0, "results": []}, indent=2, ensure_ascii=False)


# ==============================================================================
# 8. DOAJ (Directory of Open Access Journals)
# ==============================================================================
def search_doaj(query: str, limit: int = 10) -> str:
    """Search DOAJ articles API."""
    try:
        quoted_query = urllib.parse.quote_plus(query)
        url = f"https://doaj.org/api/search/articles/{quoted_query}?pageSize={limit}"
        req = urllib.request.Request(url, headers={'User-Agent': 'MedDraft_AI/1.0'})
        
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        items = data.get("results", [])
        results = []
        for item in items:
            bib = item.get("bibjson", {})
            authors = [a.get("name", "") for a in bib.get("author", [])]
            doi = ""
            for identifier in bib.get("identifier", []):
                if identifier.get("type") == "doi":
                    doi = identifier.get("id", "")

            results.append({
                "title": bib.get("title", ""),
                "authors": ", ".join(authors[:5]),
                "journal": bib.get("journal", {}).get("title", ""),
                "year": bib.get("year", ""),
                "doi": doi,
                "abstract": (bib.get("abstract") or "")[:500],
                "is_oa": True,
                "url": f"https://doi.org/{doi}" if doi else ""
            })
        return json.dumps({"source": "DOAJ", "query": query, "count": len(results), "results": results}, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"source": "DOAJ", "query": query, "error": str(e), "count": 0, "results": []}, indent=2, ensure_ascii=False)


# ==============================================================================
# Aggregated Search with Priority Execution
# ==============================================================================
def search_all_sources(query: str, limit_per_source: int = 5) -> str:
    """
    Search academic databases in parallel with priority ordering:
    Primary: PubMed, ScienceDirect, Google Scholar
    Secondary: CrossRef, Semantic Scholar, Europe PMC
    Tertiary: ClinicalTrials.gov, DOAJ
    """
    primary_sources = {
        "PubMed": lambda: search_pubmed_api(query, limit_per_source),
        "ScienceDirect": lambda: search_sciencedirect_api(query, limit_per_source),
        "Google Scholar": lambda: search_google_scholar_api(query, limit_per_source),
    }

    secondary_sources = {
        "CrossRef": lambda: search_crossref_api(query, limit_per_source),
        "Semantic Scholar": lambda: search_semantic_scholar_api(query, limit_per_source),
        "Europe PMC": lambda: search_europe_pmc(query, limit_per_source),
        "ClinicalTrials.gov": lambda: search_clinicaltrials_gov(query, limit_per_source),
        "DOAJ": lambda: search_doaj(query, limit_per_source)
    }

    combined = {"query": query, "sources": {}}

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(func): name for name, func in {**primary_sources, **secondary_sources}.items()}
        for future in as_completed(futures):
            source_name = futures[future]
            try:
                raw = future.result()
                combined["sources"][source_name] = json.loads(raw)
            except Exception as e:
                combined["sources"][source_name] = {"error": str(e), "count": 0, "results": []}

    return json.dumps(combined, indent=2, ensure_ascii=False)
