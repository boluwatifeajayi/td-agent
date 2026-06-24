"""Command-line interface for td-agent."""

import logging
import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

load_dotenv()


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
        level=logging.DEBUG if verbose else logging.WARNING,
    )


@click.group()
@click.version_option("0.1.0", prog_name="td-agent")
def main() -> None:
    """TD Agent — AI-powered technical debt detection using Claude."""


@main.command()
@click.option("--repo", required=True, type=click.Path(exists=True), help="Path to the git repository")
@click.option("--sample-every", type=int, default=None,
              help="Sample every N commits (default 20 if neither --commits nor --test given)")
@click.option("--commits", type=int, default=None, help="Number of evenly-spaced commits to sample")
@click.option("--test", "test_mode", is_flag=True, default=False,
              help="Test mode: analyse only the latest commit and print a detailed report")
@click.option("--output-dir", type=click.Path(), default=None,
              help="Directory for CSV output (default: <project>/data/)")
@click.option("--model", default=None, hidden=True, help="Override the Claude model")
@click.option("-v", "--verbose", is_flag=True, default=False)
def analyze(repo, sample_every, commits, test_mode, output_dir, model, verbose) -> None:
    """Analyse a git repository for technical debt using Claude."""
    _setup_logging(verbose)

    from .analyzer import TechnicalDebtAnalyzer
    from .git_utils import get_commits
    from .report import save_results
    from .sampler import sample_every_n, sample_evenly, sample_latest

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        click.echo(
            "Error: GEMINI_API_KEY not set.\n"
            "Get a free key at https://aistudio.google.com and add it to .env.",
            err=True,
        )
        sys.exit(1)

    repo_path = str(Path(repo).expanduser().resolve())
    repo_name = Path(repo_path).name

    click.echo(f"Repository : {repo_path}")

    click.echo("Loading commit history ...", nl=False)
    try:
        all_commits = get_commits(repo_path)
    except Exception as exc:
        click.echo(f"\nFailed to read git history: {exc}", err=True)
        sys.exit(1)
    click.echo(f" {len(all_commits)} commits found.")

    if test_mode:
        sampled = sample_latest(all_commits)
        click.echo("Test mode  : analysing the latest commit only.")
    elif commits:
        sampled = sample_evenly(all_commits, commits)
        click.echo(f"Sampling   : {len(sampled)} evenly-spaced commits.")
    else:
        n = sample_every or 20
        sampled = sample_every_n(all_commits, n)
        click.echo(f"Sampling   : every {n} commits → {len(sampled)} to analyse.")

    if not sampled:
        click.echo("No commits to analyse.")
        sys.exit(0)

    kwargs = {}
    if model:
        kwargs["model"] = model
    analyzer = TechnicalDebtAnalyzer(**kwargs)
    results = []

    for i, commit in enumerate(sampled, 1):
        date_str = commit.date.strftime("%Y-%m-%d")
        msg_preview = commit.message[:65]
        click.echo(f"\n[{i}/{len(sampled)}] {commit.short_hash}  {date_str}  {msg_preview}")
        result = analyzer.analyze_commit(repo_path, commit)
        results.append(result)

        if result.analysis_error:
            click.echo(f"  ERROR: {result.analysis_error}", err=True)
        else:
            click.echo(
                f"  Debt score : {result.ai_debt_score:>5} min  |  "
                f"Issues: {len(result.issues):>3}  |  Files: {result.files_analyzed}"
            )
            if test_mode:
                _print_detailed_report(result)

    out_dir = Path(output_dir) if output_dir else None
    csv_path = save_results(results, repo_name, out_dir)
    click.echo(f"\nResults saved to : {csv_path}")

    ok = [r for r in results if not r.analysis_error]
    if ok:
        avg = sum(r.ai_debt_score for r in ok) / len(ok)
        click.echo(f"Summary          : {len(ok)}/{len(results)} commits analysed, average debt score {avg:.0f} min")


def _print_detailed_report(result) -> None:
    """Detailed human-readable output for --test mode."""
    click.echo()
    click.echo("━" * 64)
    click.echo(f"  TECHNICAL DEBT REPORT  {result.commit.short_hash}")
    click.echo("━" * 64)
    click.echo(f"  AI Debt Score  : {result.ai_debt_score} minutes")
    click.echo(f"  Issues found   : {len(result.issues)}")
    click.echo(f"  Files analysed : {result.files_analyzed}")
    click.echo()

    if result.issues:
        click.echo("  By category (remediation minutes):")
        for cat, mins in sorted(result.category_breakdown.items(), key=lambda x: -x[1]):
            click.echo(f"    {cat:<22} {mins:>5} min")
        click.echo()

        click.echo("  By severity:")
        for sev in ("critical", "high", "medium", "low"):
            n = result.severity_breakdown.get(sev, 0)
            if n:
                click.echo(f"    {sev:<10}  {n:>3} issue(s)")
        click.echo()

        top = sorted(result.issues, key=lambda x: -x.remediation_minutes)[:5]
        click.echo(f"  Top {len(top)} issues by effort:")
        for idx, issue in enumerate(top, 1):
            click.echo(f"  {idx}. [{issue.severity.upper()}] {issue.category}")
            click.echo(f"     {issue.description[:120]}")
            click.echo(f"     Location : {issue.location}")
            click.echo(f"     Effort   : {issue.remediation_minutes} min")
            click.echo(f"     Fix      : {issue.suggestion[:100]}")
            click.echo()

    if result.overall_assessment:
        click.echo("  Overall assessment:")
        for line in _wrap(result.overall_assessment, 70):
            click.echo(f"    {line}")
    click.echo("━" * 64)
    click.echo()


def _wrap(text: str, width: int):
    words = text.split()
    line = []
    length = 0
    for word in words:
        if length + len(word) + 1 > width and line:
            yield " ".join(line)
            line, length = [], 0
        line.append(word)
        length += len(word) + 1
    if line:
        yield " ".join(line)


@main.command()
@click.option("--repo", required=True,
              help="Repository name (as used in analyse) or path to the repo")
@click.option("--output", default="report.html", show_default=True, help="Output HTML file path")
@click.option("--data-dir", type=click.Path(), default=None)
def report(repo, output, data_dir) -> None:
    """Generate a standalone HTML report from previous analysis results."""
    from .report import build_html_report, load_results

    repo_name = Path(repo).name if Path(repo).exists() else repo
    data_path = Path(data_dir) if data_dir else None
    data = load_results(repo_name, data_path)

    if not data:
        click.echo(
            f"No results found for '{repo_name}'. Run  td-agent analyze --repo <path>  first.",
            err=True,
        )
        sys.exit(1)

    html = build_html_report(repo_name, data)
    with open(output, "w", encoding="utf-8") as f:
        f.write(html)
    click.echo(f"Report written to: {output}  ({len(data)} commits)")
