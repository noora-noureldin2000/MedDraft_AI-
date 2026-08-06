import csv
import re
from pathlib import Path

class RISCSVParser:
    """Robust parser for RIS and CSV study references that extracts abstracts and key metadata."""
    
    @staticmethod
    def normalize_whitespace(text: str) -> str:
        return re.sub(r"\s+", " ", text or "").strip()

    @classmethod
    def parse_ris(cls, content: str) -> list[dict]:
        """Parses RIS content into list of normalized dictionaries."""
        # Split references by End of Reference tag (ER - ...)
        parts = re.split(r"\nER\s*-\s*\n|\nER\s*-\s*$", content)
        results = []
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            lines = [line.strip() for line in part.splitlines() if line.strip()]
            record = {
                "title": None,
                "abstract": None,
                "authors": [],
                "year": None,
                "journal": None,
                "doi": None,
                "keywords": []
            }
            
            # Map values from tags
            for line in lines:
                if "-" not in line:
                    continue
                tag, val = line.split("-", 1)
                tag = tag.strip().upper()
                val = val.strip()
                if not val:
                    continue
                
                if tag in ("TI", "T1"):
                    record["title"] = cls.normalize_whitespace(val)
                elif tag in ("AB", "N2"):
                    # Concatenate if abstract spans multiple AB lines or exists in N2
                    if record["abstract"]:
                        record["abstract"] += " " + cls.normalize_whitespace(val)
                    else:
                        record["abstract"] = cls.normalize_whitespace(val)
                elif tag == "AU":
                    record["authors"].append(cls.normalize_whitespace(val))
                elif tag in ("PY", "Y1"):
                    # Extract 4-digit year
                    year_match = re.search(r"\b(19|20)\d{2}\b", val)
                    if year_match:
                        record["year"] = year_match.group(0)
                elif tag in ("JO", "JF", "T2", "JA"):
                    record["journal"] = cls.normalize_whitespace(val)
                elif tag in ("DO", "L3"):
                    record["doi"] = val.strip().lower()
                elif tag == "KW":
                    record["keywords"].append(cls.normalize_whitespace(val))
            
            # Add to results if we have at least a title
            if record["title"]:
                results.append(record)
                
        return results

    @classmethod
    def parse_csv(cls, content: str) -> list[dict]:
        """Parses CSV content using python standard csv reader."""
        lines = content.splitlines()
        if not lines:
            return []
            
        reader = csv.DictReader(lines)
        results = []
        
        # Helper to find column matching a key case-insensitively
        def get_col_val(row, key_patterns):
            for k in row.keys():
                k_clean = k.lower().strip()
                for pat in key_patterns:
                    if pat in k_clean:
                        return row[k]
            return None

        for row in reader:
            title = get_col_val(row, ["title", "headline", "article"])
            abstract = get_col_val(row, ["abstract", "summary", "notes", "scope", "synopsis"])
            authors = get_col_val(row, ["author", "creator"])
            year = get_col_val(row, ["year", "date", "py"])
            journal = get_col_val(row, ["journal", "source", "publication", "jo", "venue"])
            doi = get_col_val(row, ["doi", "digital object identifier"])
            keywords = get_col_val(row, ["keyword", "kw"])
            
            if not title:
                continue
                
            authors_list = []
            if authors:
                # split authors by common delimiters
                authors_list = [cls.normalize_whitespace(a) for a in re.split(r";|,| and ", authors) if a.strip()]
                
            keywords_list = []
            if keywords:
                keywords_list = [cls.normalize_whitespace(k) for k in re.split(r";|,|\|", keywords) if k.strip()]
                
            year_val = None
            if year:
                year_match = re.search(r"\b(19|20)\d{2}\b", str(year))
                if year_match:
                    year_val = year_match.group(0)
            
            results.append({
                "title": cls.normalize_whitespace(title),
                "abstract": cls.normalize_whitespace(abstract) if abstract else None,
                "authors": authors_list,
                "year": year_val,
                "journal": cls.normalize_whitespace(journal) if journal else None,
                "doi": doi.strip().lower() if doi else None,
                "keywords": keywords_list
            })
            
        return results

    @classmethod
    def load_file(cls, file_path: Path) -> list[dict]:
        """Loads and parses RIS or CSV file based on extension."""
        suffix = file_path.suffix.lower()
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        if suffix == ".ris":
            return cls.parse_ris(content)
        elif suffix == ".csv":
            return cls.parse_csv(content)
        else:
            raise ValueError("Unsupported file format. Use .ris or .csv")

    @classmethod
    def export_ris(cls, records: list[dict]) -> str:
        """Converts records back into RIS format string."""
        lines = []
        for r in records:
            lines.append("TY  - JOUR")
            if r.get("title"):
                lines.append(f"TI  - {r['title']}")
            for auth in r.get("authors", []):
                lines.append(f"AU  - {auth}")
            if r.get("journal"):
                lines.append(f"JO  - {r['journal']}")
            if r.get("year"):
                lines.append(f"PY  - {r['year']}")
            if r.get("doi"):
                lines.append(f"DO  - {r['doi']}")
            if r.get("abstract"):
                # Split abstract into multiple lines if very long to fit some software limits
                abs_val = r["abstract"]
                lines.append(f"N2  - {abs_val}")
            for kw in r.get("keywords", []):
                lines.append(f"KW  - {kw}")
            lines.append("ER  -")
            lines.append("") # empty line after ER
        return "\n".join(lines)

    @classmethod
    def export_csv(cls, records: list[dict], output_path: Path):
        """Converts records back to a CSV file."""
        if not records:
            return
        
        headers = ["title", "authors", "year", "journal", "doi", "abstract", "keywords"]
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for r in records:
                writer.writerow([
                    r.get("title") or "",
                    "; ".join(r.get("authors") or []),
                    r.get("year") or "",
                    r.get("journal") or "",
                    r.get("doi") or "",
                    r.get("abstract") or "",
                    "; ".join(r.get("keywords") or [])
                ])
