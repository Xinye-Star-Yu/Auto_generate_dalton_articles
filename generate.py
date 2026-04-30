"""Compatibility entry point for one-off article generation."""

import argparse

from auto_generate_dalton_articles.generate import main

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a scientific summary article.")
    parser.add_argument("--doi", default=None, help="Target DOI to use instead of searching.")
    args = parser.parse_args()
    raise SystemExit(main(target_doi=args.doi) or 0)
