import argparse
import random
import threading
import time
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI()

REPLICAS = [
    "http://localhost:8001",
    "http://localhost:8002",
    "http://localhost:8003",
]

STRATEGY = "round_robin"
FAILURE_THRESHOLD = 2

rr_index = 0
rr_lock = threading.Lock()
connections = {r: 0 for r in REPLICAS}
conn_lock = threading.Lock()
alive_replicas = set(REPLICAS)
alive_lock = threading.Lock()
failure_counts = {r: 0 for r in REPLICAS}
failure_lock = threading.Lock()


def mark_replica_dead(replica: str):
    with alive_lock:
        alive_replicas.discard(replica)
    print(f"[LB] Replica {replica} marked DEAD")


def mark_replica_alive(replica: str):
    with alive_lock:
        was_dead = replica not in alive_replicas
        alive_replicas.add(replica)
    with failure_lock:
        failure_counts[replica] = 0
    if was_dead:
        print(f"[LB] Replica {replica} is back ONLINE")


def record_failure(replica: str):
    with failure_lock:
        failure_counts[replica] = failure_counts.get(replica, 0) + 1
        count = failure_counts[replica]
    if count >= FAILURE_THRESHOLD:
        mark_replica_dead(replica)


def record_success(replica: str):
    with failure_lock:
        failure_counts[replica] = 0


def health_check_loop():
    while True:
        for replica in list(REPLICAS):
            try:
                r = httpx.get(f"{replica}/health", timeout=1.0)
                if r.status_code == 200:
                    mark_replica_alive(replica)
                else:
                    record_failure(replica)
            except Exception:
                record_failure(replica)
        time.sleep(0.5)


def get_alive():
    with alive_lock:
        return list(alive_replicas)


def pick_replica_round_robin(candidates=None):
    global rr_index
    alive = candidates if candidates is not None else get_alive()
    if not alive:
        return None
    with rr_lock:
        replica = alive[rr_index % len(alive)]
        rr_index += 1
    return replica


def pick_replica_least_connections(candidates=None):
    alive = candidates if candidates is not None else get_alive()
    if not alive:
        return None
    with conn_lock:
        return min(alive, key=lambda r: connections.get(r, 0))


def pick_replica_random(candidates=None):
    alive = candidates if candidates is not None else get_alive()
    if not alive:
        return None
    return random.choice(alive)


def pick_replica(exclude=None):
    alive = get_alive()
    if exclude:
        alive = [r for r in alive if r != exclude]
    if not alive:
        return None
    if STRATEGY == "round_robin":
        return pick_replica_round_robin(alive)
    elif STRATEGY == "least_connections":
        return pick_replica_least_connections(alive)
    elif STRATEGY == "random":
        return pick_replica_random(alive)
    return pick_replica_round_robin(alive)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "strategy": STRATEGY,
        "alive_replicas": get_alive(),
        "total_replicas": len(REPLICAS),
        "connections": dict(connections),
        "failure_counts": dict(failure_counts)
    }


@app.post("/infer")
async def infer(request: Request):
    body = await request.json()
    replica = pick_replica()

    if replica is None:
        raise HTTPException(status_code=503, detail="No replicas available")

    with conn_lock:
        connections[replica] = connections.get(replica, 0) + 1

    primary_decremented = False

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{replica}/infer", json=body)
            resp.raise_for_status()
            data = resp.json()
            record_success(replica)
    except Exception as e:
        record_failure(replica)
        with conn_lock:
            connections[replica] = max(0, connections.get(replica, 1) - 1)
        primary_decremented = True
        retry_replica = pick_replica(exclude=replica)
        if retry_replica:
            with conn_lock:
                connections[retry_replica] = connections.get(retry_replica, 0) + 1
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(f"{retry_replica}/infer", json=body)
                    resp.raise_for_status()
                    data = resp.json()
                    record_success(retry_replica)
                    data["retried"] = True
            except Exception as e2:
                record_failure(retry_replica)
                raise HTTPException(status_code=503, detail=f"All replicas failed: {str(e2)}")
            finally:
                with conn_lock:
                    connections[retry_replica] = max(0, connections.get(retry_replica, 1) - 1)
        else:
            raise HTTPException(status_code=503, detail=f"Replica error, no fallback: {str(e)}")
    finally:
        if not primary_decremented:
            with conn_lock:
                connections[replica] = max(0, connections.get(replica, 1) - 1)

    data["lb_strategy"] = STRATEGY
    return JSONResponse(content=data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", type=str, default="round_robin",
                        choices=["round_robin", "least_connections", "random"])
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--replicas", type=str, default="")
    args = parser.parse_args()

    STRATEGY = args.strategy
    if args.replicas:
        REPLICAS.clear()
        REPLICAS.extend(args.replicas.split(","))
        connections.update({r: 0 for r in REPLICAS})
        alive_replicas.update(REPLICAS)
        failure_counts.update({r: 0 for r in REPLICAS})

    t = threading.Thread(target=health_check_loop, daemon=True)
    t.start()

    print(f"[LB] Strategy={STRATEGY} | Replicas={REPLICAS}")
    print(f"[LB] Health check: 0.5s interval | Failure threshold: {FAILURE_THRESHOLD}")
    uvicorn.run(app, host="0.0.0.0", port=args.port)