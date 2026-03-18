"""
run_experiments.py
Orchestrates all experiments:
  1. Load balancing comparison (round_robin vs least_connections vs random)
  2. Fault recovery experiment (kill a replica mid-load)

Prerequisites:
  - Ollama running: `ollama serve`
  - Model pulled: `ollama pull llama3.2:3b`
  - Replicas running on ports 8001, 8002, 8003
  - Load balancer running on port 9000

Usage:
    python run_experiments.py
"""

import subprocess
import time
import os
import sys

RESULTS_DIR = "results"
LB_PORT = 9000
REPLICA_PORTS = [8001, 8002, 8003]
LOCUST_DURATION = "120s"
LOCUST_USERS = 20
LOCUST_SPAWN_RATE = 2
MODEL = "llama3.2:3b"

os.makedirs(RESULTS_DIR, exist_ok=True)


def start_replicas():
    procs = []
    for i, port in enumerate(REPLICA_PORTS, start=1):
        cmd = [
            sys.executable, "replica_server.py",
            "--port", str(port),
            "--replica-id", str(i),
            "--model", MODEL
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
        sys.executable, "load_balancer.py",
        "--strategy", strategy,
        "--port", str(LB_PORT),
        "--replicas", replicas_arg
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
        sys.executable, "-m", "locust",
        "-f", "locustfile.py",
        "--host", f"http://localhost:{LB_PORT}",
        "--headless",
        "-u", str(LOCUST_USERS),
        "-r", str(LOCUST_SPAWN_RATE),
        "--run-time", LOCUST_DURATION,
        "--csv", csv_prefix,
        "--csv-full-history"
    ]
    print(f"[runner] Running locust for experiment: {experiment_name}")
    result = subprocess.run(cmd)
    print(f"[runner] Locust finished for {experiment_name} (exit code {result.returncode})")
    return result.returncode


def experiment_load_balancing():
    """Compare 3 load balancing strategies."""
    strategies = ["round_robin", "least_connections", "random"]

    for strategy in strategies:
        print(f"\n{'='*50}")
        print(f"[runner] EXPERIMENT: Load Balancing — {strategy}")
        print(f"{'='*50}")

        replica_procs = start_replicas()
        lb_proc = start_load_balancer(strategy)
        try:
            rc = run_locust(f"lb_{strategy}")
            if rc != 0:
                raise RuntimeError(f"Locust failed for lb_{strategy} (exit code {rc})")
        finally:
            stop_process(lb_proc)
            stop_replicas(replica_procs)
        time.sleep(3)  # Cool down between experiments

    print("\n[runner] Load balancing experiments complete!")


def experiment_fault_recovery():
    """Test fault recovery with round_robin (default)."""
    print(f"\n{'='*50}")
    print(f"[runner] EXPERIMENT: Fault Recovery")
    print(f"{'='*50}")

    replica_procs = start_replicas()
    lb_proc = start_load_balancer("round_robin")

    # Start fault injection in background (kills replica 2 after 30s)
    fault_cmd = [
        sys.executable, "fault_injection.py",
        "--replica-port", "8002",
        "--replica-id", "2",
        "--delay", "30",
        "--restart-after", "15",
        "--log-file", f"{RESULTS_DIR}/fault_events.json",
        "--model", MODEL
    ]
    fault_proc = subprocess.Popen(fault_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"[runner] Fault injection scheduled (kills replica 2 after 30s)")

    # Run locust for 120s — fault happens at 30s
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
    print("=" * 60)
    print("Team 2 Hydrazine — LLM Load Balancing & Fault Recovery")
    print("=" * 60)
    print("\nMake sure the following are running before starting:")
    print("  1. ollama serve")
    print("  2. ollama pull llama3.2:3b")
    print("\nStarting experiments...\n")

    try:
        experiment_load_balancing()
        experiment_fault_recovery()
    except Exception as e:
        print(f"\n[runner] EXPERIMENT FAILED: {e}")
        sys.exit(1)

    print("\n[runner] ALL EXPERIMENTS COMPLETE!")
    print(f"[runner] Results saved to ./{RESULTS_DIR}/")
