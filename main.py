import os
import json
import logging
from typing import Optional
import typer
from rich import print
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

# Ingestion pipeline imports
from src.utils.logger import setup_logger, get_warnings, get_errors
from src.utils.constants import STAGE_PARSING, STAGE_PROJECTION, STAGE_VALIDATION
from src.parsers.csv_parser import CSVParser
from src.parsers.ats_parser import ATSParser
from src.parsers.pdf_resume_parser import PDFResumeParser
from src.parsers.txt_notes_parser import TXTNotesParser
from src.normalizers.skills import SkillNormalizer
from src.merger.confidence_engine import ConfidenceEngine
from src.merger.conflict_resolver import ConflictResolver
from src.merger.entity_resolver import EntityResolver
from src.projection.config_projection import ConfigProjection
from src.provenance.provenance_tracker import AuditTracker

app = typer.Typer(help="Multi-Source Candidate Data Transformer CLI Pipeline.")
console = Console()

@app.command()
def ingest(
    csv: Optional[str] = typer.Option(None, "--csv", help="Path to Recruiter CSV file"),
    ats: Optional[str] = typer.Option(None, "--ats", help="Path to ATS JSON file"),
    resume: Optional[str] = typer.Option(None, "--resume", help="Path to Resume PDF file"),
    notes: Optional[str] = typer.Option(None, "--notes", help="Path to Recruiter Notes TXT file"),
    config: Optional[str] = typer.Option(None, "--config", help="Path to projection configuration JSON"),
    output: str = typer.Option("outputs/candidate.json", "--output", help="Path to output final canonical JSON file"),
    log_level: str = typer.Option("INFO", "--log-level", help="Console logging level (DEBUG, INFO, WARNING, ERROR)")
) -> None:
    """
    Ingests and merges candidate profiles from multiple sources (CSV, JSON, PDF, TXT)
    into a unified canonical candidate profile using explainable merging.
    """
    # 1. Setup Structured Logging and Audit Tracker
    log_dir = os.path.dirname(os.path.abspath(output))
    os.makedirs(log_dir, exist_ok=True)
    log_file_path = os.path.join(log_dir, "pipeline.log")
    
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    logger = setup_logger(name="pipeline", log_file=log_file_path, console_level=numeric_level)

    console.print(Panel.fit(
        "[bold cyan]Eightfold AI[/bold cyan] - [bold white]Multi-Source Candidate Data Transformer[/bold white]",
        border_style="blue"
    ))

    audit_tracker = AuditTracker()
    logger.info("Pipeline execution started.")

    # 2. Initialize engines
    skill_normalizer = SkillNormalizer()
    confidence_engine = ConfidenceEngine()
    conflict_resolver = ConflictResolver(confidence_engine)
    entity_resolver = EntityResolver(conflict_resolver, audit_tracker)

    raw_profiles = []

    # 3. Parse Ingestion Sources (with progress tracker)
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        
        # Recruiter CSV
        if csv:
            progress.add_task(description="[cyan]Parsing Recruiter CSV...[/cyan]", total=None)
            logger.info(f"Ingesting Recruiter CSV from '{csv}'")
            audit_tracker.sources_processed.append("Recruiter CSV")
            csv_parser = CSVParser(skill_normalizer=skill_normalizer)
            parsed = csv_parser.parse(csv, audit_tracker=audit_tracker)
            raw_profiles.extend(parsed)
            logger.info(f"CSV Parser successfully ingested {len(parsed)} candidate profiles.")

        # ATS JSON
        if ats:
            progress.add_task(description="[cyan]Parsing ATS JSON...[/cyan]", total=None)
            logger.info(f"Ingesting ATS JSON from '{ats}'")
            audit_tracker.sources_processed.append("ATS JSON")
            ats_parser = ATSParser(skill_normalizer=skill_normalizer)
            parsed = ats_parser.parse(ats, audit_tracker=audit_tracker)
            raw_profiles.extend(parsed)
            logger.info(f"ATS Parser successfully ingested {len(parsed)} candidate profiles.")

        # Resume PDF
        if resume:
            progress.add_task(description="[cyan]Parsing Resume PDF...[/cyan]", total=None)
            logger.info(f"Ingesting Resume PDF from '{resume}'")
            audit_tracker.sources_processed.append("Resume PDF")
            pdf_parser = PDFResumeParser(skill_normalizer=skill_normalizer)
            parsed = pdf_parser.parse(resume, audit_tracker=audit_tracker)
            raw_profiles.extend(parsed)
            logger.info(f"PDF Resume Parser successfully ingested {len(parsed)} candidate profiles.")

        # Recruiter Notes TXT
        if notes:
            progress.add_task(description="[cyan]Parsing Recruiter Notes TXT...[/cyan]", total=None)
            logger.info(f"Ingesting Recruiter Notes from '{notes}'")
            audit_tracker.sources_processed.append("Recruiter Notes TXT")
            txt_parser = TXTNotesParser(skill_normalizer=skill_normalizer)
            parsed = txt_parser.parse(notes, audit_tracker=audit_tracker)
            raw_profiles.extend(parsed)
            logger.info(f"TXT Notes Parser successfully ingested {len(parsed)} candidate profiles.")

        # 4. Check for parsed profiles
        if not raw_profiles:
            progress.stop()
            console.print("[bold red]Error: No candidate profiles were successfully parsed. Check source logs.[/bold red]")
            logger.error("Pipeline terminated: No valid candidate profiles loaded.")
            return

        # 5. Entity Resolution & Merging
        progress.add_task(description="[green]Resolving Entities & Merging Profiles...[/green]", total=None)
        logger.info("Executing entity resolution and field-level profile merging.")
        canonical_profiles = entity_resolver.resolve_and_merge(raw_profiles)

        # 6. Apply Configurable Projection Layer
        progress.add_task(description="[yellow]Applying Schema Projections...[/yellow]", total=None)
        logger.info(f"Initializing projection layer. Config: '{config}'")
        projector = ConfigProjection(config_path=config)
        projected_data = projector.project_list(canonical_profiles)

        # Write output file
        logger.info(f"Writing final projected candidate records to {output}")
        try:
            with open(output, "w", encoding="utf-8") as f:
                json.dump(projected_data, f, indent=2)
            
            # Log successful projection timeline event
            for idx, cand in enumerate(projected_data):
                audit_tracker.add_timeline_event(
                    stage=STAGE_PROJECTION,
                    source="System",
                    field="output_file",
                    raw_value=None,
                    normalized_value=None,
                    validation_result="Success",
                    explanation=f"Projected and outputted profile to '{output}'."
                )
        except Exception as e:
            logger.error(f"Failed to write output candidate JSON to {output}: {e}")
            audit_tracker.add_error(f"Failed to write output candidate JSON: {str(e)}")

        # 7. Write Audit logs
        progress.add_task(description="[magenta]Exporting Audit Log Reports...[/magenta]", total=None)
        # Import accumulated logs from utils.logger
        for warning_log in get_warnings():
            audit_tracker.add_warning(warning_log)
        for error_log in get_errors():
            audit_tracker.add_error(error_log)
            
        audit_tracker.generate_logs(log_dir)

    # 8. Output Execution Summary Table
    # Fetch metrics from tracker
    completeness = 0.0
    if audit_tracker.total_possible_fields > 0:
        completeness = round((audit_tracker.populated_fields / audit_tracker.total_possible_fields) * 100, 2)
    
    # Render final console execution report
    console.print("\n[bold green]Ingestion Pipeline Summary[/bold green]")
    summary_table = Table(show_header=True, header_style="bold magenta")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="green")

    summary_table.add_row("Sources Processed", ", ".join(audit_tracker.sources_processed))
    summary_table.add_row("Raw Inputs Ingested", str(len(raw_profiles)))
    summary_table.add_row("Unique Candidates Resolved", str(audit_tracker.candidates_processed_count))
    summary_table.add_row("Duplicates Deduped", str(audit_tracker.duplicates_removed))
    summary_table.add_row("Merge Conflicts Resolved", str(audit_tracker.conflicts_resolved))
    summary_table.add_row("Normalization Fixes Applied", str(audit_tracker.normalization_fixes))
    summary_table.add_row("Validation Failures Encountered", str(audit_tracker.validation_failures))
    summary_table.add_row("Canonical Completeness %", f"{completeness}%")
    
    # Calculate average confidence
    all_confs = []
    for cand in audit_tracker.decisions.values():
        for field in cand.values():
            if "confidence_score" in field and field.get("winning_source") is not None:
                all_confs.append(field["confidence_score"])
    avg_conf = round(sum(all_confs) / len(all_confs), 4) if all_confs else 0.0
    summary_table.add_row("Overall Ingestion Confidence Score", f"{avg_conf:.4f}")

    console.print(summary_table)

    # Render files generated list
    console.print("\n[bold yellow]Output Files Generated:[/bold yellow]")
    files_table = Table(show_header=True, header_style="bold yellow")
    files_table.add_column("File Name", style="blue")
    files_table.add_column("Description", style="white")
    
    files_table.add_row(output, "Final projected canonical candidate profiles JSON")
    files_table.add_row(os.path.join(log_dir, "candidate_timeline.json"), "Full data lineage and transformation audit trail")
    files_table.add_row(os.path.join(log_dir, "decision_log.json"), "Explainable field-level winning sources and weights log")
    files_table.add_row(os.path.join(log_dir, "quality_report.json"), "Deduplication and validation quality score report")
    files_table.add_row(os.path.join(log_dir, "pipeline_summary.json"), "Execution execution times, processed metadata, and log summaries")
    files_table.add_row(log_file_path, "Structured trace pipeline log file")
    
    console.print(files_table)
    console.print("\n[bold green]Pipeline finished successfully.[/bold green] Log files saved to outputs folder.\n")

if __name__ == "__main__":
    app()
