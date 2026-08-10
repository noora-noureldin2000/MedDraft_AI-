import json
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from meddraft_ai.core.llm_client import LLMClient

console = Console()

class AbstractScreener:
    """Orchestrates Title and Abstract screening against user-defined PICO parameters."""

    def __init__(self, pico_criteria: str):
        self.pico_criteria = pico_criteria
        self.llm = LLMClient()

    def get_system_prompt(self) -> str:
        return (
            "You are a rigorous clinical research screener conducting a systematic review.\n"
            "Your task is to evaluate the Title and Abstract of a study against the provided PICO (Population, Intervention, Comparator, Outcome, Study Design) criteria and Inclusion/Exclusion guidelines.\n\n"
            "CRITICAL RULES:\n"
            "1. Be objective and strictly follow the criteria. Do not make assumptions beyond what is stated in the abstract.\n"
            "2. If an abstract lacks information needed to confirm an exclusion criterion, err on the side of caution and mark it as 'INCLUDE' or 'UNSURE' so it can be evaluated in full-text screening.\n"
            "3. If the study clearly violates any exclusion criteria or fails to match inclusion criteria, mark it as 'EXCLUDE'.\n\n"
            "You MUST respond ONLY with a JSON object matching this schema:\n"
            "{\n"
            "  \"verdict\": \"INCLUDE\" | \"EXCLUDE\" | \"UNSURE\",\n"
            "  \"reason\": \"A concise, clear 1-2 sentence explanation of your decision referencing the specific criteria matched or violated.\"\n"
            "}"
        )

    def format_user_prompt(self, record: dict) -> str:
        return (
            f"=== ELIGIBILITY CRITERIA (PICO) ===\n"
            f"{self.pico_criteria}\n\n"
            f"=== STUDY TO EVALUATE ===\n"
            f"Title: {record.get('title')}\n"
            f"Journal: {record.get('journal') or 'Unknown'}\n"
            f"Year: {record.get('year') or 'Unknown'}\n"
            f"Authors: {', '.join(record.get('authors') or ['Unknown'])}\n"
            f"Abstract: {record.get('abstract') or '[No abstract available]'}\n\n"
            f"Evaluate the study. Remember to respond ONLY with the JSON object."
        )

    def screen_records(self, records: list[dict], session_file: Path = None, max_workers: int = 5) -> list[dict]:
        """Screens study records. Supports resuming using a session file."""
        results = []
        start_index = 0
        
        # Load existing state if resuming
        if session_file and session_file.exists():
            try:
                with open(session_file, "r", encoding="utf-8") as f:
                    saved_data = json.load(f)
                results = saved_data.get("results", [])
                start_index = len(results)
                console.print(f"[bold green]Resuming screening from index {start_index} ({len(records) - start_index} remaining)...[/bold green]")
            except Exception as e:
                console.print(f"[red]Error loading session file, starting fresh: {e}[/red]")
                results = []

        # If already completed
        if start_index >= len(records):
            return results

        records_to_process = records[start_index:]
        
        # Batch preparation for parallel execution
        tasks = []
        for rec in records_to_process:
            sys_p = self.get_system_prompt()
            usr_p = self.format_user_prompt(rec)
            tasks.append((sys_p, usr_p, True))
            
        console.print(f"Starting screening of [bold cyan]{len(records_to_process)}[/bold cyan] articles using {self.llm.api_type} ({self.llm.model_name})...")
        
        # Run batches in parallel and show progress bar
        batch_size = max_workers * 2
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task_id = progress.add_task("[cyan]Screening abstracts...", total=len(records_to_process))
            
            for b_idx in range(0, len(records_to_process), batch_size):
                batch_records = records_to_process[b_idx:b_idx + batch_size]
                batch_tasks = tasks[b_idx:b_idx + batch_size]
                
                batch_outputs = self.llm.run_parallel_screening(batch_tasks, max_workers=max_workers)
                
                for idx, out in enumerate(batch_outputs):
                    rec = batch_records[idx]
                    # Strip markdown code fences that LLMs sometimes wrap JSON in
                    # e.g. ```json\n{...}\n``` → {...}
                    cleaned = out.strip()
                    if cleaned.startswith("```"):
                        cleaned = cleaned.lstrip("`").strip()
                        if cleaned.lower().startswith("json"):
                            cleaned = cleaned[4:].strip()
                        cleaned = cleaned.rstrip("`").strip()
                    # Parse JSON verdict
                    try:
                        decision = json.loads(cleaned)
                        verdict = decision.get("verdict", "UNSURE").upper()
                        reason = decision.get("reason", "No reason provided.")
                    except Exception:
                        # Fallback for parsing errors — log raw output for debugging
                        verdict = "UNSURE"
                        reason = f"Parsing Error on raw response: {out[:200]}"
                        
                    screened_record = dict(rec)
                    screened_record["screening"] = {
                        "verdict": verdict,
                        "reason": reason
                    }
                    results.append(screened_record)
                
                # Save progress periodically
                if session_file:
                    try:
                        session_file.parent.mkdir(parents=True, exist_ok=True)
                        with open(session_file, "w", encoding="utf-8") as f:
                            json.dump({"results": results}, f, ensure_ascii=False, indent=2)
                    except Exception as e:
                        console.print(f"[red]Warning: failed to save session checkpoint: {e}[/red]")
                        
                progress.update(task_id, advance=len(batch_records))
                
        console.print("[bold green]Abstract screening completed![/bold green]")
        
        # Summarize results
        includes = sum(1 for r in results if r["screening"]["verdict"] == "INCLUDE")
        excludes = sum(1 for r in results if r["screening"]["verdict"] == "EXCLUDE")
        unsures = sum(1 for r in results if r["screening"]["verdict"] == "UNSURE")
        
        console.print(f"📊 [bold]Abstract Screening Summary:[/bold] Included: [green]{includes}[/green] | Excluded: [red]{excludes}[/red] | Unsure: [yellow]{unsures}[/yellow]")
        
        return results
