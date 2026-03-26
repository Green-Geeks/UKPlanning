#!/usr/bin/env python3
"""Disable councils whose URLs failed verification.

Reads url_report.txt and adds 'enabled: false' to configs that aren't responding.
"""
from pathlib import Path


def disable_dead(report_path: Path, config_dir: Path) -> dict:
    stats = {"disabled": 0, "already_disabled": 0, "kept_enabled": 0}

    for line in report_path.read_text().strip().split("\n"):
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        name, platform, status = parts[0], parts[1], parts[2]
        code = name.lower().replace(" ", "_")
        config_path = config_dir / f"{code}.yml"

        if not config_path.exists():
            continue

        content = config_path.read_text()

        if status == "ok":
            stats["kept_enabled"] += 1
            continue

        if "enabled: false" in content:
            stats["already_disabled"] += 1
            continue

        # Add enabled: false
        content = content.rstrip() + "\nenabled: false\n"
        config_path.write_text(content)
        stats["disabled"] += 1

    return stats


if __name__ == "__main__":
    repo_root = Path(__file__).parent.parent
    report_path = repo_root / "url_report.txt"
    config_dir = repo_root / "src" / "config" / "councils"

    if not report_path.exists():
        print("Run verify_urls.py first to generate url_report.txt")
        exit(1)

    stats = disable_dead(report_path, config_dir)
    print(f"Disabled: {stats['disabled']}")
    print(f"Already disabled: {stats['already_disabled']}")
    print(f"Kept enabled: {stats['kept_enabled']}")
