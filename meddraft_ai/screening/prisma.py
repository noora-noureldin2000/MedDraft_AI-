class PrismaFlow:
    """Computes screening stats and generates PRISMA 2020 compliant flowcharts in ASCII and Mermaid.js format."""

    @staticmethod
    def categorize_exclusions(records: list[dict], level: str = "fulltext") -> dict[str, int]:
        """Groups exclusions by reasons."""
        categories = {}
        for r in records:
            verdict = r.get(level, {}).get("verdict")
            if verdict == "EXCLUDE":
                reason = r.get(level, {}).get("reason", "Other reasons")
                # Clean and group common reasons
                reason_clean = "Other reasons"
                reason_lower = reason.lower()
                
                if "not retrieved" in reason_lower or "missing fulltext" in reason_lower or "full-text not found" in reason_lower:
                    # This is handled separately under "Reports not retrieved"
                    continue
                elif "population" in reason_lower or "wrong population" in reason_lower or "wrong cohort" in reason_lower:
                    reason_clean = "Wrong study population"
                elif "intervention" in reason_lower or "wrong intervention" in reason_lower:
                    reason_clean = "Wrong intervention evaluated"
                elif "comparator" in reason_lower or "wrong comparator" in reason_lower:
                    reason_clean = "Wrong comparator group"
                elif "outcome" in reason_lower or "wrong outcome" in reason_lower:
                    reason_clean = "Wrong outcomes measured"
                elif "study design" in reason_lower or "wrong design" in reason_lower or "not an rct" in reason_lower:
                    reason_clean = "Ineligible study design"
                elif "animal" in reason_lower or "in vitro" in reason_lower:
                    reason_clean = "Non-human / in vitro study"
                else:
                    # Truncate long reasons at a sentence boundary, not a colon.
                    # Splitting on ':' would turn 'EXCLUDE: narrative review' into just 'EXCLUDE'.
                    first_period = reason.find(".")
                    if 0 < first_period <= 40:
                        reason_clean = reason[:first_period].strip()
                    else:
                        reason_clean = reason[:40].strip()
                    if reason_clean and not reason_clean.endswith("..."):
                        reason_clean += "..."
                        
                categories[reason_clean] = categories.get(reason_clean, 0) + 1
        return categories

    @classmethod
    def generate_flowchart(cls, original_count: int, duplicate_count: int, screened_records: list[dict]) -> dict:
        """Computes all PRISMA steps and returns reports in text and mermaid format."""
        
        # 1. Identification
        records_identified = original_count
        duplicates_removed = duplicate_count
        
        # 2. Screening (Title/Abstract)
        records_screened = len(screened_records)
        
        # Excludes at abstract level
        abstract_excluded_records = [r for r in screened_records if r.get("screening", {}).get("verdict") == "EXCLUDE"]
        abstract_excluded = len(abstract_excluded_records)
        
        # 3. Eligibility (Full Text)
        reports_sought = records_screened - abstract_excluded
        
        # Reports not retrieved (failed to load full text)
        reports_not_retrieved_records = [
            r for r in screened_records 
            if r.get("fulltext", {}).get("verdict") == "EXCLUDE" 
            and ("not retrieved" in r.get("fulltext", {}).get("reason", "").lower() 
                 or "missing fulltext" in r.get("fulltext", {}).get("reason", "").lower())
        ]
        reports_not_retrieved = len(reports_not_retrieved_records)
        
        # Reports assessed for eligibility
        reports_assessed = reports_sought - reports_not_retrieved
        
        # Full text excluded with reasons
        fulltext_excluded_records = [
            r for r in screened_records 
            if r.get("fulltext", {}).get("verdict") == "EXCLUDE" 
            and not ("not retrieved" in r.get("fulltext", {}).get("reason", "").lower() 
                     or "missing fulltext" in r.get("fulltext", {}).get("reason", "").lower())
        ]
        reports_excluded = len(fulltext_excluded_records)
        
        # Categorized reasons
        excluded_reasons = cls.categorize_exclusions(screened_records, "fulltext")
        
        # 4. Included
        studies_included = sum(1 for r in screened_records if r.get("fulltext", {}).get("verdict") == "INCLUDE")
        
        # Generate ASCII Flowchart
        ascii_flow = (
            f"┌────────────────────────────────────────────────────────┐\n"
            f"│                      IDENTIFICATION                    │\n"
            f"├────────────────────────────────────────────────────────┤\n"
            f"│  Records identified from databases (n = {records_identified:<5})       │\n"
            f"│  Duplicates removed (n = {duplicates_removed:<5})                    │\n"
            f"└───────────────────────────┬────────────────────────────┘\n"
            f"                            │\n"
            f"┌───────────────────────────▼────────────────────────────┐\n"
            f"│                        SCREENING                       │\n"
            f"├────────────────────────────────────────────────────────┤\n"
            f"│  Records screened (n = {records_screened:<5})                         │\n"
            f"│  Records excluded (n = {abstract_excluded:<5})                         │\n"
            f"└───────────────────────────┬────────────────────────────┘\n"
            f"                            │\n"
            f"┌───────────────────────────▼────────────────────────────┐\n"
            f"│                       ELIGIBILITY                      │\n"
            f"├────────────────────────────────────────────────────────┤\n"
            f"│  Reports sought for retrieval (n = {reports_sought:<5})             │\n"
            f"│  Reports not retrieved (n = {reports_not_retrieved:<5})                    │\n"
            f"│  Reports assessed for eligibility (n = {reports_assessed:<5})          │\n"
            f"│  Reports excluded (n = {reports_excluded:<5})                         │\n"
        )
        
        for reason, count in excluded_reasons.items():
            ascii_flow += f"│    - {reason[:35]:<35} (n = {count:<3})     │\n"
            
        ascii_flow += (
            f"└───────────────────────────┬────────────────────────────┘\n"
            f"                            │\n"
            f"┌───────────────────────────▼────────────────────────────┐\n"
            f"│                        INCLUDED                        │\n"
            f"├────────────────────────────────────────────────────────┤\n"
            f"│  Studies included in systematic review (n = {studies_included:<5})     │\n"
            f"└────────────────────────────────────────────────────────┘\n"
        )
        
        # Generate Mermaid Diagram
        reasons_list = [f"&nbsp;&nbsp;- {r}: {c}" for r, c in excluded_reasons.items()]
        reasons_str = "<br/>".join(reasons_list)
        if reasons_str:
            reasons_str = "<br/>Exclusion reasons:<br/>" + reasons_str
            
        mermaid_flow = (
            "graph TD\n"
            "    subgraph Identification\n"
            f"        ID1[\"Records identified from databases<br/>(n = {records_identified})\"]\n"
            f"        ID2[\"Duplicates removed<br/>(n = {duplicates_removed})\"]\n"
            "    end\n\n"
            "    subgraph Screening\n"
            f"        SC1[\"Records screened (Title/Abstract)<br/>(n = {records_screened})\"]\n"
            f"        SC2[\"Records excluded<br/>(n = {abstract_excluded})\"]\n"
            "    end\n\n"
            "    subgraph Eligibility\n"
            f"        EL1[\"Reports sought for retrieval<br/>(n = {reports_sought})\"]\n"
            f"        EL2[\"Reports not retrieved<br/>(n = {reports_not_retrieved})\"]\n"
            f"        EL3[\"Reports assessed for eligibility<br/>(n = {reports_assessed})\"]\n"
            f"        EL4[\"Reports excluded (n = {reports_excluded}){reasons_str}\"]\n"
            "    end\n\n"
            "    subgraph Included\n"
            f"        IN1[\"Studies included in systematic review<br/>(n = {studies_included})\"]\n"
            "    end\n\n"
            "    ID1 --> ID2\n"
            "    ID2 --> SC1\n"
            "    SC1 --> SC2\n"
            "    SC1 --> EL1\n"
            "    EL1 --> EL2\n"
            "    EL1 --> EL3\n"
            "    EL3 --> EL4\n"
            "    EL3 --> IN1\n"
        )
        
        return {
            "ascii": ascii_flow,
            "mermaid": mermaid_flow,
            "stats": {
                "identified": records_identified,
                "duplicates_removed": duplicates_removed,
                "screened": records_screened,
                "abstract_excluded": abstract_excluded,
                "sought": reports_sought,
                "not_retrieved": reports_not_retrieved,
                "assessed": reports_assessed,
                "excluded": reports_excluded,
                "included": studies_included
            }
        }
