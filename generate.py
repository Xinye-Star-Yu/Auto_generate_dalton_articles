"""Compatibility entry point for one-off article generation."""

from auto_generate_dalton_articles.generate import main


if __name__ == "__main__":
    raise SystemExit(main() or 0)
