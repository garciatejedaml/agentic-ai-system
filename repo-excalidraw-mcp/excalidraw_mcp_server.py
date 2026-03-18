#!/usr/bin/env python3
"""
Excalidraw MCP Server

Generates and manipulates .excalidraw diagram files so Claude can produce
architecture diagrams, flowcharts, and annotated sketches that open directly
in Excalidraw (https://excalidraw.com or the VS Code Excalidraw extension).

Tools
─────
  excalidraw_new            Create a new blank diagram file
  excalidraw_add_box        Add a labeled rectangle / ellipse / diamond
  excalidraw_add_arrow      Connect two elements with an arrow
  excalidraw_add_text       Add a standalone text label
  excalidraw_architecture   Generate a full architecture diagram from nodes + edges
  excalidraw_flowchart      Generate a top-down flowchart from steps
  excalidraw_read           Inspect an existing diagram (element summary)
  excalidraw_list           List .excalidraw files in a directory

Usage — Claude Code (stdio, recommended for local / VDI)
─────────────────────────────────────────────────────────
  Add to ~/.claude.json (or project .mcp.json):

    {
      "mcpServers": {
        "excalidraw": {
          "command": "python",
          "args": ["/absolute/path/to/excalidraw_mcp_server.py"],
          "env": {
            "DIAGRAMS_DIR": "/absolute/path/to/your/diagrams"
          }
        }
      }
    }

  Then ask Claude:
    "Create an architecture diagram showing the API, 3 microservices, and a DB"
    "Save it to ~/diagrams/api_arch.excalidraw"

Usage — HTTP mode (for MCP Gateway integration)
──────────────────────────────────────────────────
  MCP_TRANSPORT=http MCP_PORT=9105 python excalidraw_mcp_server.py
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server

logger = logging.getLogger(__name__)

# Default directory for saving diagrams (override via DIAGRAMS_DIR env var)
DIAGRAMS_DIR = os.getenv("DIAGRAMS_DIR", str(Path.home() / "diagrams"))

# ── Color palette ─────────────────────────────────────────────────────────────

COLORS: dict[str, str] = {
    "default":  "#e3f2fd",   # light blue  — general purpose
    "entry":    "#74c0fc",   # blue        — load balancer / API gateway
    "service":  "#b2f2bb",   # green       — microservices / agents
    "data":     "#ffd8a8",   # orange      — databases / queues / storage
    "external": "#e9ecef",   # gray        — third-party / external
    "warning":  "#ffe066",   # yellow      — optional / degraded path
    "error":    "#ffa8a8",   # red         — failure / timed-out
    "decision": "#d0ebff",   # light blue  — decision diamond
    "terminal": "#dee2e6",   # gray        — start / end oval
}

# ── Low-level element builders ────────────────────────────────────────────────

def _uid() -> str:
    return uuid.uuid4().hex[:16]


def _det_id(key: str) -> str:
    """Deterministic 16-char hex ID from a logical key (e.g. node id)."""
    return hashlib.md5(key.encode()).hexdigest()[:16]


def _seed() -> int:
    return int(time.time() * 1_000_000) % (2 ** 31)


def _now() -> int:
    return int(time.time() * 1000)


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", text.lower().strip())[:32]


def _make_box(
    element_id: str,
    label: str,
    x: int,
    y: int,
    width: int = 180,
    height: int = 80,
    color: str = "#e3f2fd",
    shape: str = "rectangle",  # rectangle | ellipse | diamond
) -> list[dict]:
    """
    Returns [container_element, bound_text_element].
    Text is bound to the container so Excalidraw centres it automatically.
    """
    text_id = f"t_{element_id}"
    now = _now()
    s1, s2 = _seed(), _seed() + 1

    roundness: dict | None
    if shape == "rectangle":
        roundness = {"type": 3}
    elif shape == "ellipse":
        roundness = {"type": 2}
    else:  # diamond — no roundness
        roundness = None

    container: dict = {
        "id": element_id,
        "type": shape,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "angle": 0,
        "strokeColor": "#1e1e1e",
        "backgroundColor": color,
        "fillStyle": "solid",
        "strokeWidth": 2,
        "strokeStyle": "solid",
        "roughness": 1,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "roundness": roundness,
        "seed": s1,
        "version": 1,
        "versionNonce": s1,
        "isDeleted": False,
        "boundElements": [{"type": "text", "id": text_id}],
        "updated": now,
        "link": None,
        "locked": False,
    }

    font_size = 14
    # Text centered inside the container
    text_el: dict = {
        "id": text_id,
        "type": "text",
        "x": x + 5,
        "y": y + (height - font_size * 1.25) / 2,
        "width": width - 10,
        "height": font_size * 1.25,
        "angle": 0,
        "strokeColor": "#1e1e1e",
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "strokeWidth": 1,
        "strokeStyle": "solid",
        "roughness": 1,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "roundness": None,
        "seed": s2,
        "version": 1,
        "versionNonce": s2,
        "isDeleted": False,
        "boundElements": None,
        "updated": now,
        "link": None,
        "locked": False,
        "text": label,
        "fontSize": font_size,
        "fontFamily": 1,
        "textAlign": "center",
        "verticalAlign": "middle",
        "baseline": font_size,
        "containerId": element_id,
        "originalText": label,
        "lineHeight": 1.25,
    }

    return [container, text_el]


def _make_arrow(
    arrow_id: str,
    from_id: str,
    from_cx: int,
    from_cy: int,
    to_id: str,
    to_cx: int,
    to_cy: int,
    label: str = "",
) -> list[dict]:
    """
    Arrow from the center of one element to the center of another.
    Excalidraw adjusts the endpoints to element boundaries when rendered.
    """
    now = _now()
    s = _seed()

    dx = to_cx - from_cx
    dy = to_cy - from_cy

    arrow: dict = {
        "id": arrow_id,
        "type": "arrow",
        "x": from_cx,
        "y": from_cy,
        "width": abs(dx),
        "height": abs(dy),
        "angle": 0,
        "strokeColor": "#495057",
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "strokeWidth": 2,
        "strokeStyle": "solid",
        "roughness": 1,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "roundness": {"type": 2},
        "seed": s,
        "version": 1,
        "versionNonce": s,
        "isDeleted": False,
        "boundElements": None,
        "updated": now,
        "link": None,
        "locked": False,
        "points": [[0, 0], [dx, dy]],
        "lastCommittedPoint": None,
        "startBinding": {"elementId": from_id, "focus": 0.0, "gap": 4},
        "endBinding":   {"elementId": to_id,   "focus": 0.0, "gap": 4},
        "startArrowhead": None,
        "endArrowhead": "arrow",
    }

    elements: list[dict] = [arrow]

    if label:
        lt = _uid()
        s2 = _seed()
        lx = from_cx + dx / 2 - 40
        ly = from_cy + dy / 2 - 10
        label_el: dict = {
            "id": lt,
            "type": "text",
            "x": lx,
            "y": ly,
            "width": 80,
            "height": 16,
            "angle": 0,
            "strokeColor": "#495057",
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 1,
            "strokeStyle": "solid",
            "roughness": 1,
            "opacity": 100,
            "groupIds": [],
            "frameId": None,
            "roundness": None,
            "seed": s2,
            "version": 1,
            "versionNonce": s2,
            "isDeleted": False,
            "boundElements": None,
            "updated": _now(),
            "link": None,
            "locked": False,
            "text": label,
            "fontSize": 12,
            "fontFamily": 1,
            "textAlign": "center",
            "verticalAlign": "top",
            "baseline": 12,
            "containerId": None,
            "originalText": label,
            "lineHeight": 1.25,
        }
        elements.append(label_el)

    return elements


def _make_standalone_text(
    text_id: str,
    text: str,
    x: int,
    y: int,
    font_size: int = 16,
    bold: bool = False,
) -> dict:
    s = _seed()
    font_family = 1  # 1=Virgil, 2=Helvetica, 3=Cascadia
    return {
        "id": text_id,
        "type": "text",
        "x": x,
        "y": y,
        "width": len(text) * font_size * 0.6,
        "height": font_size * 1.5,
        "angle": 0,
        "strokeColor": "#1e1e1e",
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "strokeWidth": 1,
        "strokeStyle": "solid",
        "roughness": 1,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "roundness": None,
        "seed": s,
        "version": 1,
        "versionNonce": s,
        "isDeleted": False,
        "boundElements": None,
        "updated": _now(),
        "link": None,
        "locked": False,
        "text": text,
        "fontSize": font_size,
        "fontFamily": font_family,
        "textAlign": "left",
        "verticalAlign": "top",
        "baseline": font_size,
        "containerId": None,
        "originalText": text,
        "lineHeight": 1.25,
    }


# ── File helpers ──────────────────────────────────────────────────────────────

def _empty_diagram() -> dict:
    return {
        "type": "excalidraw",
        "version": 2,
        "source": "https://excalidraw.com",
        "elements": [],
        "appState": {
            "gridSize": None,
            "viewBackgroundColor": "#ffffff",
        },
        "files": {},
    }


def _load(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(path: str, diagram: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(diagram, f, indent=2, ensure_ascii=False)


def _resolve_path(path: str) -> str:
    """Make relative paths relative to DIAGRAMS_DIR."""
    p = Path(path)
    if not p.is_absolute():
        p = Path(DIAGRAMS_DIR) / p
    if not p.suffix:
        p = p.with_suffix(".excalidraw")
    return str(p)


def _find_element(diagram: dict, element_id: str) -> dict | None:
    for el in diagram["elements"]:
        if el.get("id") == element_id:
            return el
    return None


def _center(el: dict) -> tuple[int, int]:
    return (
        int(el["x"] + el["width"] / 2),
        int(el["y"] + el["height"] / 2),
    )


def _fmt(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


# ── Tool implementations ──────────────────────────────────────────────────────

def tool_new(path: str, title: str = "") -> str:
    path = _resolve_path(path)
    diagram = _empty_diagram()
    if title:
        diagram["elements"].append(
            _make_standalone_text(_uid(), title, 20, 20, font_size=24, bold=True)
        )
    _save(path, diagram)
    return _fmt({"created": path, "title": title or "(untitled)"})


def tool_add_box(
    path: str,
    label: str,
    x: int = 100,
    y: int = 100,
    width: int = 180,
    height: int = 80,
    color: str = "default",
    shape: str = "rectangle",
    element_id: str = "",
) -> str:
    path = _resolve_path(path)
    diagram = _load(path)
    eid = element_id or _det_id(_slugify(label) + str(x) + str(y))
    bg = COLORS.get(color, color) if color in COLORS else color
    elements = _make_box(eid, label, x, y, width, height, bg, shape)
    diagram["elements"].extend(elements)
    _save(path, diagram)
    return _fmt({"element_id": eid, "label": label, "shape": shape, "x": x, "y": y})


def tool_add_arrow(
    path: str,
    from_id: str,
    to_id: str,
    label: str = "",
) -> str:
    path = _resolve_path(path)
    diagram = _load(path)

    src = _find_element(diagram, from_id)
    dst = _find_element(diagram, to_id)
    if src is None:
        return _fmt({"error": f"Element not found: {from_id}"})
    if dst is None:
        return _fmt({"error": f"Element not found: {to_id}"})

    arrow_id = _uid()
    elements = _make_arrow(
        arrow_id,
        from_id, *_center(src),
        to_id,   *_center(dst),
        label=label,
    )

    # Register arrow in both elements' boundElements lists
    for eid in (from_id, to_id):
        el = _find_element(diagram, eid)
        if el and isinstance(el.get("boundElements"), list):
            el["boundElements"].append({"type": "arrow", "id": arrow_id})
        elif el:
            el["boundElements"] = [{"type": "arrow", "id": arrow_id}]

    diagram["elements"].extend(elements)
    _save(path, diagram)
    return _fmt({"arrow_id": arrow_id, "from": from_id, "to": to_id, "label": label})


def tool_add_text(
    path: str,
    text: str,
    x: int = 100,
    y: int = 100,
    font_size: int = 16,
) -> str:
    path = _resolve_path(path)
    diagram = _load(path)
    tid = _uid()
    diagram["elements"].append(
        _make_standalone_text(tid, text, x, y, font_size)
    )
    _save(path, diagram)
    return _fmt({"text_id": tid, "text": text, "x": x, "y": y})


def tool_architecture(
    path: str,
    title: str,
    nodes: list[dict],
    edges: list[dict],
) -> str:
    """
    Auto-layout architecture diagram.

    nodes: [{"id": str, "label": str, "layer": int, "color": str, "shape": str}]
      layer 0 = entry (top), 1 = services (middle), 2 = data (bottom)
    edges: [{"from": str, "to": str, "label": str}]
    """
    # ── Layout ────────────────────────────────────────────────────────────────
    BOX_W, BOX_H = 180, 72
    H_GAP, V_GAP = 60, 80
    LAYER_Y = {0: 60, 1: 60 + BOX_H + V_GAP, 2: 60 + (BOX_H + V_GAP) * 2, 3: 60 + (BOX_H + V_GAP) * 3}
    LAYER_COLOR = {0: COLORS["entry"], 1: COLORS["service"], 2: COLORS["data"], 3: COLORS["external"]}

    # Group nodes by layer
    layers: dict[int, list[dict]] = {}
    for node in nodes:
        layer = int(node.get("layer", 1))
        layers.setdefault(layer, []).append(node)

    # Assign positions
    pos: dict[str, tuple[int, int, int, int]] = {}  # id -> (x, y, w, h)
    for layer_idx, layer_nodes in sorted(layers.items()):
        total_w = len(layer_nodes) * BOX_W + (len(layer_nodes) - 1) * H_GAP
        start_x = max(40, 500 - total_w // 2)
        y = LAYER_Y.get(layer_idx, 60 + layer_idx * (BOX_H + V_GAP))
        for i, node in enumerate(layer_nodes):
            x = start_x + i * (BOX_W + H_GAP)
            pos[node["id"]] = (x, y, BOX_W, BOX_H)

    # ── Build elements ────────────────────────────────────────────────────────
    diagram = _empty_diagram()
    if title:
        diagram["elements"].append(
            _make_standalone_text(_uid(), title, 40, 10, font_size=22, bold=True)
        )

    # Draw boxes
    el_ids: dict[str, str] = {}  # logical id -> element id
    for node in nodes:
        nid = node["id"]
        if nid not in pos:
            continue
        x, y, w, h = pos[nid]
        layer = int(node.get("layer", 1))
        default_color = LAYER_COLOR.get(layer, COLORS["default"])
        bg = COLORS.get(node.get("color", ""), node.get("color", default_color))
        if bg not in COLORS.values():
            bg = default_color
        shape = node.get("shape", "rectangle")
        eid = _det_id(nid)
        el_ids[nid] = eid
        diagram["elements"].extend(_make_box(eid, node["label"], x, y, w, h, bg, shape))

    # Draw arrows
    for edge in edges:
        src_nid = edge.get("from", "")
        dst_nid = edge.get("to", "")
        if src_nid not in pos or dst_nid not in pos:
            continue
        src_x, src_y, src_w, src_h = pos[src_nid]
        dst_x, dst_y, dst_w, dst_h = pos[dst_nid]
        cx_src = src_x + src_w // 2
        cy_src = src_y + src_h // 2
        cx_dst = dst_x + dst_w // 2
        cy_dst = dst_y + dst_h // 2
        arrow_id = _uid()
        diagram["elements"].extend(
            _make_arrow(
                arrow_id,
                el_ids[src_nid], cx_src, cy_src,
                el_ids[dst_nid], cx_dst, cy_dst,
                label=edge.get("label", ""),
            )
        )

    path_resolved = _resolve_path(path)
    _save(path_resolved, diagram)
    return _fmt({
        "saved": path_resolved,
        "nodes": len(nodes),
        "edges": len(edges),
        "element_ids": el_ids,
    })


def tool_flowchart(
    path: str,
    title: str,
    steps: list[dict],
    edges: list[dict] | None = None,
) -> str:
    """
    Top-down flowchart.

    steps: [{"id": str, "label": str, "type": "rect"|"diamond"|"oval"}]
    edges: optional explicit edges; defaults to sequential (each step → next)
    """
    BOX_W, BOX_H = 200, 72
    DIAMOND_W, DIAMOND_H = 220, 90
    V_GAP = 60
    START_X, START_Y = 300, 60

    SHAPE_MAP = {"rect": "rectangle", "diamond": "diamond", "oval": "ellipse"}
    COLOR_MAP = {
        "oval":    COLORS["terminal"],
        "diamond": COLORS["decision"],
        "rect":    COLORS["service"],
    }

    pos: dict[str, tuple[int, int, int, int]] = {}
    el_ids: dict[str, str] = {}
    diagram = _empty_diagram()
    if title:
        diagram["elements"].append(
            _make_standalone_text(_uid(), title, 40, 10, font_size=22, bold=True)
        )

    y = START_Y
    for step in steps:
        sid = step["id"]
        stype = step.get("type", "rect")
        shape = SHAPE_MAP.get(stype, "rectangle")
        w = DIAMOND_W if stype == "diamond" else BOX_W
        h = DIAMOND_H if stype == "diamond" else BOX_H
        x = START_X - w // 2
        eid = _det_id(sid)
        el_ids[sid] = eid
        pos[sid] = (x, y, w, h)
        color = COLOR_MAP.get(stype, COLORS["default"])
        diagram["elements"].extend(_make_box(eid, step["label"], x, y, w, h, color, shape))
        y += h + V_GAP

    # Build edge list (default: sequential)
    if edges:
        edge_list = edges
    else:
        edge_list = [
            {"from": steps[i]["id"], "to": steps[i + 1]["id"]}
            for i in range(len(steps) - 1)
        ]

    for edge in edge_list:
        src_nid = edge.get("from", "")
        dst_nid = edge.get("to", "")
        if src_nid not in pos or dst_nid not in pos:
            continue
        sx, sy, sw, sh = pos[src_nid]
        dx, dy, dw, dh = pos[dst_nid]
        diagram["elements"].extend(
            _make_arrow(
                _uid(),
                el_ids[src_nid], sx + sw // 2, sy + sh // 2,
                el_ids[dst_nid], dx + dw // 2, dy + dh // 2,
                label=edge.get("label", ""),
            )
        )

    path_resolved = _resolve_path(path)
    _save(path_resolved, diagram)
    return _fmt({
        "saved": path_resolved,
        "steps": len(steps),
        "edges": len(edge_list),
        "element_ids": el_ids,
    })


def tool_read(path: str) -> str:
    path = _resolve_path(path)
    try:
        diagram = _load(path)
    except FileNotFoundError:
        return _fmt({"error": f"File not found: {path}"})
    elements = diagram.get("elements", [])
    summary: list[dict] = []
    for el in elements:
        if el.get("isDeleted"):
            continue
        entry: dict = {"id": el["id"], "type": el["type"]}
        if el["type"] == "text":
            entry["text"] = el.get("text", "")[:80]
            entry["container"] = el.get("containerId")
        elif el["type"] in ("rectangle", "ellipse", "diamond"):
            entry["x"] = el.get("x")
            entry["y"] = el.get("y")
            entry["bound_elements"] = [b["id"] for b in (el.get("boundElements") or [])]
        elif el["type"] == "arrow":
            entry["from"] = (el.get("startBinding") or {}).get("elementId")
            entry["to"]   = (el.get("endBinding") or {}).get("elementId")
        summary.append(entry)
    return _fmt({
        "path": path,
        "element_count": len(summary),
        "elements": summary,
    })


def tool_list(directory: str = "") -> str:
    d = Path(directory) if directory else Path(DIAGRAMS_DIR)
    if not d.exists():
        return _fmt({"error": f"Directory not found: {d}", "tip": "Set DIAGRAMS_DIR or pass an absolute path."})
    files = sorted(d.rglob("*.excalidraw"))
    result = []
    for f in files:
        stat = f.stat()
        result.append({
            "path": str(f),
            "size_kb": round(stat.st_size / 1024, 1),
            "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime)),
        })
    return _fmt({"directory": str(d), "count": len(result), "files": result})


# ── MCP Server ────────────────────────────────────────────────────────────────

server = Server("excalidraw-mcp")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="excalidraw_new",
            description=(
                "Create a new blank .excalidraw file. "
                "Use this before adding elements with other tools, "
                "or use excalidraw_architecture / excalidraw_flowchart to build a full diagram in one call."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path (absolute or relative to DIAGRAMS_DIR). Extension .excalidraw added automatically.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Optional title text shown at the top of the diagram.",
                        "default": "",
                    },
                },
                "required": ["path"],
            },
        ),
        types.Tool(
            name="excalidraw_add_box",
            description=(
                "Add a labeled shape (rectangle, ellipse, or diamond) to an existing diagram. "
                "Returns the element_id needed for connecting arrows."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path":       {"type": "string", "description": "Path to the .excalidraw file."},
                    "label":      {"type": "string", "description": "Text displayed inside the shape."},
                    "x":          {"type": "integer", "description": "X position in pixels.", "default": 100},
                    "y":          {"type": "integer", "description": "Y position in pixels.", "default": 100},
                    "width":      {"type": "integer", "description": "Width in pixels.", "default": 180},
                    "height":     {"type": "integer", "description": "Height in pixels.", "default": 80},
                    "color":      {
                        "type": "string",
                        "description": "Background color. Use a palette key (default, entry, service, data, external, warning, error, decision, terminal) or a hex color.",
                        "default": "default",
                    },
                    "shape":      {
                        "type": "string",
                        "enum": ["rectangle", "ellipse", "diamond"],
                        "description": "Shape type.",
                        "default": "rectangle",
                    },
                    "element_id": {
                        "type": "string",
                        "description": "Optional stable ID. Auto-generated if omitted.",
                        "default": "",
                    },
                },
                "required": ["path", "label"],
            },
        ),
        types.Tool(
            name="excalidraw_add_arrow",
            description=(
                "Draw an arrow connecting two elements in a diagram. "
                "Use the element_id values returned by excalidraw_add_box."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path":     {"type": "string", "description": "Path to the .excalidraw file."},
                    "from_id":  {"type": "string", "description": "element_id of the source shape."},
                    "to_id":    {"type": "string", "description": "element_id of the target shape."},
                    "label":    {"type": "string", "description": "Optional label on the arrow.", "default": ""},
                },
                "required": ["path", "from_id", "to_id"],
            },
        ),
        types.Tool(
            name="excalidraw_add_text",
            description="Add a standalone text label to an existing diagram.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path":      {"type": "string"},
                    "text":      {"type": "string"},
                    "x":         {"type": "integer", "default": 100},
                    "y":         {"type": "integer", "default": 100},
                    "font_size": {"type": "integer", "description": "Font size in px.", "default": 16},
                },
                "required": ["path", "text"],
            },
        ),
        types.Tool(
            name="excalidraw_architecture",
            description=(
                "Generate a full architecture diagram in one call. "
                "Auto-lays out nodes by layer (0=entry, 1=services, 2=data, 3=external) "
                "and draws all arrows. Creates the file if it does not exist."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path":  {"type": "string", "description": "Output file path."},
                    "title": {"type": "string", "description": "Diagram title.", "default": ""},
                    "nodes": {
                        "type": "array",
                        "description": "List of service nodes.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id":    {"type": "string", "description": "Unique node identifier (used in edges)."},
                                "label": {"type": "string", "description": "Display name."},
                                "layer": {"type": "integer", "description": "Layout layer: 0=entry, 1=service, 2=data, 3=external.", "default": 1},
                                "color": {"type": "string", "description": "Palette key or hex color. Defaults to layer color.", "default": ""},
                                "shape": {"type": "string", "enum": ["rectangle", "ellipse", "diamond"], "default": "rectangle"},
                            },
                            "required": ["id", "label"],
                        },
                    },
                    "edges": {
                        "type": "array",
                        "description": "Arrows between nodes.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "from":  {"type": "string"},
                                "to":    {"type": "string"},
                                "label": {"type": "string", "default": ""},
                            },
                            "required": ["from", "to"],
                        },
                    },
                },
                "required": ["path", "nodes", "edges"],
            },
        ),
        types.Tool(
            name="excalidraw_flowchart",
            description=(
                "Generate a top-down flowchart. "
                "Use type=oval for start/end, type=diamond for decisions, type=rect for processes. "
                "Edges default to sequential if omitted."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path":  {"type": "string"},
                    "title": {"type": "string", "default": ""},
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id":    {"type": "string"},
                                "label": {"type": "string"},
                                "type":  {"type": "string", "enum": ["rect", "diamond", "oval"], "default": "rect"},
                            },
                            "required": ["id", "label"],
                        },
                    },
                    "edges": {
                        "type": "array",
                        "description": "Explicit edges. If omitted, steps connect sequentially.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "from":  {"type": "string"},
                                "to":    {"type": "string"},
                                "label": {"type": "string", "default": ""},
                            },
                            "required": ["from", "to"],
                        },
                    },
                },
                "required": ["path", "steps"],
            },
        ),
        types.Tool(
            name="excalidraw_read",
            description="Read and inspect an existing .excalidraw file. Returns a summary of all elements.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        ),
        types.Tool(
            name="excalidraw_list",
            description="List all .excalidraw files in a directory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Directory to scan. Defaults to DIAGRAMS_DIR.",
                        "default": "",
                    },
                },
                "required": [],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, _dispatch, name, arguments)
    except Exception as exc:
        logger.exception("[excalidraw] tool %s failed", name)
        result = _fmt({"error": str(exc), "tool": name})
    return [types.TextContent(type="text", text=result)]


def _dispatch(name: str, args: dict) -> str:  # noqa: PLR0911
    if name == "excalidraw_new":
        return tool_new(args["path"], args.get("title", ""))

    if name == "excalidraw_add_box":
        return tool_add_box(
            path=args["path"],
            label=args["label"],
            x=int(args.get("x", 100)),
            y=int(args.get("y", 100)),
            width=int(args.get("width", 180)),
            height=int(args.get("height", 80)),
            color=args.get("color", "default"),
            shape=args.get("shape", "rectangle"),
            element_id=args.get("element_id", ""),
        )

    if name == "excalidraw_add_arrow":
        return tool_add_arrow(
            path=args["path"],
            from_id=args["from_id"],
            to_id=args["to_id"],
            label=args.get("label", ""),
        )

    if name == "excalidraw_add_text":
        return tool_add_text(
            path=args["path"],
            text=args["text"],
            x=int(args.get("x", 100)),
            y=int(args.get("y", 100)),
            font_size=int(args.get("font_size", 16)),
        )

    if name == "excalidraw_architecture":
        return tool_architecture(
            path=args["path"],
            title=args.get("title", ""),
            nodes=args.get("nodes", []),
            edges=args.get("edges", []),
        )

    if name == "excalidraw_flowchart":
        return tool_flowchart(
            path=args["path"],
            title=args.get("title", ""),
            steps=args.get("steps", []),
            edges=args.get("edges") or None,
        )

    if name == "excalidraw_read":
        return tool_read(args["path"])

    if name == "excalidraw_list":
        return tool_list(args.get("directory", ""))

    return _fmt({"error": f"Unknown tool: {name}"})


# ── Entry point ───────────────────────────────────────────────────────────────

async def _stdio_main() -> None:
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "http":
        # HTTP/SSE mode for MCP Gateway integration
        sys.path.insert(0, str(Path(__file__).parent.parent / "repo-mcp-tools"))
        try:
            from mcp_http_server import run_http_server  # type: ignore
        except ImportError:
            print(
                "ERROR: mcp_http_server not found.\n"
                "Run from the repo root or set MCP_TRANSPORT=stdio (default).",
                file=sys.stderr,
            )
            sys.exit(1)

        _tools = [
            "excalidraw_new", "excalidraw_add_box", "excalidraw_add_arrow",
            "excalidraw_add_text", "excalidraw_architecture", "excalidraw_flowchart",
            "excalidraw_read", "excalidraw_list",
        ]
        run_http_server(server, server_id="excalidraw-mcp", tools=_tools,
                        port=int(os.getenv("MCP_PORT", "9105")))
    else:
        asyncio.run(_stdio_main())
