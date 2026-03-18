import argparse
import glob
import os
import subprocess
import sys
import time

RESULTS_DIR = "results"
LB_PORT = 9000
REPLICA_PORTS = [8001, 8002, 8003]
LOCUST_DURATION = "120s"
LOCUST_USERS = 20
LOCUST_SPAWN_RATE = 2
MODEL = "llama3.2:3b"

os.makedirs(RESULTS_DIR, exist_ok=True)


def clean_results():
    patterns = [
        f"{RESULTS_DIR}/lb_*_stats.csv",
        f"{RESULTS_DIR}/lb_*_stats_history.csv",
        f"{RESULTS_DIR}/lb_*_failures.csv",
        f"{RESULTS_DIR}/lb_*_exceptions.csv",
        f"{RESULTS_DIR}/fault_recovery_stats.csv",
        f"{RESULTS_DIR}/fault_recovery_stats_history.csv",
        f"{RESULTS_DIR}/fault_recovery_failures.csv",
        f"{RESULTS_DIR}/fault_recovery_exceptions.csv",
        f"{RESULTS_DIR}/fault_events.json",
    ]
    removed = 0
    for pattern in patterns:
        for path in glob.glob(pattern):
            if os.path.isfile(path):
                os.remove(path)
                removed += 1
    print(f"[runner] Cleaned {removed} file(s) from ./{RESULTS_DIR}/")


def start_replicas():
    procs = []
    for i, port in enumerate(REPLICA_PORTS, start=1):
        cmd = [
            sys.executable,
            "replica_server.py",
            "--port",
            str(port),
            "--replica-id",
            str(i),
            "--model",
            MODEL,
        ]
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append(p)
        print(f"[runner] Started replica {i} on port {port} (PID {p.pid})")
    print("[runner] Waiting 5s for replicas to initialize...")
    time.sleep(5)
    return procs


def stop_replicas(procs):
    for p in procs:
        stop_process(p)
    print("[runner] Stopped all replicas")


def start_load_balancer(strategy: str):
    replicas_arg = ",".join([f"http://localhost:{p}" for p in REPLICA_PORTS])
    cmd = [
        sys.executable,
        "load_balancer.py",
        "--strategy",
        strategy,
        "--port",
        str(LB_PORT),
        "--replicas",
        replicas_arg,
    ]
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"[runner] Started load balancer ({strategy}) on port {LB_PORT} (PID {p.pid})")
    time.sleep(3)
    return p


def stop_process(p):
    if p:
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait(timeout=3)


def run_locust(experiment_name: str):
    csv_prefix = f"{RESULTS_DIR}/{experiment_name}"
    cmd = [
        sys.executable,
        "-m",
        "locust",
        "-f",
        "locustfile.py",
        "--host",
        f"http://localhost:{LB_PORT}",
        "--headless",
        "-u",
        str(LOCUST_USERS),
        "-r",
        str(LOCUST_SPAWN_RATE),
        "--run-time",
        LOCUST_DURATION,
        "--csv",
        csv_prefix,
        "--csv-full-history",
    ]
    print(f"[runner] Running locust for experiment: {experiment_name}")
    result = subprocess.run(cmd)
    print(f"[runner] Locust finished for {experiment_name} (exit code {result.returncode})")
    return result.returncode


def experiment_load_balancing():
    strategies = ["round_robin", "least_connections", "random"]

    for strategy in strategies:
        print(f"\n{'=' * 50}")
        print(f"[runner] EXPERIMENT: Load Balancing — {strategy}")
        print(f"{'=' * 50}")

        replica_procs = start_replicas()
        lb_proc = start_load_balancer(strategy)
        try:
            rc = run_locust(f"lb_{strategy}")
            if rc != 0:
                raise RuntimeError(f"Locust failed for lb_{strategy} (exit code {rc})")
        finally:
            stop_process(lb_proc)
            stop_replicas(replica_procs)
        time.sleep(3)

    print("\n[runner] Load balancing experiments complete!")


def experiment_fault_recovery():
    print(f"\n{'=' * 50}")
    print("[runner] EXPERIMENT: Fault Recovery")
    print(f"{'=' * 50}")

    replica_procs = start_replicas()
    lb_proc = start_load_balancer("round_robin")
    fault_cmd = [
        sys.executable,
        "fault_injection.py",
        "--replica-port",
        "8002",
        "--replica-id",
        "2",
        "--delay",
        "30",
        "--restart-after",
        "15",
        "--log-file",
        f"{RESULTS_DIR}/fault_events.json",
        "--model",
        MODEL,
    ]
    fault_proc = subprocess.Popen(fault_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("[runner] Fault injection scheduled (kills replica 2 after 30s)")
    try:
        rc = run_locust("fault_recovery")
        if rc != 0:
            raise RuntimeError(f"Locust failed for fault_recovery (exit code {rc})")
    finally:
        stop_process(fault_proc)
        stop_process(lb_proc)
        stop_replicas(replica_procs)

    print("\n[runner] Fault recovery experiment complete!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("Team 2 Hydrazine — LLM Load Balancing & Fault Recovery")
    print("=" * 60)
    print("\nMake sure the following are running before starting:")
    print("  1. ollama serve")
    print("  2. ollama pull llama3.2:3b")
    print("\nStarting experiments...\n")

    try:
        if args.clean:
            clean_results()
        experiment_load_balancing()
        experiment_fault_recovery()
    except Exception as e:
        print(f"\n[runner] EXPERIMENT FAILED: {e}")
        sys.exit(1)

    print("\n[runner] ALL EXPERIMENTS COMPLETE!")
    print(f"[runner] Results saved to ./{RESULTS_DIR}/")
