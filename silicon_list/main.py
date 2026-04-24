import argparse
import sys
import json
import webbrowser
import datetime
from pathlib import Path

from silicon_list.config import Config, DEFAULT_DIR
from silicon_list.storage.state import StateManager
from silicon_list.storage.logging_utils import setup_logger, print_summary

from silicon_list.providers.base import ProviderError, RateLimitError
from silicon_list.providers.mock_provider import MockProvider
from silicon_list.providers.github_simplify import GitHubSimplifyProvider
from silicon_list.providers.google_search import GoogleSearchProvider
from silicon_list.providers.searxng_search import SearXNGSearchProvider
from silicon_list.providers.openclaw_file import OpenClawFileProvider
from silicon_list.providers.hermes import HermesProvider

from silicon_list.pipeline.normalize import normalize_listings
from silicon_list.pipeline.filtering import filter_listings
from silicon_list.pipeline.merge import merge_stage_listings
from silicon_list.pipeline.dedupe import dedupe_listings, generate_dedupe_keys
from silicon_list.pipeline.scoring import score_listings
from silicon_list.pipeline.report import generate_report, generate_html_report
from silicon_list.ranker import rank_listings
from silicon_list.deduper import Deduper


def str_to_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def build_legacy_providers(config: Config, provider_choice: str, mode: str, include_github_only: bool, openclaw_file: Path | None, hermes_file: Path | None = None):
    providers = []

    if mode == "live" and provider_choice == "mock":
        provider_choice = "github"

    if provider_choice == "github" or (mode == "live" and provider_choice == "all"):
        providers.append(("legacy", GitHubSimplifyProvider(config)))

    if provider_choice == "google":
        providers.append(("legacy", GoogleSearchProvider(config)))

    if provider_choice == "searxng":
        providers.append(("legacy", SearXNGSearchProvider(config)))

    if provider_choice == "openclaw" or (mode == "live" and provider_choice == "all"):
        providers.append(("legacy", OpenClawFileProvider(config, openclaw_file)))

    if provider_choice == "hermes" or (mode == "live" and provider_choice == "all" and (hermes_file or config.hermes_enabled)):
        providers.append(("legacy", HermesProvider(config, hermes_file)))

    if provider_choice == "mock" or (mode == "mock" and provider_choice == "all"):
        if not include_github_only:
            providers.append(("legacy", MockProvider(config)))

    return providers


def _searxng_available(config: Config) -> bool:
    """Return True only when SEARXNG_URL is explicitly set and the instance responds."""
    import os
    env_key = getattr(config, "searxng_url_env", "SEARXNG_URL")
    url = os.getenv(env_key)
    if not url:
        return False
    try:
        import requests as _r
        _r.get(f"{url.rstrip('/')}/search", params={"q": "test", "format": "json"}, timeout=2)
        return True
    except Exception:
        return False


def _google_available(config: Config) -> bool:
    import os
    return bool(
        os.getenv(getattr(config, "google_api_key_env", "GOOGLE_API_KEY"))
        and os.getenv(getattr(config, "google_cse_id_env", "GOOGLE_CSE_ID"))
    )


def build_hybrid_stages(config: Config, provider_choice: str, mode: str, include_github_only: bool, openclaw_file: Path | None, hermes_file: Path | None = None):
    if mode == "live" and provider_choice == "mock":
        provider_choice = "all"

    stage1 = []
    stage2 = []

    if mode == "mock":
        if provider_choice in ("mock", "all") and not include_github_only:
            stage1.append(("stage1", MockProvider(config)))
        return stage1

    if provider_choice in ("github", "all"):
        stage1.append(("stage1", GitHubSimplifyProvider(config)))
    if provider_choice == "google" or (provider_choice == "all" and _google_available(config)):
        stage1.append(("stage1", GoogleSearchProvider(config)))
    if provider_choice == "searxng" or (provider_choice == "all" and _searxng_available(config)):
        stage1.append(("stage1", SearXNGSearchProvider(config)))

    if provider_choice == "openclaw" or (provider_choice == "all" and config.openclaw_stage2):
        stage2.append(("stage2", OpenClawFileProvider(config, openclaw_file)))

    if provider_choice == "hermes" or (provider_choice == "all" and (hermes_file or config.hermes_enabled)):
        stage2.append(("stage2", HermesProvider(config, hermes_file)))

    return stage1 + stage2


def _run_validate_only(config: Config, output_dir: Path, errors_file: Path, no_open_html: bool):
    """Re-validate all active DB listings without fetching new ones."""
    from silicon_list.storage.database import ListingsDatabase
    from silicon_list.validator import ListingValidator, ValidationStatus
    from silicon_list.models import Listing, ScoredListing

    db_path = output_dir / "listings.db"
    if not db_path.exists():
        print("No listings database found. Run a full pass first.", file=sys.stderr)
        sys.exit(1)

    db = ListingsDatabase(db_path)
    rows = db.fetch_active()
    if not rows:
        print("No active listings in database.", file=sys.stderr)
        sys.exit(0)

    validator = ListingValidator()
    updated = 0
    for row in rows:
        listing = Listing(
            source=row.get("source", ""),
            source_job_id=row.get("id", ""),
            company=row.get("company", ""),
            role=row.get("role", ""),
            location=row.get("location", ""),
            apply_url=row.get("apply_url", ""),
            description=row.get("description", ""),
            posted_at=row.get("posted_at"),
            cycle=row.get("cycle", ""),
        )
        result = validator.validate(listing)
        listing.raw_metadata = {
            "validation_status": result.status.value,
            "validation_confidence": result.confidence,
            "tags": json.loads(row.get("tags") or "[]"),
        }
        scored = ScoredListing(
            listing=listing,
            score=row.get("score", 0),
            tier=row.get("tier", 3),
        )
        db.upsert(scored)
        updated += 1

    db.close()
    print(f"[Silicon List] Validated {updated} listings.")


def main():
    parser = argparse.ArgumentParser(description="Silicon List CLI")
    parser.add_argument("--mode", choices=["mock", "live"], default="mock", help="Run mode")
    parser.add_argument("--pipeline", choices=["hybrid", "legacy"], help="Sourcing pipeline to use")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_DIR, help="Output directory")
    parser.add_argument("--write-default-config", action="store_true", help="Write default config and exit")
    parser.add_argument("--print-report", action="store_true", help="Print the report to stdout instead of file")
    parser.add_argument("--include-github-only", action="store_true", help="Only run Github Simplify provider")
    parser.add_argument("--provider", choices=["mock", "github", "google", "searxng", "openclaw", "hermes", "all"], default="mock", help="Provider to use")
    parser.add_argument("--openclaw-file", type=Path, help="Path to a JSON listing export from OpenClaw or another browser agent")
    parser.add_argument("--openclaw-stage2", choices=["true", "false"], help="Include OpenClaw import as Stage 2 in hybrid mode")
    parser.add_argument("--openclaw-max-leads", type=int, help="Maximum Stage 1 leads to hand to OpenClaw scripts")
    parser.add_argument("--openclaw-search-depth", choices=["light", "normal", "aggressive"], help="OpenClaw Stage 2 search depth hint")
    parser.add_argument("--hardware-bias", choices=["true", "false"], help="Bias scoring and discovery toward hardware roles")
    parser.add_argument("--hermes-file", type=Path, help="Path to a JSON listing export from Hermes Agent")
    parser.add_argument("--hermes-enabled", choices=["true", "false"], help="Include Hermes export in all-provider runs")
    parser.add_argument("--validate-only", action="store_true", help="Re-validate active DB listings without fetching new ones")
    parser.add_argument("--validate-links", action="store_true", help="Run HTTP link validation on fetched listings (slow)")
    parser.add_argument("--dry-run", action="store_true", help="Do not write state to seen.json")
    parser.add_argument("--reset-seen", action="store_true", help="Clear seen.json before running")
    parser.add_argument("--json-export", action="store_true", help="Export new listings to json")
    parser.add_argument("--no-open-html", action="store_true", help="Generate results.html but do not open it")

    args = parser.parse_args()

    # Paths
    config_file = args.output_dir / "config.json"
    seen_file = args.output_dir / "seen.json"
    results_file = args.output_dir / "results.md"
    html_file = args.output_dir / "results.html"
    errors_file = args.output_dir / "errors.log"

    logger = setup_logger(errors_file)

    if args.write_default_config:
        Config().save(config_file)
        print(f"Default config written to {config_file}")
        sys.exit(0)

    config = Config.load(config_file)
    if args.pipeline:
        config.pipeline = args.pipeline
    if args.openclaw_stage2 is not None:
        config.openclaw_stage2 = str_to_bool(args.openclaw_stage2)
    if args.openclaw_max_leads is not None:
        config.openclaw_max_leads = args.openclaw_max_leads
    if args.openclaw_search_depth:
        config.openclaw_search_depth = args.openclaw_search_depth
    if args.hardware_bias is not None:
        config.hardware_bias = str_to_bool(args.hardware_bias)
    if args.hermes_enabled is not None:
        config.hermes_enabled = str_to_bool(args.hermes_enabled)

    if args.validate_only:
        _run_validate_only(config, args.output_dir, errors_file, args.no_open_html)
        sys.exit(0)

    state_manager = StateManager(seen_file)
    if args.reset_seen:
        if seen_file.exists():
            seen_file.unlink()
    else:
        state_manager.load()

    # Determine providers
    provider_choice = args.provider
    pipeline_choice = getattr(config, "pipeline", "hybrid")
    hermes_file = args.hermes_file

    if pipeline_choice == "legacy":
        providers = build_legacy_providers(config, provider_choice, args.mode, args.include_github_only, args.openclaw_file, hermes_file)
    else:
        providers = build_hybrid_stages(config, provider_choice, args.mode, args.include_github_only, args.openclaw_file, hermes_file)

    # Fallback to mock if empty
    if not providers:
        providers.append(("stage1", MockProvider(config)))

    all_raw_listings = []
    rate_limit_errors = []
    date_found = datetime.date.today().isoformat()

    for stage_name, provider in providers:
        try:
            listings = provider.fetch_listings()
            for listing in listings:
                listing.raw_metadata = {
                    **listing.raw_metadata,
                    "stage": stage_name,
                    "date_found": listing.raw_metadata.get("date_found") or date_found,
                }
            all_raw_listings.extend(listings)
        except RateLimitError as e:
            rate_limit_errors.append((provider.__class__.__name__, str(e)))
            logger.error(f"Rate limit error from {provider.__class__.__name__}: {e}")
            print(f"Rate limit from {provider.__class__.__name__}; continuing with other providers.", file=sys.stderr)
        except ProviderError as e:
            logger.error(f"Provider error from {provider.__class__.__name__}: {e}")
            print(f"Provider error from {provider.__class__.__name__}: {e}", file=sys.stderr)
        except Exception as e:
            logger.exception(f"Unexpected error from {provider.__class__.__name__}: {e}")
            print(f"Unexpected error from {provider.__class__.__name__}: {e}", file=sys.stderr)

    if not all_raw_listings and rate_limit_errors:
        print("Rate limit hit and no listings were collected. Retry later.", file=sys.stderr)
        sys.exit(42)

    # Pipeline
    try:
        normalized = normalize_listings(all_raw_listings)
        if pipeline_choice == "hybrid":
            normalized = merge_stage_listings(normalized)

        # Optional HTTP link validation
        if args.validate_links:
            from silicon_list.validator import ListingValidator, ValidationStatus
            validator = ListingValidator()
            validated = []
            for lst in normalized:
                result = validator.validate(lst)
                lst.raw_metadata = {
                    **lst.raw_metadata,
                    "validation_status": result.status.value,
                    "validation_confidence": result.confidence,
                }
                validated.append(lst)
            normalized = validated

        kept, skipped = filter_listings(normalized, config)

        # Intra-batch deduplication
        deduper = Deduper()
        kept = deduper.deduplicate(kept)

        # Cross-run deduplication
        new_listings, seen = dedupe_listings(kept, state_manager)
        new_count = len(new_listings)

        # Scoring/ranking
        use_new_ranker = getattr(config, "use_new_ranker", True)
        if use_new_ranker:
            scored = rank_listings(new_listings, config)
            # Filter out tier 4 (suppressed)
            suppressed = [s for s in scored if s.tier == 4]
            scored = [s for s in scored if s.tier <= 3]
        else:
            scored = score_listings(new_listings, config)
            suppressed = []

        # SQLite upsert
        db = None
        if getattr(config, "db_enabled", True):
            try:
                from silicon_list.storage.database import ListingsDatabase
                db_path = args.output_dir / "listings.db"
                db = ListingsDatabase(db_path)
                for s in scored:
                    db.upsert(s)
                db.mark_stale(days=7)
                db.close()
            except Exception as e:
                logger.warning(f"Database write failed (non-fatal): {e}")

        generate_report(scored, skipped, results_file, config)
        generate_html_report(scored, skipped, html_file, config, new_count=new_count)

        # Write state
        if not args.dry_run:
            for s in scored:
                for k in generate_dedupe_keys(s.listing):
                    state_manager.add(k)
            state_manager.save()

        # Print report if requested
        if args.print_report:
            with open(results_file, 'r') as f:
                print(f.read())

        # JSON export
        if args.json_export:
            json_file = args.output_dir / "results.json"
            from dataclasses import asdict
            data = [asdict(s.listing) for s in scored]
            with open(json_file, 'w') as f:
                json.dump(data, f, indent=4)

        if not args.no_open_html:
            opened = webbrowser.open(html_file.resolve().as_uri())
            if not opened:
                print(f"HTML report written to {html_file}", file=sys.stderr)

        # Summary
        tier_counts = {1: 0, 2: 0, 3: 0}
        for s in scored:
            tier_counts[s.tier] = tier_counts.get(s.tier, 0) + 1

        suppressed_count = len(suppressed)
        updated_count = len(seen)

        print(
            f"[Silicon List] Run complete — {new_count} new, {updated_count} updated, "
            f"{suppressed_count} suppressed "
            f"({tier_counts[1]} T1 · {tier_counts[2]} T2 · {tier_counts[3]} T3). "
            f"See {html_file}"
        )

    except Exception as e:
        logger.exception(f"Pipeline error: {e}")
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
