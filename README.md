# Team 2 Hydrazine

Performance evaluation of load balancing and fault recovery in a multi-replica LLM serving system.

## What this project does

- Runs 3 local FastAPI LLM replicas backed by Ollama (`llama3.2:3b`)
- Routes traffic through a custom load balancer with 3 strategies:
  - `round_robin`
  - `least_connections`
  - `random`
- Generates mixed traffic with Locust
- Injects a replica fault and evaluates recovery behavior
- Saves CSV metrics and PNG plots for analysis/paper writing

## Architecture

```text
Locust (load generator)
        |
        v
Load Balancer :9000
(FastAPI + custom routing)
   |         |         |
   v         v         v
Replica1  Replica2  Replica3
:8001     :8002     :8003
   \         |         /
    \--------+--------/
             |
        Ollama :11434
       (llama3.2:3b)
```

## Prerequisites

- macOS or Linux
- Python 3.12+ (3.13 also works)
- [Ollama](https://ollama.com) installed

## Setup

```bash
# from project root
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Ollama model setup
ollama serve
ollama pull llama3.2:3b
```

## Quick start

```bash
source .venv/bin/activate
python run_experiments.py
python plot_results.py
```

This runs all experiments and writes:
- CSV outputs to `results/`
- Plot images to `plots/`

## Manual run (component-by-component)

```bash
# terminal 1
source .venv/bin/activate
python replica_server.py --port 8001 --replica-id 1

# terminal 2
source .venv/bin/activate
python replica_server.py --port 8002 --replica-id 2

# terminal 3
source .venv/bin/activate
python replica_server.py --port 8003 --replica-id 3

# terminal 4
source .venv/bin/activate
python load_balancer.py --strategy round_robin --port 9000

# terminal 5 (load test)
source .venv/bin/activate
locust -f locustfile.py --host http://localhost:9000 --headless -u 20 -r 2 --run-time 120s --csv results/manual_run --csv-full-history
```

## Fault injection

```bash
source .venv/bin/activate
python fault_injection.py --replica-port 8002 --replica-id 2 --delay 30 --restart-after 15 --log-file results/fault_events.json
```

## Output files

- `results/*_stats.csv` - aggregate locust metrics
- `results/*_stats_history.csv` - per-second history
- `results/fault_events.json` - fault/restart timestamps
- `plots/*.png` - generated charts

## Important notes

- Keep `ollama serve` running during experiments.
- First run can be slower because model + font caches warm up.
- Fault recovery quality depends on local machine load.
- `run_experiments.py` is strict: non-zero Locust exit now fails the run.

## Project files

- `replica_server.py` - replica service (`/health`, `/infer`)
- `load_balancer.py` - routing + health checks + retry/circuit-breaker
- `fault_injection.py` - targeted replica kill/restart
- `locustfile.py` - mixed request profile
- `run_experiments.py` - orchestration
- `plot_results.py` - figure generation
