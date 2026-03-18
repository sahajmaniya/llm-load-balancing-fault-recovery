import argparse
import subprocess
import time
import signal
import os
import json
import sys
from datetime import datetime, timezone


def find_listener_pid_on_port(port: int):
    try:
        result = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True, text=True
        )
        pid = result.stdout.strip().split("\n")[0]
        if pid.isdigit():
            return int(pid)
        return None
    except Exception as e:
        print(f"[fault] Error finding PID: {e}")
        return None


def wait_for_exit(pid: int, timeout_s: float = 3.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except Exception:
            return False
        time.sleep(0.1)
    return False


def kill_replica(port: int):
    pid = find_listener_pid_on_port(port)
    if pid is None:
        print(f"[fault] No process found on port {port}")
        return False

    try:
        os.kill(pid, signal.SIGTERM)
        if not wait_for_exit(pid, timeout_s=3.0):
            os.kill(pid, signal.SIGKILL)
            wait_for_exit(pid, timeout_s=1.0)
        print(f"[fault] Killed replica PID {pid} on port {port}")
    except Exception as e:
        print(f"[fault] Could not kill PID {pid}: {e}")
        return False

    return True


def restart_replica(port: int, replica_id: int, model: str = "llama3.2:3b"):
    cmd = [
        sys.executable, "replica_server.py",
        "--port", str(port),
        "--replica-id", str(replica_id),
        "--model", model
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"[fault] Restarted replica {replica_id} on port {port} (PID {proc.pid})")
    return proc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--replica-port", type=int, default=8002,
                        help="Port of replica to kill")
    parser.add_argument("--replica-id", type=int, default=2,
                        help="Replica ID (for restart)")
    parser.add_argument("--delay", type=float, default=30.0,
                        help="Seconds to wait before killing replica")
    parser.add_argument("--restart-after", type=float, default=15.0,
                        help="Seconds after kill to restart (0 = no restart)")
    parser.add_argument("--log-file", type=str, default="fault_events.json",
                        help="File to log fault events with timestamps")
    parser.add_argument("--model", type=str, default="llama3.2:3b")
    args = parser.parse_args()

    events = []

    print(f"[fault] Waiting {args.delay}s before injecting fault on port {args.replica_port}...")
    time.sleep(args.delay)
    fault_time = time.time()
    fault_ts = datetime.now(timezone.utc).isoformat()
    success = kill_replica(args.replica_port)

    event = {
        "event": "fault_injected",
        "timestamp": fault_ts,
        "unix_time": fault_time,
        "port": args.replica_port,
        "success": success
    }
    events.append(event)
    print(f"[fault] Fault injected at {fault_ts}")

    if args.restart_after > 0:
        print(f"[fault] Waiting {args.restart_after}s before restarting replica...")
        time.sleep(args.restart_after)

        restart_time = time.time()
        restart_ts = datetime.now(timezone.utc).isoformat()
        restart_replica(args.replica_port, args.replica_id, args.model)

        event2 = {
            "event": "replica_restarted",
            "timestamp": restart_ts,
            "unix_time": restart_time,
            "port": args.replica_port,
            "recovery_time_s": restart_time - fault_time
        }
        events.append(event2)
        print(f"[fault] Replica restarted at {restart_ts} "
              f"(recovery time: {restart_time - fault_time:.1f}s)")
    os.makedirs(os.path.dirname(args.log_file) or ".", exist_ok=True)
    with open(args.log_file, "w") as f:
        json.dump(events, f, indent=2)
    print(f"[fault] Events saved to {args.log_file}")


if __name__ == "__main__":
    main()
