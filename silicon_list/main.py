import argparse
import sys
import json
import webbrowser
from pathlib import Path

from silicon_list.config import Config, DEFAULT_DIR
from silicon_list.storage.state import StateManager
from silicon_list.storage.logging_utils import setup_logger, print_summary

from silicon_list.providers.base import ProviderError, RateLimitError
from silicon_list.providers.mock_provider import MockProvider
from silicon_list.providers.github_simplify import GitHubSimplifyProvider
from silicon_list.providers.google_search import GoogleSearchProvider
from silicon_list.providers.openclaw_file import OpenClawFileProvider

from silicon_list.pipeline.normalize import normalize_listings
from silicon_list.pipeline.filtering import filter_listings
from silicon_list.pipeline.dedupe import dedupe_listings, generate_dedupe_keys
from silicon_list.pipeline.scoring import score_listings
from silicon_list.pipeline.report import generate_report, generate_html_report

def main():
    parser = argparse.ArgumentParser(description="Silicon List CLI")
    parser.add_argument("--mode", choices=["mock", "live"], default="mock", help="Run mode")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_DIR, help="Output directory")
    parser.add_argument("--write-default-config", action="store_true", help="Write default config and exit")
    parser.add_argument("--print-report", action="store_true", help="Print the report to stdout instead of file")
    parser.add_argument("--include-github-only", action="store_true", help="Only run Github Simplify provider")
    parser.add_argument("--provider", choices=["mock", "github", "google", "openclaw", "all"], default="mock", help="Provider to use")
    parser.add_argument("--openclaw-file", type=Path, help="Path to a JSON listing export from OpenClaw or another browser agent")
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

    state_manager = StateManager(seen_file)
    if args.reset_seen:
        if seen_file.exists():
            seen_file.unlink()
    else:
        state_manager.load()

    # Determine providers
    providers = []

    provider_choice = args.provider
    if args.mode == "live" and provider_choice == "mock":
        provider_choice = "github"

    if provider_choice == "github" or (args.mode == "live" and provider_choice == "all"):
        providers.append(GitHubSimplifyProvider(config))

    if provider_choice == "google" or (args.mode == "live" and provider_choice == "all"):
        providers.append(GoogleSearchProvider(config))

    if provider_choice == "openclaw" or (args.mode == "live" and provider_choice == "all"):
        providers.append(OpenClawFileProvider(config, args.openclaw_file))
    
    if provider_choice == "mock" or (args.mode == "mock" and provider_choice == "all"):
        if not args.include_github_only:
            providers.append(MockProvider(config))

    # Fallback to mock if empty
    if not providers:
        providers.append(MockProvider(config))

    all_raw_listings = []
    
    for provider in providers:
        try:
            listings = provider.fetch_listings()
            all_raw_listings.extend(listings)
        except RateLimitError as e:
            logger.error(f"Rate limit error from {provider.__class__.__name__}: {e}")
            # Exit 42 for a scheduler to detect retryable
            print(f"Rate limit hit. Retry later.", file=sys.stderr)
            sys.exit(42)
        except ProviderError as e:
            logger.error(f"Provider error from {provider.__class__.__name__}: {e}")
            print(f"Provider error from {provider.__class__.__name__}: {e}", file=sys.stderr)
        except Exception as e:
            logger.exception(f"Unexpected error from {provider.__class__.__name__}: {e}")
            print(f"Unexpected error from {provider.__class__.__name__}: {e}", file=sys.stderr)

    # Pipeline
    try:
        normalized = normalize_listings(all_raw_listings)
        kept, skipped = filter_listings(normalized, config)
        new_listings, seen = dedupe_listings(kept, state_manager)
        scored = score_listings(new_listings, config)
        
        generate_report(scored, skipped, results_file)
        generate_html_report(scored, skipped, html_file)
        
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

        # Print summary
        tier_counts = {1: 0, 2: 0, 3: 0}
        for s in scored:
            tier_counts[s.tier] = tier_counts.get(s.tier, 0) + 1
            
        print_summary(len(scored), tier_counts, html_file)
        
    except Exception as e:
        logger.exception(f"Pipeline error: {e}")
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
