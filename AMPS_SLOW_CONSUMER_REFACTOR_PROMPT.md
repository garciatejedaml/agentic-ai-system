# AMPS Slow Consumer Refactor — Copilot Execution Prompt

**Context**: Upgrading `amps-python-client` from 5.3.4.3 to 5.3.5.1 exposed a pre-existing slow-consumer problem. The consumer is CPU-bound (Python), holds the GIL during message processing, causes AMPS heartbeat timeouts, triggers disconnects, and under `HAClient` + `DefaultServerChooser` creates a death-loop of reconnect/SOW-replay.

**Goal**: Refactor from callback-based `sow_and_subscribe` to pull-based `MessageStream` + `ProcessPoolExecutor` to (a) free the AMPS transport thread from Python user code, (b) parallelize CPU-bound processing across processes (bypassing the GIL), and (c) preserve `batch_size=10` as a hard business constraint.

---

## Prompt to paste into Copilot

```
Refactor the AMPS consumer in this codebase from callback-based `sow_and_subscribe` to pull-based `MessageStream` + `ProcessPoolExecutor`, to fix heartbeat disconnects caused by a slow CPU-bound handler under the Python GIL.

## Context

- AMPS Python client: `amps-python-client==5.3.5.1` (recently upgraded from 5.3.4.3).
- Connection: `HAClient` with `DefaultServerChooser` + reconnect delay strategy.
- Subscription: currently uses `client.sow_and_subscribe(handler, topic, options="batch_size=10")`.
- `batch_size=10` is a hard business constraint — do NOT change it.
- The message handler does CPU-bound Python work that holds the GIL.
- Symptom: heartbeat timeouts cause the server to disconnect the client; on reconnect the full SOW replays, which creates a death-loop of disconnect/reconnect under load.

## Root cause (state it, don't explain it back to me)

With callback-based subscriptions, the user handler runs on the AMPS transport thread. CPU-bound Python code holds the GIL for the full processing duration, which:
1. Blocks AMPS from delivering subsequent messages.
2. Fills internal queues.
3. Interferes with heartbeat timing.

Threads don't help because of GIL contention. The fix requires (a) decoupling the handler from the AMPS transport thread and (b) running heavy work in separate processes.

## Target architecture

from concurrent.futures import ProcessPoolExecutor
from collections import deque
from AMPS import HAClient

def process_message(data):
    """Runs in a separate process. CPU-bound work goes here."""
    # ... existing handler logic ...
    return result

def main():
    client = HAClient("my-client")
    client.set_server_chooser(...)                 # preserve existing chooser
    client.set_reconnect_delay_strategy(...)       # preserve existing policy
    client.set_heartbeat(10, 120)                  # interval 10s, timeout 120s — margin for submit() blocking
    client.connect_and_logon()

    pool = ProcessPoolExecutor(max_workers=4)
    MAX_INFLIGHT = 20                              # backpressure window
    inflight = deque()

    stream = client.execute_async(
        "sow_and_subscribe",
        topic="...",                               # preserve existing topic
        filter="...",                              # preserve existing filter if any
        options="batch_size=10",                   # HARD CONSTRAINT: keep 10
    )

    try:
        for message in stream:
            # Main-thread extraction (Message objects are not picklable)
            data = message.get_data()
            topic = message.get_topic()
            key = message.get_sow_key() if has_sow else None

            # Backpressure: block submit when too many futures are inflight.
            # This propagates to AMPS: stream iteration pauses → AMPS waits.
            while len(inflight) >= MAX_INFLIGHT:
                inflight.popleft().result()        # blocks until one completes; raises if that worker failed

            future = pool.submit(process_message, data)
            inflight.append(future)
    finally:
        for f in inflight:
            f.result()
        pool.shutdown(wait=True)

if __name__ == "__main__":
    main()

## Why this works

- The AMPS transport thread is never blocked by user code → heartbeats always succeed.
- `pool.submit` copies data to a worker process via pickle → each worker has its own GIL → true CPU parallelism.
- `MAX_INFLIGHT` bounds memory and provides backpressure to the AMPS stream.
- `batch_size=10` still controls per-batch delivery; the change is where processing happens, not how much.

## Tasks

1. Locate the current `sow_and_subscribe` call site(s) in this codebase.
2. Refactor to the pattern above. Preserve:
   - Topic, filter, options (except options must keep `batch_size=10`).
   - Server chooser, reconnect delay strategy, and any authentication/SSL config.
   - All business logic currently in the handler — move it verbatim into `process_message`.
3. Extract all needed fields from the `Message` object in the main thread BEFORE submitting (e.g., `get_data()`, `get_sow_key()`, `get_topic()`, `get_command()`, `get_bookmark()` if used). Do NOT pass the `Message` object itself to the worker — it is not picklable and the buffer may be reused by the client.
4. Handle the SOW-vs-live phase distinction if the existing handler depends on it:
   - `command == "group_begin"` / `command == "group_end"` markers
   - `command == "sow"` (record from initial state)
   - `command in ("publish", "oof")` (live update, out-of-focus)
   If the handler dispatches on these, preserve that routing inside `process_message` or at the stream level (dispatch to different worker functions accordingly).
5. Add structured logging:
   - Time spent per message (via `time.monotonic()` around `pool.submit` vs `future.result()`).
   - Queue depth (`len(inflight)`).
   - Worker failures (`future.result()` exceptions).
6. Add a clean shutdown path that drains inflight futures and calls `pool.shutdown(wait=True)` on SIGTERM/SIGINT.
7. Keep a commented link to this prompt in the file header for future maintainers.

## Constraints

- Do NOT modify `batch_size`; it must remain `10`.
- Do NOT remove the HAClient / DefaultServerChooser setup.
- Do NOT introduce asyncio — use synchronous pull-based iteration over the stream.
- Do NOT share mutable state between workers — each worker process is independent. If the old handler relied on module-level caches, DB connections, or global state, each worker must initialize its own in an initializer function passed to `ProcessPoolExecutor(initializer=...)`.
- Preserve existing bookmark / replay semantics if the consumer uses them for resume-on-reconnect.

## Verification

After the refactor, run the consumer under load and confirm:
- No heartbeat timeouts in logs for at least 30 minutes of sustained processing.
- CPU utilization across N cores (not just one) while processing.
- `htop` or `ps` shows `max_workers` child Python processes.
- If you kill one worker, the main process continues and re-uses other workers (pool auto-recovers).

## What to ask me before writing code

- How many cores are available on the VDI? (to set `max_workers` appropriately)
- Is there shared state the old handler relied on? (DB connections, caches, config)
- Does the handler publish back to AMPS? If yes, that publish should happen from the main thread after `future.result()`, not from inside the worker process.

Start by showing me the current `sow_and_subscribe` call site and the handler function. Don't refactor yet — I want to confirm the plan fits the existing code before you change anything.
```

---

## How to use this

1. Clone or pull this repo in your VDI.
2. Open the file in your codebase that contains the `sow_and_subscribe` call (or open the broader project in Copilot Chat workspace mode).
3. Paste the prompt above into Copilot Chat.
4. Copilot will first ask to see the existing code — show it the file(s).
5. It will propose a refactor plan; review it, confirm or correct the plan.
6. Only after you OK the plan, let it write the code.
7. Apply the "Verification" checks before committing to main.

## Background / rationale

The issue is not the AMPS client version per se — `5.3.4.3 → 5.3.5.1` skipped ~16 months of changes, and `5.3.5.0` in particular changed disconnect/reconnect semantics. That change **exposed** a pre-existing slow-consumer problem. The old reconnect behavior was lazier, masking the heartbeat timeouts. The new behavior is more aggressive, so the same slow handler now causes an observable death-loop.

The proper fix is not to downgrade — downgrading just hides the symptom. The proper fix is to stop blocking the AMPS transport thread with CPU-bound Python work. `MessageStream` + `ProcessPoolExecutor` is the idiomatic way to do that in Python: pull-based iteration keeps the transport thread free, and process-based parallelism bypasses the GIL entirely.

## Related documents

- `CARSON_TIER1_FIXES.md` through `CARSON_TIER4_FIXES.md` — broader Carson improvement backlog
- `CARSON_SELF_IMPROVEMENT_EXECUTION.md` — how to run Tier 1 fixes via Copilot
- `CARSON_COPILOT_STRATEGY.md` — Copilot integration strategy
