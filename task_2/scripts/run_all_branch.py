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

PREDICTORS = [
    "pap",
    "gap",
    "gag",
    "bimodal",
]

WARMUP_INSTRUCTIONS = 5000
SIMULATION_INSTRUCTIONS = 15000
MAX_WORKERS = len(PREDICTORS)

IPC_PATTERN = re.compile(r"CPU 0 cumulative IPC:\s*([0-9.]+)")
MPKI_PATTERN = re.compile(r"Branch Prediction Accuracy:.*MPKI:\s*([0-9.]+)")


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
        help="Directory for branch_predictor_results.csv (default: current working directory)",
    )
    parser.add_argument(
        "-t",
        "--traces-dir",
        type=Path,
        default=None,
        help="Path to trace files (default: <champsim-dir>/traces)",
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
    mpki_match = MPKI_PATTERN.search(output)

    ipc = float(ipc_match.group(1)) if ipc_match else None
    mpki = float(mpki_match.group(1)) if mpki_match else None

    return ipc, mpki


def predictor_worker(
    predictor: str,
    champsim_dir: Path,
    traces_dir: Path,
    warmup_instructions: int,
    simulation_instructions: int,
):
    results = []

    print(f"[INFO] Starting worker for predictor: {predictor}")

    temp_dir = Path(tempfile.mkdtemp(prefix=f"champsim_{predictor}_"))

    print(f"[INFO] [{predictor}] Working directory: {temp_dir}")
    shutil.copytree(
        champsim_dir,
        temp_dir,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("traces"),
    )

    traces_symlink = temp_dir / "traces"
    traces_symlink.symlink_to(traces_dir, target_is_directory=True)

    config_path = temp_dir / "champsim_config.json"

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    if isinstance(config["ooo_cpu"], list):
        for cpu in config["ooo_cpu"]:
            cpu["branch_predictor"] = predictor
    else:
        config["ooo_cpu"]["branch_predictor"] = predictor

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

    print(f"[INFO] [{predictor}] Running config.sh")

    subprocess.run(
        ["./config.sh", "champsim_config.json"],
        check=True,
        cwd=temp_dir,
    )

    print(f"[INFO] [{predictor}] Building ChampSim")

    subprocess.run(
        ["make", "-j"],
        check=True,
        cwd=temp_dir,
    )

    traces = sorted(traces_dir.glob("*.xz"))

    for trace in traces:
        print(f"[INFO] [{predictor}] Running {trace.name}")

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
            ipc, mpki = parse_results(output)
            results.append({
                "trace": trace.name,
                "predictor": predictor,
                "IPC": ipc,
                "MPKI": mpki,
            })
            print(f"[RESULT] [{predictor}] {trace.name} IPC={ipc} MPKI={mpki}")

        except subprocess.CalledProcessError as e:
            print(f"[ERROR] [{predictor}] {trace.name} failed")
            print(e.stdout)

    print(f"[INFO] [{predictor}] Completed")

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
                predictor_worker,
                predictor,
                champsim_dir,
                traces_dir,
                args.warmup,
                args.sim,
            ): predictor
            for predictor in PREDICTORS
        }

        for future in as_completed(futures):
            predictor = futures[future]

            try:
                predictor_results = future.result()
                all_results.extend(predictor_results)

            except Exception as e:
                print(f"[ERROR] Worker failed for predictor {predictor}: {e}")

    output_csv = output_dir / "branch_predictor_results.csv"

    with open(output_csv, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=["trace", "predictor", "IPC", "MPKI"],
        )
        writer.writeheader()
        for row in all_results:
            writer.writerow(row)

    print("\n[INFO] All experiments completed.")
    print(f"[INFO] Results saved to: {output_csv}")


if __name__ == "__main__":
    main()
