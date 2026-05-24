#!/usr/bin/env python3
import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

REPLACEMENTS = [
    "lru",
    "pseudo_lru",
    "lru_bip",
    "lru_lip",
    "srrip"
]

WARMUP_INSTRUCTIONS = 5000
SIMULATION_INSTRUCTIONS = 150000
MAX_WORKERS = len(REPLACEMENTS)

IPC_PATTERN  = re.compile(r"CPU 0 cumulative IPC:\s*([0-9.]+)")
L2_PATTERN   = re.compile(r"cpu0->cpu0_L2C TOTAL\s+ACCESS:\s*([0-9]+)\s+HIT:\s*([0-9]+)\s+MISS:\s*([0-9]+)")

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run ChampSim branch-predictor experiments and write results to CSV.",
    )
    parser.add_argument(
        "-c",
        "--champsim-dir",
        type=Path,
        default=SCRIPT_DIR,
        help="Path to ChampSim project root (default: directory containing this script)",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path.cwd(),
        help="Directory for replacement_results.csv (default: current working directory)",
    )
    parser.add_argument(
        "-t",
        "--traces-dir",
        type=Path,
        default=None,
        help="Path to trace files",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=WARMUP_INSTRUCTIONS,
        help=f"Number of warmup instructions (default: {WARMUP_INSTRUCTIONS})",
    )
    parser.add_argument(
        "--sim",
        type=int,
        default=SIMULATION_INSTRUCTIONS,
        help=f"Number of simulation instructions (default: {SIMULATION_INSTRUCTIONS})",
    )
    return parser.parse_args()


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    champsim_dir = args.champsim_dir.resolve()
    traces_dir = (args.traces_dir or champsim_dir / "traces").resolve()
    output_dir = args.output_dir.resolve()

    if not champsim_dir.is_dir():
        print(f"[ERROR] ChampSim directory not found: {champsim_dir}", file=sys.stderr)
        sys.exit(1)

    for name in ("champsim_config.json", "config.sh"):
        if not (champsim_dir / name).is_file():
            print(f"[ERROR] Missing {name} in {champsim_dir}", file=sys.stderr)
            sys.exit(1)

    if not traces_dir.is_dir():
        print(f"[ERROR] Traces directory not found: {traces_dir}", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    return champsim_dir, traces_dir, output_dir


def parse_results(output: str):
    ipc_match = IPC_PATTERN.search(output)
    l2_match = L2_PATTERN.search(output)

    ipc = float(ipc_match.group(1)) if ipc_match else None
    access = int(l2_match.group(1)) if l2_match else None
    hit = int(l2_match.group(2)) if l2_match else None
    miss = int(l2_match.group(3)) if l2_match else None

    return ipc, access, hit, miss


def replacement_worker(
    replacement: str,
    champsim_dir: Path,
    traces_dir: Path,
    warmup_instructions: int,
    simulation_instructions: int,
):
    results = []

    print(f"[INFO] Starting worker for replacement: {replacement}")

    temp_dir = Path(tempfile.mkdtemp(prefix=f"champsim_{replacement}_"))

    print(f"[INFO] [{replacement}] Working directory: {temp_dir}")
    shutil.copytree(
        champsim_dir,
        temp_dir,
        dirs_exist_ok=True,
        # Do not copy build artifacts: stale .csconfig/*.d files embed absolute
        # paths from the source tree and make exits 2 after a successful link.
        ignore=shutil.ignore_patterns("traces", "_configuration.mk"),
    )

    traces_symlink = temp_dir / "traces"
    traces_symlink.symlink_to(traces_dir, target_is_directory=True)

    config_path = temp_dir / "champsim_config.json"

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    config["ooo_cpu"][0]["branch_predictor"] = "bimodal"
    config["L2C"]["replacement"] = replacement

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

    print(f"[INFO] [{replacement}] Running config.sh")

    subprocess.run(
        ["./config.sh", "champsim_config.json"],
        check=True,
        cwd=temp_dir,
    )

    print(f"[INFO] [{replacement}] Building ChampSim")

    subprocess.run(
        ["make", "-j"],
        check=True,
        cwd=temp_dir,
    )

    traces = sorted(traces_dir.glob("*.xz"))

    for trace in traces:
        print(f"[INFO] [{replacement}] Running {trace.name}")

        cmd = [
            str(temp_dir / "bin/champsim"),
            "--warmup-instructions",
            str(warmup_instructions),
            "--simulation-instructions",
            str(simulation_instructions),
            str(trace),
        ]

        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=True,
                cwd=temp_dir,
            )

            output = proc.stdout
            ipc, access, _, miss = parse_results(output)

            if (ipc    is None or
                access is None or
                miss   is None):
                print("[ERROR] Failed to parse results")
                continue

            miss_rate = miss / access if access > 0 else 0.0
            results.append({
                "trace": trace.name,
                "replacement": replacement,
                "IPC": ipc,
                "l2_miss_rate": miss_rate
            })
            print(f"[RESULT] [{replacement}] {trace.name} IPC={ipc} L2_MISS_RATE={miss_rate}")

        except subprocess.CalledProcessError as e:
            print(f"[ERROR] [{replacement}] {trace.name} failed")
            print(e.stdout)

    print(f"[INFO] [{replacement}] Completed")

    return results


def main():
    args = parse_args()
    champsim_dir, traces_dir, output_dir = resolve_paths(args)

    print(f"[INFO] ChampSim directory: {champsim_dir}")
    print(f"[INFO] Traces directory:   {traces_dir}")
    print(f"[INFO] Output directory:   {output_dir}")
    print(f"[INFO] Warmup instructions: {args.warmup}")
    print(f"[INFO] Simulation instructions: {args.sim}")

    all_results = []
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(
                replacement_worker,
                replacement,
                champsim_dir,
                traces_dir,
                args.warmup,
                args.sim,
            ): replacement
            for replacement in REPLACEMENTS
        }

        for future in as_completed(futures):
            replacement = futures[future]

            try:
                replacement_results = future.result()
                all_results.extend(replacement_results)

            except Exception as e:
                print(f"[ERROR] Worker failed for replacement {replacement}: {e}")

    output_csv = output_dir / "replacement_results.csv"

    with open(output_csv, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=["trace", "replacement", "IPC", "l2_miss_rate"],
        )
        writer.writeheader()
        for row in all_results:
            writer.writerow(row)

    print("\n[INFO] All experiments completed.")
    print(f"[INFO] Results saved to: {output_csv}")


if __name__ == "__main__":
    main()
