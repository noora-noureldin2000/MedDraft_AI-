import json
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from meddraft_ai.core.llm_client import LLMClient
from .deduplicator import StudyDeduplicator

console = Console()

class HTMLTextExtractor(HTMLParser):
    """Simple HTML parser to extract clean text from web pages."""
    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.ignore_tags = {"script", "style", "head", "title", "meta", "link", "nav", "footer"}
        self.current_tag = ""

    def handle_starttag(self, tag, attrs):
        self.current_tag = tag.lower()

    def handle_endtag(self, tag):
        self.current_tag = ""

    def handle_data(self, data):
        if self.current_tag not in self.ignore_tags:
            text = data.strip()
            if text:
                self.text_parts.append(text)

    def get_text(self) -> str:
        return "\n".join(self.text_parts)


class FullTextScreener:
    """Orchestrates Full-Text screening against inclusion/exclusion criteria using local files or URLs."""

    def __init__(self, pico_criteria: str):
        self.pico_criteria = pico_criteria
        self.llm = LLMClient()

    def get_system_prompt(self) -> str:
        return (
            "You are a senior clinical research editor conducting a systematic review.\n"
            "Your task is to evaluate the FULL TEXT of a study against the provided PICO criteria and Eligibility Guidelines to make a final inclusion decision.\n\n"
            "CRITICAL RULES:\n"
            "1. Read the full text carefully. Verify if the population, intervention, comparator, outcomes, and study design strictly match your criteria.\n"
            "2. If the study does not meet the criteria, you must EXCLUDE it and state the EXACT primary reason (e.g., 'Wrong comparator: used placebo instead of active drug', 'Wrong study design: retrospective cohort instead of RCT').\n"
            "3. If it matches all criteria, mark it as 'INCLUDE'.\n\n"
            "You MUST respond ONLY with a JSON object matching this schema:\n"
            "{\n"
            "  \"verdict\": \"INCLUDE\" | \"EXCLUDE\",\n"
            "  \"reason\": \"A detailed explanation of why the study was included or excluded, citing specific details from the text.\"\n"
            "}"
        )

    def format_user_prompt(self, record: dict, full_text: str) -> str:
        # Truncate full text if too long for LLM safety (e.g. ~40,000 characters ≈ 10,000 tokens)
        truncated_text = full_text
        if len(full_text) > 40000:
            truncated_text = full_text[:40000] + "\n... [FULL TEXT TRUNCATED FOR LENGTH] ..."
            
        return (
            f"=== ELIGIBILITY CRITERIA (PICO) ===\n"
            f"{self.pico_criteria}\n\n"
            f"=== STUDY METADATA ===\n"
            f"Title: {record.get('title')}\n"
            f"Authors: {', '.join(record.get('authors') or ['Unknown'])}\n\n"
            f"=== STUDY FULL TEXT ===\n"
            f"{truncated_text}\n\n"
            f"Evaluate the full text of this study. Respond ONLY with the JSON object."
        )

    def fetch_url_text(self, url: str) -> str:
        """Fetches and parses text from a full-text URL.

        Uses the anti-detection scraper first (crawl4ai / SeleniumBase UC),
        then falls back to standard urllib.
        """
        try:
            from agent_core.web_scraper import scrape_url_sync
            result = scrape_url_sync(url)
            if result.success and result.raw_text:
                return result.raw_text
        except Exception:
            pass

        # Legacy fallback
        try:
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                html = response.read().decode('utf-8', errors='ignore')
            extractor = HTMLTextExtractor()
            extractor.feed(html)
            return extractor.get_text()
        except Exception as e:
            raise RuntimeError(f"Failed to fetch content from URL {url}: {e}")

    def find_local_file(self, title: str, fulltext_dir: Path) -> Path:
        """Finds a local markdown file that matches the study title using fuzzy title matching."""
        if not fulltext_dir or not fulltext_dir.exists():
            return None
            
        # Normalise study title
        normalized_title = StudyDeduplicator.clean_title(title)
        
        # Scan all .md files
        for path in fulltext_dir.glob("**/*.md"):
            # Check if filename is similar
            file_title = StudyDeduplicator.clean_title(path.stem)
            if file_title and normalized_title in file_title or file_title in normalized_title:
                return path
            
            # Read first few lines of file to see if Title is written there
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                # Look for first header or line
                lines = [l.strip() for l in content.splitlines() if l.strip()][:5]
                for line in lines:
                    line_clean = StudyDeduplicator.clean_title(line)
                    if line_clean and (normalized_title in line_clean or line_clean in normalized_title):
                        return path
            except Exception:
                pass
                
        return None

    def screen_fulltext(self, records: list[dict], fulltext_dir: Path = None, session_file: Path = None, max_workers: int = 3) -> list[dict]:
        """Screens study full-texts. Filters out EXCLUDE records first."""
        # We only screen studies that were NOT excluded in abstract screening
        eligible_records = [r for r in records if r.get("screening", {}).get("verdict") in ("INCLUDE", "UNSURE")]
        excluded_records = [r for r in records if r.get("screening", {}).get("verdict") == "EXCLUDE"]
        
        results = list(excluded_records) # Excludes are carried over directly
        screened_results = []
        start_index = 0
        
        if session_file and session_file.exists():
            try:
                with open(session_file, "r", encoding="utf-8") as f:
                    saved_data = json.load(f)
                screened_results = saved_data.get("results", [])
                start_index = len(screened_results)
                console.print(f"[bold green]Resuming full-text screening from index {start_index}...[/bold green]")
            except Exception as e:
                console.print(f"[red]Error loading session file, starting fresh: {e}[/red]")
                screened_results = []

        records_to_process = eligible_records[start_index:]
        
        if not records_to_process:
            # Combine already screened results with excluded ones
            final_list = results + screened_results
            return final_list
            
        console.print(f"Starting full-text screening of [bold cyan]{len(records_to_process)}[/bold cyan] eligible articles...")
        
        # Prepare list of tasks
        tasks = []
        skipped_count = 0
        
        # Locate text for each record
        for rec in records_to_process:
            title = rec.get("title")
            full_text = ""
            
            # Step 1: Try local directory
            if fulltext_dir:
                file_path = self.find_local_file(title, fulltext_dir)
                if file_path:
                    try:
                        full_text = file_path.read_text(encoding="utf-8", errors="ignore")
                        console.print(f"[green]Found local full text for:[/green] '{title[:50]}...'")
                    except Exception as e:
                        console.print(f"[red]Error reading local file {file_path}: {e}[/red]")
            
            # Step 2: Try URL access if no local text found
            url = rec.get("doi") or ""
            # If it's a DOI, construct doi.org URL
            if url and not url.startswith("http"):
                url = f"https://doi.org/{url}"
            
            if not full_text and url.startswith("http"):
                try:
                    console.print(f"[yellow]Attempting to fetch full text from URL:[/yellow] {url}")
                    full_text = self.fetch_url_text(url)
                except Exception as e:
                    console.print(f"[red]Could not fetch full text from URL: {e}[/red]")
            
            if not full_text:
                # If we cannot locate full text, we must mark it as UNSURE / Missing Fulltext
                console.print(f"[red]Skipped:[/red] Full-text not found for '{title[:50]}...'")
                screened_rec = dict(rec)
                screened_rec["fulltext"] = {
                    "verdict": "EXCLUDE",
                    "reason": "Exclusion: Full-text report not retrieved."
                }
                screened_results.append(screened_rec)
                skipped_count += 1
                continue
                
            sys_p = self.get_system_prompt()
            usr_p = self.format_user_prompt(rec, full_text)
            tasks.append((rec, sys_p, usr_p))
            
        if not tasks:
            final_list = results + screened_results
            return final_list

        # Screen remaining articles using LLM
        batch_size = max_workers
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task_id = progress.add_task("[cyan]Screening full text...", total=len(tasks))
            
            for b_idx in range(0, len(tasks), batch_size):
                batch_tasks = tasks[b_idx:b_idx + batch_size]
                
                # Format arguments for llm.run_parallel_screening
                llm_tasks = [(sys_p, usr_p, True) for _, sys_p, usr_p in batch_tasks]
                batch_outputs = self.llm.run_parallel_screening(llm_tasks, max_workers=max_workers)
                
                for idx, out in enumerate(batch_outputs):
                    rec = batch_tasks[idx][0]
                    try:
                        decision = json.loads(out)
                        verdict = decision.get("verdict", "EXCLUDE").upper()
                        reason = decision.get("reason", "No reason provided.")
                    except Exception:
                        verdict = "EXCLUDE"
                        reason = f"Exclusion: Error parsing LLM response. Raw: {out[:100]}"
                        
                    screened_rec = dict(rec)
                    screened_rec["fulltext"] = {
                        "verdict": verdict,
                        "reason": reason
                    }
                    screened_results.append(screened_rec)
                    
                # Save progress
                if session_file:
                    try:
                        with open(session_file, "w", encoding="utf-8") as f:
                            json.dump({"results": screened_results}, f, ensure_ascii=False, indent=2)
                    except Exception:
                        pass
                        
                progress.update(task_id, advance=len(batch_tasks))
                
        final_list = results + screened_results
        
        # Summary
        final_includes = sum(1 for r in final_list if r.get("fulltext", {}).get("verdict") == "INCLUDE")
        final_excludes = sum(1 for r in final_list if r.get("fulltext", {}).get("verdict") == "EXCLUDE")
        
        console.print("[bold green]Full-text screening completed![/bold green]")
        console.print(f"📊 [bold]Full-Text Screening Summary:[/bold] Included: [green]{final_includes}[/green] | Excluded: [red]{final_excludes}[/red] (including {skipped_count} missing full-text).")
        
        return final_list
