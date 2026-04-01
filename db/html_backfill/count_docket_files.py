"""
count_docket_files.py

Walks a 'data' folder with the structure:
  data/
    <AGENCY>/
      <AGENCY-DOCKETID>/
        text-<AGENCY-DOCKETID>/
          documents/
            *.json, *.htm, etc.

Counts file types per docket, groups by agency, and saves results to a text file.
"""

import os
from collections import defaultdict

# ── Configuration ────────────────────────────────────────────────────────────
DATA_DIR   = "data"          # Path to your top-level data folder
OUTPUT_FILE = "docket_file_counts.txt"
OUTPUT_FILE_HTM = "docket_htm_status.txt"
# ─────────────────────────────────────────────────────────────────────────────


def count_files_in_docket(documents_path: str) -> dict[str, int]:
    """Return a dict of {extension: count} for all files in a documents folder."""
    counts: dict[str, int] = defaultdict(int)
    if not os.path.isdir(documents_path):
        return counts
    for entry in os.scandir(documents_path):
        if entry.is_file():
            _, ext = os.path.splitext(entry.name)
            ext = ext.lower() if ext else "(no extension)"
            counts[ext] += 1
    return counts


def build_report(data_dir: str) -> dict[str, dict[str, dict[str, int]]]:
    """
    Returns nested dict:
      { agency: { docket_id: { ext: count } } }
    """
    report: dict[str, dict[str, dict[str, int]]] = {}

    if not os.path.isdir(data_dir):
        raise FileNotFoundError(f"Data directory not found: '{data_dir}'")

    for agency in sorted(os.listdir(data_dir)):
        agency_path = os.path.join(data_dir, agency)
        if not os.path.isdir(agency_path):
            continue

        report[agency] = {}

        for docket in sorted(os.listdir(agency_path)):
            docket_path = os.path.join(agency_path, docket)
            if not os.path.isdir(docket_path):
                continue

            # Layer:  text-<docket>[-optional-suffix]/documents/
            # Scan for any subfolder starting with "text-" to handle
            # variants like text-CMS-2025-0265-0001
            counts: dict[str, int] = {}
            try:
                subfolders = [
                    e.name for e in os.scandir(docket_path)
                    if e.is_dir() and e.name.lower().startswith("text-")
                ]
            except PermissionError:
                subfolders = []

            if subfolders:
                text_folder = os.path.join(docket_path, subfolders[0])
                documents_path = os.path.join(text_folder, "documents")
                counts = dict(count_files_in_docket(documents_path))

            report[agency][docket] = counts

    return report


def write_report(report: dict, output_file: str) -> None:
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("DOCKET FILE TYPE REPORT")
    lines.append("=" * 60)

    for agency in sorted(report):
        lines.append(f"\n{'─' * 60}")
        lines.append(f"  AGENCY: {agency}")
        lines.append(f"{'─' * 60}")

        dockets = report[agency]
        if not dockets:
            lines.append("    (no dockets found)")
            continue

        # Agency-level totals
        agency_totals: dict[str, int] = defaultdict(int)

        for docket in sorted(dockets):
            ext_counts = dockets[docket]
            lines.append(f"\n  Docket: {docket}")

            if not ext_counts:
                lines.append("    (no files found in documents folder)")
                continue

            total = sum(ext_counts.values())
            for ext in sorted(ext_counts):
                lines.append(f"    {ext:<20} {ext_counts[ext]:>5} file(s)")
                agency_totals[ext] += ext_counts[ext]

            lines.append(f"    {'TOTAL':<20} {total:>5} file(s)")

        # Agency summary
        agency_grand_total = sum(agency_totals.values())
        lines.append(f"\n  {'─' * 40}")
        lines.append(f"  {agency} SUMMARY:")
        for ext in sorted(agency_totals):
            lines.append(f"    {ext:<20} {agency_totals[ext]:>5} file(s)")
        lines.append(f"    {'GRAND TOTAL':<20} {agency_grand_total:>5} file(s)")

    # Grand total docket count across all agencies
    total_dockets = sum(len(dockets) for dockets in report.values())
    global_ext_totals: dict[str, int] = defaultdict(int)
    for dockets in report.values():
        for ext_counts in dockets.values():
            for ext, count in ext_counts.items():
                global_ext_totals[ext] += count
    total_files_all = sum(global_ext_totals.values())

    lines.append(f"\n{'=' * 60}")
    lines.append("OVERALL TOTALS")
    lines.append(f"{'=' * 60}")
    lines.append(f"  {'Total Agencies:':<25} {len(report):>5}")
    lines.append(f"  {'Total Dockets:':<25} {total_dockets:>5}")
    lines.append(f"  {'Total Files:':<25} {total_files_all:>5}")
    lines.append(f"\n  File Type Breakdown:")
    for ext in sorted(global_ext_totals):
        lines.append(f"    {ext:<20} {global_ext_totals[ext]:>5} file(s)")
    lines.append(f"{'=' * 60}")
    lines.append("END OF REPORT")
    lines.append("=" * 60)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Report saved to: {output_file}")


def write_htm_report(report: dict, output_file: str) -> None:
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("DOCKET HTM FILE STATUS REPORT")
    lines.append("=" * 60)

    total_with = 0
    total_without = 0

    for agency in sorted(report):
        lines.append(f"\n{'─' * 60}")
        lines.append(f"  AGENCY: {agency}")
        lines.append(f"{'─' * 60}")

        dockets = report[agency]
        if not dockets:
            lines.append("    (no dockets found)")
            continue

        with_htm    = [d for d, exts in dockets.items() if ".htm" in exts]
        without_htm = [d for d, exts in dockets.items() if ".htm" not in exts]

        lines.append(f"\n  Contains HTM files ({len(with_htm)}):")
        if with_htm:
            for docket in sorted(with_htm):
                count = dockets[docket][".htm"]
                lines.append(f"    [YES]  {docket}  ({count} .htm file(s))")
        else:
            lines.append("    (none)")

        lines.append(f"\n  No HTM files ({len(without_htm)}):")
        if without_htm:
            for docket in sorted(without_htm):
                lines.append(f"    [NO ]  {docket}")
        else:
            lines.append("    (none)")

        total_with    += len(with_htm)
        total_without += len(without_htm)

    total_dockets = total_with + total_without
    lines.append(f"\n{'=' * 60}")
    lines.append("OVERALL TOTALS")
    lines.append(f"{'=' * 60}")
    lines.append(f"  {'Total Dockets:':<30} {total_dockets:>5}")
    lines.append(f"  {'Dockets with HTM files:':<30} {total_with:>5}")
    lines.append(f"  {'Dockets without HTM files:':<30} {total_without:>5}")
    lines.append(f"{'=' * 60}")
    lines.append("END OF REPORT")
    lines.append("=" * 60)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"HTM status report saved to: {output_file}")



def main() -> None:
    print(f"Scanning '{DATA_DIR}' ...")
    try:
        report = build_report(DATA_DIR)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        return

    write_report(report, OUTPUT_FILE)
    write_htm_report(report, OUTPUT_FILE_HTM)

    # Print a quick summary to the terminal as well
    total_dockets = sum(len(d) for d in report.values())
    print(f"Agencies found : {len(report)}")
    print(f"Dockets found  : {total_dockets}")


if __name__ == "__main__":
    main()
