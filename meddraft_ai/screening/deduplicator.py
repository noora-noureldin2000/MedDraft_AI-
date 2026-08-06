import re
from difflib import SequenceMatcher
from rich.console import Console
from rich.table import Table

console = Console()

class StudyDeduplicator:
    """Performs manual and automated de-duplication of clinical study reference records."""

    @staticmethod
    def clean_title(title: str) -> str:
        """Normalizes titles by lowering casing, stripping punctuation, spacing, and brackets."""
        if not title:
            return ""
        # Lowers case
        title = title.lower()
        # Removes punctuation, brackets, parentheses
        title = re.sub(r"[^\w\s]", "", title)
        # Normalizes spaces
        title = re.sub(r"\s+", " ", title)
        return title.strip()

    @staticmethod
    def clean_doi(doi: str) -> str:
        """Normalizes DOIs by converting to lowercase and stripping resolver URLs."""
        if not doi:
            return ""
        doi = doi.strip().lower()
        doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
        return doi

    @classmethod
    def are_titles_similar(cls, title1: str, title2: str, threshold: float = 0.85) -> tuple[bool, float]:
        """Calculates fuzzy similarity between normalized titles."""
        c1 = cls.clean_title(title1)
        c2 = cls.clean_title(title2)
        if not c1 or not c2:
            return False, 0.0
        
        # Quick check for exact matches after cleaning
        if c1 == c2:
            return True, 1.0
            
        ratio = SequenceMatcher(None, c1, c2).ratio()
        return ratio >= threshold, ratio

    @classmethod
    def merge_records(cls, rec1: dict, rec2: dict) -> dict:
        """Merges two records, keeping the most complete metadata (abstracts, DOIs, etc.)."""
        # Create a new merged dict based on rec1
        merged = dict(rec1)
        
        # Prioritize abstract
        if not merged.get("abstract") and rec2.get("abstract"):
            merged["abstract"] = rec2["abstract"]
            
        # Prioritize DOI
        if not merged.get("doi") and rec2.get("doi"):
            merged["doi"] = rec2["doi"]
            
        # Prioritize Year
        if not merged.get("year") and rec2.get("year"):
            merged["year"] = rec2["year"]
            
        # Prioritize Journal
        if not merged.get("journal") and rec2.get("journal"):
            merged["journal"] = rec2["journal"]
            
        # Merge authors (keep unique authors case-insensitively)
        authors1 = merged.get("authors") or []
        authors2 = rec2.get("authors") or []
        all_authors = list(authors1)
        lower_authors = {a.lower() for a in all_authors}
        for a in authors2:
            if a.lower() not in lower_authors:
                all_authors.append(a)
                lower_authors.add(a.lower())
        merged["authors"] = all_authors
        
        # Merge keywords
        kw1 = merged.get("keywords") or []
        kw2 = rec2.get("keywords") or []
        all_kw = list(kw1)
        lower_kw = {k.lower() for k in all_kw}
        for k in kw2:
            if k.lower() not in lower_kw:
                all_kw.append(k)
                lower_kw.add(k.lower())
        merged["keywords"] = all_kw
        
        return merged

    @classmethod
    def deduplicate(cls, records: list[dict], threshold: float = 0.85, interactive: bool = False) -> tuple[list[dict], int]:
        """Runs the de-duplication loop. Returns (deduplicated_list, number_of_duplicates_removed)."""
        deduped = []
        removed_count = 0
        processed_indices = set()
        
        for i, rec in enumerate(records):
            if i in processed_indices:
                continue
                
            current_record = dict(rec)
            duplicates_found = []
            
            # Compare current record against all subsequent records
            for j in range(i + 1, len(records)):
                if j in processed_indices:
                    continue
                
                other = records[j]
                match = False
                match_type = ""
                similarity = 1.0
                
                # Check 1: DOI Match (Highest Confidence)
                doi1 = cls.clean_doi(current_record.get("doi"))
                doi2 = cls.clean_doi(other.get("doi"))
                if doi1 and doi2 and doi1 == doi2:
                    match = True
                    match_type = "DOI Match"
                
                # Check 2: Fuzzy Title Match
                if not match:
                    similar, similarity = cls.are_titles_similar(
                        current_record.get("title"), other.get("title"), threshold
                    )
                    if similar:
                        match = True
                        match_type = f"Fuzzy Title Similarity ({similarity:.2f})"
                
                # Check 3: Short Title + Year + Author Match (additional safety)
                if not match and current_record.get("year") == other.get("year"):
                    # If years match and first author matches and titles are reasonably similar
                    auths1 = current_record.get("authors") or []
                    auths2 = other.get("authors") or []
                    if auths1 and auths2:
                        first_auth1 = auths1[0].split(",")[0].split(" ")[0].lower()
                        first_auth2 = auths2[0].split(",")[0].split(" ")[0].lower()
                        if first_auth1 == first_auth2:
                            # calculate looser title similarity
                            similar, similarity = cls.are_titles_similar(
                                current_record.get("title"), other.get("title"), 0.70
                            )
                            if similar:
                                match = True
                                match_type = f"Author-Year + Title Similarity ({similarity:.2f})"
                
                if match:
                    duplicates_found.append((j, other, match_type))
            
            if duplicates_found:
                for idx, duplicate, match_reason in duplicates_found:
                    if interactive:
                        # Present duplicates to the user
                        console.print(f"\n[bold yellow]⚠️ Duplication Alert: {match_reason}[/bold yellow]")
                        table = Table(title="Select the record to keep (or 'merge' to combine them)")
                        table.add_column("Field", style="bold cyan")
                        table.add_column("Record A (Current)", style="green")
                        table.add_column("Record B (Duplicate)", style="yellow")
                        
                        table.add_row("Title", current_record.get("title"), duplicate.get("title"))
                        table.add_row("Authors", "; ".join(current_record.get("authors") or []), "; ".join(duplicate.get("authors") or []))
                        table.add_row("Year", current_record.get("year"), duplicate.get("year"))
                        table.add_row("Journal", current_record.get("journal"), duplicate.get("journal"))
                        table.add_row("DOI", current_record.get("doi"), duplicate.get("doi"))
                        table.add_row("Has Abstract", "Yes" if current_record.get("abstract") else "No", "Yes" if duplicate.get("abstract") else "No")
                        
                        console.print(table)
                        
                        choice = ""
                        while choice not in ("a", "b", "m", "s"):
                            choice = input("Keep Record [a], Duplicate [b], [m]erge both, or [s]kip (keep both separated)? ").strip().lower()
                        
                        if choice == "a":
                            # Keep current_record as is, mark duplicate as processed (discard duplicate)
                            processed_indices.add(idx)
                            removed_count += 1
                        elif choice == "b":
                            # Replace current_record with duplicate, discard duplicate
                            current_record = dict(duplicate)
                            processed_indices.add(idx)
                            removed_count += 1
                        elif choice == "m":
                            # Merge duplicates
                            current_record = cls.merge_records(current_record, duplicate)
                            processed_indices.add(idx)
                            removed_count += 1
                        else:
                            # Skip (do not mark as duplicate, keep both)
                            pass
                    else:
                        # Automated merge (default choice)
                        current_record = cls.merge_records(current_record, duplicate)
                        processed_indices.add(idx)
                        removed_count += 1
                        
            deduped.append(current_record)
            
        return deduped, removed_count
