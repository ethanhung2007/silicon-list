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
from silicon_list.providers.cowork import CoworkProvider

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


def build_legacy_providers(
    config: Config,
    provider_choice: str,
    mode: str,
    include_github_only: bool,
    cowork_file: Path | None,
    skip_cowork_run: bool = False,
):
    providers = []

    if mode == "live" and provider_choice == "mock":
        provider_choice = "github"

    if provider_choice == "github" or (mode == "live" and provider_choice == "all"):
        providers.append(("legacy", GitHubSimplifyProvider(config)))

    if provider_choice == "google":
        providers.append(("legacy", GoogleSearchProvider(config)))

    if provider_choice == "searxng":
        providers.append(("legacy", SearXNGSearchProvider(config)))

    if provider_choice == "cowork" or (mode == "live" and provider_choice == "all"):
        providers.append(("legacy", CoworkProvider(config, cowork_file, skip_run=skip_cowork_run)))

    if provider_choice == "mock" or (mode == "mock" and provider_choice == "all"):
        if not include_github_only:
            providers.append(("legacy", MockProvider(config)))

    return providers


def _searxng_available(config: Config) -> bool:
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


def build_hybrid_stages(
    config: Config,
    provider_choice: str,
    mode: str,
    include_github_only: bool,
    cowork_file: Path | None,
    skip_cowork_run: bool = False,
):
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

    if provider_choice == "cowork" or (provider_choice == "all" and config.cowork_stage2):
        stage2.append(("stage2", CoworkProvider(config, cowork_file, skip_run=skip_cowork_run)))

    return stage1 + stage2


def _run_validate_only(config: Config, output_dir: Path, errors_file: Path, no_open_html: bool):
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
    parser.add_argument("--mode", choices=["mock", "live"], default="mock")
    parser.add_argument("--pipeline", choices=["hybrid", "legacy"])
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--write-default-config", action="store_true")
    parser.add_argument("--print-report", action="store_true")
    parser.add_argument("--include-github-only", action="store_true")
    parser.add_argument(
        "--provider",
        choices=["mock", "github", "google", "searxng", "cowork", "all"],
        default="mock",
    )
    parser.add_argument("--cowork-file", type=Path, help="Path override for the Cowork JSON output")
    parser.add_argument("--cowork-stage2", choices=["true", "false"], help="Include Cowork as Stage 2 in hybrid mode")
    parser.add_argument("--cowork-max-listings", type=int, help="Maximum listings to request from Cowork")
    parser.add_argument("--skip-cowork-run", action="store_true", help="Skip running claude; reload existing export")
    parser.add_argument("--hardware-bias", choices=["true", "false"])
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--validate-links", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reset-seen", action="store_true")
    parser.add_argument("--json-export", action="store_true")
    parser.add_argument("--no-open-html", action="store_true")

    args = parser.parse_args()

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
    if args.cowork_stage2 is not None:
        config.cowork_stage2 = str_to_bool(args.cowork_stage2)
    if args.cowork_max_listings is not None:
        config.cowork_max_listings = args.cowork_max_listings
    if args.hardware_bias is not None:
        config.hardware_bias = str_to_bool(args.hardware_bias)

    if args.validate_only:
        _run_validate_only(config, args.output_dir, errors_file, args.no_open_html)
        sys.exit(0)

    state_manager = StateManager(seen_file)
    if args.reset_seen:
        if seen_file.exists():
            seen_file.unlink()
    else:
        state_manager.load()

    provider_choice = args.provider
    pipeline_choice = getattr(config, "pipeline", "hybrid")
    cowork_file = args.cowork_file
    skip_cowork_run = args.skip_cowork_run

    if pipeline_choice == "legacy":
        providers = build_legacy_providers(config, provider_choice, args.mode, args.include_github_only, cowork_file, skip_cowork_run)
    else:
        providers = build_hybrid_stages(config, provider_choice, args.mode, args.include_github_only, cowork_file, skip_cowork_run)

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
            print(f"Rate limit from {provider.__class__.__name__}; continuing.", file=sys.stderr)
        except ProviderError as e:
            logger.error(f"Provider error from {provider.__class__.__name__}: {e}")
            print(f"Provider error from {provider.__class__.__name__}: {e}", file=sys.stderr)
        except Exception as e:
            logger.exception(f"Unexpected error from {provider.__class__.__name__}: {e}")
            print(f"Unexpected error from {provider.__class__.__name__}: {e}", file=sys.stderr)

    if not all_raw_listings and rate_limit_errors:
        print("Rate limit hit and no listings were collected. Retry later.", file=sys.stderr)
        sys.exit(42)

    try:
        normalized = normalize_listings(all_raw_listings)
        if pipeline_choice == "hybrid":
            normalized = merge_stage_listings(normalized)

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

        deduper = Deduper()
        kept = deduper.deduplicate(kept)

        new_listings, seen = dedupe_listings(kept, state_manager)
        new_count = len(new_listings)

        use_new_ranker = getattr(config, "use_new_ranker", True)
        if use_new_ranker:
            scored = rank_listings(new_listings, config)
            suppressed = [s for s in scored if s.tier == 4]
            scored = [s for s in scored if s.tier <= 3]
        else:
            scored = score_listings(new_listings, config)
            suppressed = []

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

        if not args.dry_run:
            for s in scored:
                for k in generate_dedupe_keys(s.listing):
                    state_manager.add(k)
            state_manager.save()

        if args.print_report:
            with open(results_file, 'r') as f:
                print(f.read())

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
