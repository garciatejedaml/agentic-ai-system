"""Heuristic + LLM classifier for Jira tickets → Carson agent.

The router decides whether an incoming Jira ticket belongs to:
  - athena.{bob,hydra,csb,pixie,studio,sdlc,aquiles}  (knowledge agents)
  - coder.{aquiles,sdlc}                              (autonomous coders)
  - infra                                             (terraform / pipelines)
  - docs                                              (confluence)

Two backends, same return shape:
  1. heuristic — fast, deterministic, runs on keywords + repo name. Default.
  2. haiku     — drop-in slot for `claude-haiku-4-5` via CDAOSDK / Bedrock.
                 Enabled with CARSON_CLASSIFIER_BACKEND=haiku.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, asdict
from typing import Any


ATHENA_AGENTS = ["bob", "hydra", "csb", "pixie", "studio", "sdlc", "aquiles"]
CODER_AGENTS = ["aquiles", "sdlc"]

ATHENA_KEYWORDS = {
    "bob":     ["bob", "borrowing", "rates engine"],
    "hydra":   ["hydra", "credit-decision", "decision engine"],
    "csb":     ["csb", "credit syndicate", "syndicate book"],
    "pixie":   ["pixie", "pricing", "pricing tier"],
    "studio":  ["studio", "ml studio", "feature store"],
    "sdlc":    ["sdlc", "release index", "ci index"],
    "aquiles": ["aquiles", "knowledge index", "code index"],
}

ATHENA_SIGNALS = ["reindex", "re-sync", "resync", "vectoriz", "embed", "knowledge", "ingest"]
CODER_SIGNALS  = ["fix", "patch", "bug", "endpoint", "field", "validation", "service", "svc", "api"]
INFRA_SIGNALS  = ["terraform", "tfstate", "pipeline", "jenkins", "spinnaker", "vpc", "iam", "infra"]
DOCS_SIGNALS   = ["runbook", "release notes", "documentation", "confluence"]


@dataclass
class Classification:
    track: str          # athena | coder | infra | docs | unknown
    agent: str          # bob | hydra | aquiles | sdlc | infra | docs | unknown
    confidence: float   # 0.0 – 1.0
    signals: list[str]  # human-readable reasons (+ matched / − missing)
    backend: str        # heuristic | haiku

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify(ticket: dict[str, Any]) -> Classification:
    """Top-level classifier. Reads CARSON_CLASSIFIER_BACKEND for routing."""
    backend = os.environ.get("CARSON_CLASSIFIER_BACKEND", "heuristic").lower()
    if backend == "haiku":
        try:
            return classify_via_haiku(ticket)
        except Exception:
            pass  # graceful fallback
    return classify_heuristic(ticket)


# ── Heuristic backend ──────────────────────────────────────────────────────


def classify_heuristic(ticket: dict[str, Any]) -> Classification:
    text = " ".join([
        str(ticket.get("summary", "")),
        str(ticket.get("description", "")),
        str(ticket.get("project", "")),
        " ".join(ticket.get("labels", []) or []),
        str(ticket.get("repo", "")),
    ]).lower()

    signals: list[str] = []
    scores = {"athena": 0, "coder": 0, "infra": 0, "docs": 0}
    chosen_agent = "unknown"

    # Athena name + signals
    athena_hits: list[str] = []
    for agent, kws in ATHENA_KEYWORDS.items():
        if any(kw in text for kw in kws):
            athena_hits.append(agent)
    for sig in ATHENA_SIGNALS:
        if sig in text:
            scores["athena"] += 1
            signals.append(f'+ "{sig}" → athena track')
    if athena_hits:
        scores["athena"] += 2
        signals.append(f'+ agent name "{athena_hits[0]}" matched')

    # Coder
    for sig in CODER_SIGNALS:
        if re.search(rf"\b{re.escape(sig)}\b", text):
            scores["coder"] += 1
            signals.append(f'+ "{sig}" → coder track')
    repo = (ticket.get("repo") or "").lower()
    if any(svc in repo for svc in ["payments", "risk", "credit", "order"]):
        scores["coder"] += 2
        signals.append(f'+ repo "{repo}" → coder')

    # Infra — terraform/pipeline strongly bias infra; repo prefixed "infra-" too
    for sig in INFRA_SIGNALS:
        if sig in text:
            weight = 2 if sig in ("terraform", "tfstate") else 1
            scores["infra"] += weight
            signals.append(f'+ "{sig}" → infra')
    if repo.startswith("infra-") or repo.startswith("tf-"):
        scores["infra"] += 2
        signals.append(f'+ repo "{repo}" → infra')

    # Docs
    for sig in DOCS_SIGNALS:
        if sig in text:
            scores["docs"] += 1
            signals.append(f'+ "{sig}" → docs')

    track = max(scores, key=scores.get) if max(scores.values()) > 0 else "unknown"
    total = sum(scores.values()) or 1
    confidence = scores[track] / total

    if track == "athena":
        chosen_agent = athena_hits[0] if athena_hits else "bob"
    elif track == "coder":
        chosen_agent = "sdlc" if any(s in text for s in ["release", "build", "pipeline"]) else "aquiles"
    elif track == "infra":
        chosen_agent = "infra"
    elif track == "docs":
        chosen_agent = "docs"

    if not signals:
        signals.append("− no strong signals matched")

    return Classification(
        track=track,
        agent=chosen_agent,
        confidence=round(confidence, 2),
        signals=signals,
        backend="heuristic",
    )


# ── Haiku backend (Bedrock via CDAOSDK) ────────────────────────────────────


def classify_via_haiku(ticket: dict[str, Any]) -> Classification:
    """Drop-in for Claude Haiku 4.5 via CDAOSDK / Bedrock.

    To enable on the VDI:
        pip install cdao-sdk            # per Carson's existing install
        export CARSON_CLASSIFIER_BACKEND=haiku
        export CARSON_BEDROCK_REGION=us-east-1
    """
    try:
        from cdao_sdk.bedrock import BedrockClient  # type: ignore
    except Exception as e:
        raise RuntimeError("cdao-sdk not available — using heuristic") from e

    client = BedrockClient(region=os.environ.get("CARSON_BEDROCK_REGION", "us-east-1"))
    summary = ticket.get("summary", "")
    description = ticket.get("description", "")
    repo = ticket.get("repo", "")
    labels = ", ".join(ticket.get("labels", []) or [])

    prompt = (
        "You are a router for Carson, a JPMC AI orchestrator. Decide which "
        "track this Jira ticket belongs to.\n\n"
        "Tracks:\n"
        "- athena.<bob|hydra|csb|pixie|studio|sdlc|aquiles> — knowledge / index work\n"
        "- coder.<aquiles|sdlc> — autonomous code changes to a service\n"
        "- infra — terraform, pipelines, IAM, VPC\n"
        "- docs — runbooks, release notes\n\n"
        f"Ticket: {summary}\n"
        f"Description: {description[:500]}\n"
        f"Repo: {repo}\n"
        f"Labels: {labels}\n\n"
        'Return JSON only: {"track":"...","agent":"...","confidence":0.0-1.0,'
        '"signals":["+ ...","- ..."]}'
    )
    out = client.invoke(
        model_id="anthropic.claude-haiku-4-5-v1:0",
        prompt=prompt,
        max_tokens=200,
    )
    parsed = json.loads(out.strip())
    return Classification(
        track=parsed.get("track", "unknown"),
        agent=parsed.get("agent", "unknown"),
        confidence=float(parsed.get("confidence", 0.5)),
        signals=parsed.get("signals", []),
        backend="haiku",
    )
