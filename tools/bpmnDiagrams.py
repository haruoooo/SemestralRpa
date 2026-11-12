"""Generates the BPMN 2.0 diagrams of the three flows from one description (docs/processDesign.md).

Outputs, per flow, in docs/bpmn/:
  <flow>.bpmn  BPMN 2.0 XML with diagram interchange (opens in bpmn.io / Camunda Modeler)
  <flow>.svg   Rendered picture used in the PDF report

Run:  python -m tools.bpmnDiagrams
"""

import sys
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

# ---------- Layout constants (pixels) ----------

COLUMN = 122
ROW = 132
POOL_HEADER = 34
LANE_HEADER = 30
LEFT = POOL_HEADER + LANE_HEADER + 10
TOP = 20
TASK_W, TASK_H = 106, 66
EVENT_R = 17
GATEWAY_HALF = 23
EXTERNAL_POOL_H = 46
FONT = 11
LINE_HEIGHT = 13
CHAR_W = 5.9

INK = "#1d2a3a"
ROBOT_FILL = "#eef4fb"
HUMAN_FILL = "#fff6e5"
SUBPROCESS_FILL = "#f7fafd"


@dataclass
class Node:
    id: str
    kind: str  # start, timerStart, messageStart, end, errorEnd, task, userTask, serviceTask, sendTask, gateway, dataStore
    label: str
    col: float
    row: float
    lane: str = ""
    parent: str | None = None  # Subprocess id
    fixedCenter: tuple[float, float] | None = None  # Subprocess proxies: geometry from the subprocess box
    fixedHalf: tuple[float, float] | None = None

    @property
    def center(self) -> tuple[float, float]:
        if self.fixedCenter:
            return self.fixedCenter
        return LEFT + self.col * COLUMN + COLUMN / 2, TOP + self.row * ROW + ROW / 2

    @property
    def half(self) -> tuple[float, float]:
        if self.fixedHalf:
            return self.fixedHalf
        if self.kind in ("task", "userTask", "serviceTask", "sendTask"):
            return TASK_W / 2, TASK_H / 2
        if self.kind == "gateway":
            return GATEWAY_HALF, GATEWAY_HALF
        if self.kind == "dataStore":
            return 25, 22
        return EVENT_R, EVENT_R

    def box(self) -> tuple[float, float, float, float]:
        (x, y), (hw, hh) = self.center, self.half
        return x - hw, y - hh, hw * 2, hh * 2


@dataclass
class SubProcess:
    id: str
    label: str
    col0: float
    col1: float
    row0: float
    row1: float
    lane: str

    def box(self) -> tuple[float, float, float, float]:
        x = LEFT + self.col0 * COLUMN + 6
        y = TOP + self.row0 * ROW + 6
        return x, y, (self.col1 - self.col0 + 1) * COLUMN - 12, (self.row1 - self.row0 + 1) * ROW - 12


@dataclass
class Flow:
    source: str
    target: str
    label: str = ""
    route: str = "auto"  # auto, down, up


@dataclass
class Diagram:
    key: str
    title: str
    lanes: list[tuple[str, str, float, float]]  # id, label, firstRow, lastRow
    columns: int
    nodes: list[Node]
    flows: list[Flow]
    subprocesses: list[SubProcess] = field(default_factory=list)
    externals: list[tuple[str, str, float, float]] = field(default_factory=list)  # id, label, firstCol, lastCol (collapsed pools)
    messages: list[tuple[str, str, str]] = field(default_factory=list)  # nodeId, externalId, label
    associations: list[tuple[str, str]] = field(default_factory=list)  # nodeId, dataStoreId
    annotations: list[tuple[str, str, float, float, str]] = field(default_factory=list)  # id, text, col, row, attachedNodeId

    def node(self, nodeId: str) -> Node:
        return next(node for node in self.nodes if node.id == nodeId)

    @property
    def poolBottom(self) -> float:
        return TOP + (max(lane[3] for lane in self.lanes) + 1) * ROW

    @property
    def width(self) -> float:
        return LEFT + self.columns * COLUMN + 10

    @property
    def storeRowY(self) -> float:
        return self.poolBottom + 40

    def externalY(self, index: int) -> float:
        hasStores = any(node.kind == "dataStore" for node in self.nodes)
        return self.poolBottom + (135 if hasStores else 50) + index * (EXTERNAL_POOL_H + 18)

    @property
    def height(self) -> float:
        return self.externalY(len(self.externals)) + 10


# ---------- Edge routing ----------


def _anchor(node: Node, side: str) -> tuple[float, float]:
    (x, y), (hw, hh) = node.center, node.half
    return {"left": (x - hw, y), "right": (x + hw, y), "top": (x, y - hh), "bottom": (x, y + hh)}[side]


def route(diagram: Diagram, flow: Flow) -> list[tuple[float, float]]:
    source, target = diagram.node(flow.source), diagram.node(flow.target)
    (sx, sy), (tx, ty) = source.center, target.center
    if flow.route == "below":  # Goes under the nodes in between and enters the target from below
        bypass = sy + ROW / 2 - 6
        return [_anchor(source, "bottom"), (sx, bypass), (tx, bypass), _anchor(target, "bottom")]
    if abs(sy - ty) < 1:
        if tx > sx:
            return [_anchor(source, "right"), _anchor(target, "left")]
        bottom = sy + ROW / 2 - 8
        return [_anchor(source, "bottom"), (sx, bottom), (tx, bottom), _anchor(target, "bottom")]
    goingDown = ty > sy
    if abs(sx - tx) < 1:
        return [_anchor(source, "bottom" if goingDown else "top"), _anchor(target, "top" if goingDown else "bottom")]
    if source.kind == "gateway" or flow.route == "down":
        # Vertical first, then horizontal into the target side
        start = _anchor(source, "bottom" if goingDown else "top")
        end = _anchor(target, "left" if tx > sx else "right")
        return [start, (sx, ty), end]
    # Horizontal first, then vertical into the target
    start = _anchor(source, "right" if tx > sx else "left")
    end = _anchor(target, "top" if goingDown else "bottom")
    return [start, (tx, sy), end]


# ---------- SVG rendering ----------


def _wrap(text: str, width: float) -> list[str]:
    maxChars = max(6, int(width / CHAR_W))
    lines: list[str] = []
    for paragraph in text.split("\n"):
        current = ""
        for word in paragraph.split():
            candidate = f"{current} {word}".strip()
            if len(candidate) <= maxChars or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def _text(x: float, y: float, text: str, width: float, size: int = FONT, weight: str = "normal", anchor: str = "middle", valign: str = "middle") -> str:
    lines = _wrap(text, width)
    total = len(lines) * LINE_HEIGHT
    first = y - total / 2 + LINE_HEIGHT * 0.78 if valign == "middle" else y + LINE_HEIGHT * 0.78
    spans = "".join(f'<tspan x="{x:.1f}" y="{first + index * LINE_HEIGHT:.1f}">{escape(line)}</tspan>' for index, line in enumerate(lines))
    return f'<text font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" fill="{INK}">{spans}</text>'


def _icon(kind: str, x: float, y: float) -> str:
    if kind == "userTask":
        return (f'<circle cx="{x + 7}" cy="{y + 6}" r="3.2" fill="none" stroke="{INK}" stroke-width="1.2"/>'
                f'<path d="M{x + 1} {y + 16} q6 -9 12 0" fill="none" stroke="{INK}" stroke-width="1.2"/>')
    if kind == "serviceTask":
        return (f'<circle cx="{x + 7}" cy="{y + 9}" r="5" fill="none" stroke="{INK}" stroke-width="1.2" stroke-dasharray="2 1.4"/>'
                f'<circle cx="{x + 7}" cy="{y + 9}" r="2" fill="none" stroke="{INK}" stroke-width="1.1"/>')
    if kind == "sendTask":
        return (f'<rect x="{x + 1}" y="{y + 3}" width="13" height="9" fill="{INK}"/>'
                f'<path d="M{x + 1} {y + 3} l6.5 5 l6.5 -5" fill="none" stroke="#fff" stroke-width="1"/>')
    return ""


def _shape(node: Node, laneKind: str) -> str:
    (x, y) = node.center
    bx, by, bw, bh = node.box()
    fill = HUMAN_FILL if laneKind == "human" else ROBOT_FILL
    if node.kind in ("task", "userTask", "serviceTask", "sendTask"):
        return (f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="9" fill="{fill}" stroke="{INK}" stroke-width="1.4"/>'
                + _icon(node.kind, bx + 4, by + 4) + _text(x, y + (3 if node.kind != "task" else 0), node.label, bw - 10))
    if node.kind == "gateway":
        h = GATEWAY_HALF
        diamond = f'<path d="M{x} {y - h} L{x + h} {y} L{x} {y + h} L{x - h} {y} Z" fill="#fff" stroke="{INK}" stroke-width="1.4"/>'
        cross = f'<path d="M{x - 7} {y - 7} L{x + 7} {y + 7} M{x + 7} {y - 7} L{x - 7} {y + 7}" stroke="{INK}" stroke-width="2.4"/>'
        return diamond + cross + _text(x, y - h - 4 - LINE_HEIGHT * len(_wrap(node.label, 180)) / 2, node.label, 180, size=10)
    if node.kind == "dataStore":
        return (f'<path d="M{bx} {by + 6} v{bh - 12} a{bw / 2} 6 0 0 0 {bw} 0 v{-(bh - 12)} a{bw / 2} 6 0 0 0 {-bw} 0 a{bw / 2} 6 0 0 0 {bw} 0" '
                f'fill="#fff" stroke="{INK}" stroke-width="1.3"/>' + _text(x, by + bh + 4, node.label, 130, size=10, valign="top"))
    stroke = 3.4 if node.kind in ("end", "errorEnd") else 1.5
    shape = f'<circle cx="{x}" cy="{y}" r="{EVENT_R}" fill="#fff" stroke="{INK}" stroke-width="{stroke}"/>'
    if node.kind == "timerStart":
        shape += (f'<circle cx="{x}" cy="{y}" r="{EVENT_R - 4}" fill="none" stroke="{INK}" stroke-width="1"/>'
                  f'<path d="M{x} {y - 8} L{x} {y} L{x + 6} {y + 3}" fill="none" stroke="{INK}" stroke-width="1.3"/>')
    if node.kind == "messageStart":
        shape += f'<rect x="{x - 8}" y="{y - 5.5}" width="16" height="11" fill="none" stroke="{INK}" stroke-width="1.1"/><path d="M{x - 8} {y - 5.5} l8 6 l8 -6" fill="none" stroke="{INK}" stroke-width="1.1"/>'
    if node.kind == "errorEnd":
        shape += f'<path d="M{x - 7} {y + 7} L{x - 3} {y - 6} L{x + 2} {y + 2} L{x + 7} {y - 8} L{x + 4} {y + 6} L{x - 1} {y - 2} Z" fill="{INK}"/>'
    return shape + _text(x, y + EVENT_R + 4, node.label, 112, size=10, valign="top")


def _path(points: list[tuple[float, float]], dashed: bool = False, marker: str = "arrow", startMarker: str = "") -> str:
    data = " ".join(f"{'M' if index == 0 else 'L'}{x:.1f} {y:.1f}" for index, (x, y) in enumerate(points))
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    start = f' marker-start="url(#{startMarker})"' if startMarker else ""
    end = f' marker-end="url(#{marker})"' if marker else ""
    return f'<path d="{data}" fill="none" stroke="{INK}" stroke-width="1.3"{dash}{start}{end}/>'


def _externalSpan(diagram: Diagram, firstCol: float, lastCol: float) -> tuple[float, float]:
    x0 = 0.5 if firstCol <= 0 else LEFT + firstCol * COLUMN
    x1 = LEFT + diagram.columns * COLUMN if lastCol >= diagram.columns - 1 else LEFT + (lastCol + 1) * COLUMN
    return x0, x1


def renderSvg(diagram: Diagram) -> str:
    width, height = diagram.width, diagram.height
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'font-family="Segoe UI, Helvetica, Arial, sans-serif">',
        "<defs>"
        f'<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto"><path d="M0 0 L10 5 L0 10 Z" fill="{INK}"/></marker>'
        f'<marker id="openArrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto"><path d="M0 0 L10 5 L0 10 Z" fill="#fff" stroke="{INK}"/></marker>'
        f'<marker id="dot" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="7" markerHeight="7"><circle cx="5" cy="5" r="4" fill="#fff" stroke="{INK}"/></marker>'
        "</defs>",
        f'<rect width="100%" height="100%" fill="#fff"/>',
    ]
    poolTop, poolBottom = TOP, diagram.poolBottom
    poolRight = LEFT + diagram.columns * COLUMN
    parts.append(f'<rect x="0.5" y="{poolTop}" width="{poolRight}" height="{poolBottom - poolTop}" fill="none" stroke="{INK}" stroke-width="1.4"/>')
    parts.append(f'<line x1="{POOL_HEADER}" y1="{poolTop}" x2="{POOL_HEADER}" y2="{poolBottom}" stroke="{INK}" stroke-width="1.2"/>')
    parts.append(f'<text transform="translate({POOL_HEADER / 2 + 5} {(poolTop + poolBottom) / 2}) rotate(-90)" font-size="13" font-weight="600" text-anchor="middle" fill="{INK}">{escape(diagram.title)}</text>')
    laneKinds = {}
    for laneId, label, firstRow, lastRow in diagram.lanes:
        y0, y1 = TOP + firstRow * ROW, TOP + (lastRow + 1) * ROW
        human = laneId == "hr"
        laneKinds[laneId] = "human" if human else "robot"
        parts.append(f'<rect x="{POOL_HEADER}" y="{y0}" width="{poolRight - POOL_HEADER}" height="{y1 - y0}" fill="{"#fffdf7" if human else "#fcfdff"}" stroke="{INK}" stroke-width="1"/>')
        parts.append(f'<line x1="{POOL_HEADER + LANE_HEADER}" y1="{y0}" x2="{POOL_HEADER + LANE_HEADER}" y2="{y1}" stroke="{INK}" stroke-width="1"/>')
        parts.append(f'<text transform="translate({POOL_HEADER + LANE_HEADER / 2 + 4} {(y0 + y1) / 2}) rotate(-90)" font-size="12" font-weight="600" text-anchor="middle" fill="{INK}">{escape(label)}</text>')
    for sub in diagram.subprocesses:
        x, y, w, h = sub.box()
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{SUBPROCESS_FILL}" stroke="{INK}" stroke-width="1.4"/>')
        parts.append(_text(x + 10, y + 6, sub.label, w - 20, size=11, weight="600", anchor="start", valign="top"))
        mx, my = x + w / 2, y + h - 16  # Sequential multi-instance marker (three horizontal lines)
        parts.append("".join(f'<line x1="{mx - 7}" y1="{my + offset}" x2="{mx + 7}" y2="{my + offset}" stroke="{INK}" stroke-width="1.8"/>' for offset in (0, 5, 10)))
    for index, (externalId, label, firstCol, lastCol) in enumerate(diagram.externals):
        y = diagram.externalY(index)
        x0, x1 = _externalSpan(diagram, firstCol, lastCol)
        parts.append(f'<rect x="{x0}" y="{y}" width="{x1 - x0}" height="{EXTERNAL_POOL_H}" fill="#f4f4f4" stroke="{INK}" stroke-width="1.4"/>')
        parts.append(_text((x0 + x1) / 2, y + EXTERNAL_POOL_H / 2, label, x1 - x0, size=12, weight="600"))
    for flow in diagram.flows:
        points = route(diagram, flow)
        parts.append(_path(points))
        if flow.label:
            (x0, y0), (x1, y1) = points[0], points[1]
            if abs(x0 - x1) < 1:  # Vertical first segment: label to the right
                parts.append(_text(x0 + 6, (y0 + y1) / 2 - 6, flow.label, 70, size=10, anchor="start", valign="top"))
            else:
                parts.append(_text((x0 + x1) / 2, y0 - 14, flow.label, 80, size=10))
    for nodeId, externalId, label in diagram.messages:
        node = diagram.node(nodeId)
        index = [item[0] for item in diagram.externals].index(externalId)
        x = node.center[0] + 22
        parts.append(_path([(x, node.box()[1] + TASK_H), (x, diagram.externalY(index))], dashed=True, marker="openArrow", startMarker="dot"))
        if label:
            parts.append(_text(x + 5, diagram.poolBottom + 6, label, 150, size=9, anchor="start", valign="top"))
    for nodeId, storeId in diagram.associations:
        node, store = diagram.node(nodeId), diagram.node(storeId)
        x = node.center[0] - 22
        parts.append(_path([(x, node.box()[1] + TASK_H), (x, store.box()[1])], dashed=True, marker="arrow"))
    for annotationId, text, col, row, attachedId in diagram.annotations:
        x, y = LEFT + col * COLUMN + 8, TOP + row * ROW + 10
        lines = _wrap(text, 250)
        h = len(lines) * LINE_HEIGHT + 10
        parts.append(f'<path d="M{x + 12} {y} H{x} V{y + h} H{x + 12}" fill="none" stroke="{INK}" stroke-width="1.2"/>')
        parts.append(_text(x + 6, y + 5, text, 250, size=10, anchor="start", valign="top"))
        if attachedId:
            target = diagram.node(attachedId)
            tx, ty = target.center
            parts.append(_path([(x, y + h / 2), (tx, ty - target.half[1])], dashed=True, marker=""))
    for node in diagram.nodes:
        if node.kind != "subprocess":
            parts.append(_shape(node, laneKinds.get(node.lane, "robot")))
    parts.append("</svg>")
    return "\n".join(parts)


# ---------- BPMN 2.0 XML ----------

_BPMN_TAG = {
    "start": "startEvent", "timerStart": "startEvent", "messageStart": "startEvent", "end": "endEvent", "errorEnd": "endEvent",
    "task": "task", "userTask": "userTask", "serviceTask": "serviceTask", "sendTask": "sendTask", "gateway": "exclusiveGateway",
}


def renderBpmn(diagram: Diagram) -> str:
    processId = f"{diagram.key}Process"
    flowsByNode: dict[str, tuple[list[str], list[str]]] = {node.id: ([], []) for node in diagram.nodes}
    for index, flow in enumerate(diagram.flows):
        flowsByNode[flow.source][1].append(f"flow{index}")
        flowsByNode[flow.target][0].append(f"flow{index}")

    def element(node: Node) -> str:
        if node.kind == "dataStore":
            return f'<bpmn:dataStoreReference id="{node.id}" name="{escape(node.label)}"/>'
        tag = _BPMN_TAG[node.kind]
        incoming, outgoing = flowsByNode[node.id]
        children = "".join(f"<bpmn:incoming>{item}</bpmn:incoming>" for item in incoming) + "".join(f"<bpmn:outgoing>{item}</bpmn:outgoing>" for item in outgoing)
        stores = [storeId for nodeId, storeId in diagram.associations if nodeId == node.id]
        children += "".join(f'<bpmn:dataOutputAssociation id="assoc_{node.id}_{storeId}"><bpmn:targetRef>{storeId}</bpmn:targetRef></bpmn:dataOutputAssociation>' for storeId in stores)
        if node.kind == "timerStart":
            cycle = "R/PT10M" if "10 min" in node.label else "R/PT5M"
            children += f'<bpmn:timerEventDefinition id="timer_{node.id}"><bpmn:timeCycle xsi:type="bpmn:tFormalExpression">{cycle}</bpmn:timeCycle></bpmn:timerEventDefinition>'
        if node.kind == "messageStart":
            children += f'<bpmn:messageEventDefinition id="message_{node.id}"/>'
        if node.kind == "errorEnd":
            children += f'<bpmn:errorEventDefinition id="error_{node.id}"/>'
        return f'<bpmn:{tag} id="{node.id}" name="{escape(node.label)}">{children}</bpmn:{tag}>'

    def sequenceFlow(index: int, flow: Flow) -> str:
        name = f' name="{escape(flow.label)}"' if flow.label else ""
        return f'<bpmn:sequenceFlow id="flow{index}"{name} sourceRef="{flow.source}" targetRef="{flow.target}"/>'

    def flowsInside(parent: str | None) -> list[str]:
        ids = {node.id for node in diagram.nodes if node.parent == parent}
        return [sequenceFlow(index, flow) for index, flow in enumerate(diagram.flows) if flow.source in ids]

    body: list[str] = []
    for sub in diagram.subprocesses:
        inner = [element(node) for node in diagram.nodes if node.parent == sub.id] + flowsInside(sub.id)
        incoming, outgoing = flowsByNode.get(sub.id, ([], []))
        links = "".join(f"<bpmn:incoming>{item}</bpmn:incoming>" for item in incoming) + "".join(f"<bpmn:outgoing>{item}</bpmn:outgoing>" for item in outgoing)
        body.append(
            f'<bpmn:subProcess id="{sub.id}" name="{escape(sub.label)}">{links}'
            f'<bpmn:multiInstanceLoopCharacteristics isSequential="true"/>{"".join(inner)}</bpmn:subProcess>'
        )
    body += [element(node) for node in diagram.nodes if node.parent is None and node.kind != "subprocess"]
    body += flowsInside(None)
    for annotationId, text, *_ in diagram.annotations:
        body.append(f'<bpmn:textAnnotation id="{annotationId}"><bpmn:text>{escape(text)}</bpmn:text></bpmn:textAnnotation>')
    for annotationId, _, _, _, attachedId in diagram.annotations:
        if attachedId:
            body.append(f'<bpmn:association id="assoc_{annotationId}" sourceRef="{attachedId}" targetRef="{annotationId}"/>')

    lanes = []
    for laneId, label, *_ in diagram.lanes:
        refs = [node.id for node in diagram.nodes if node.lane == laneId and node.parent is None and node.kind not in ("dataStore", "subprocess")]
        refs += [sub.id for sub in diagram.subprocesses if sub.lane == laneId]
        lanes.append(f'<bpmn:lane id="{laneId}" name="{escape(label)}">' + "".join(f"<bpmn:flowNodeRef>{ref}</bpmn:flowNodeRef>" for ref in refs) + "</bpmn:lane>")

    participants = [f'<bpmn:participant id="{diagram.key}Pool" name="{escape(diagram.title)}" processRef="{processId}"/>']
    participants += [f'<bpmn:participant id="{externalId}" name="{escape(label)}"/>' for externalId, label, *_ in diagram.externals]
    messageFlows = [
        f'<bpmn:messageFlow id="message{index}" name="{escape(label)}" sourceRef="{nodeId}" targetRef="{externalId}"/>'
        for index, (nodeId, externalId, label) in enumerate(diagram.messages)
    ]

    # Diagram interchange (same geometry as the SVG)
    shapes = [_diShape(f"{diagram.key}Pool", 0, TOP, LEFT + diagram.columns * COLUMN, diagram.poolBottom - TOP, horizontal=True)]
    for laneId, _, firstRow, lastRow in diagram.lanes:
        shapes.append(_diShape(laneId, POOL_HEADER, TOP + firstRow * ROW, LEFT + diagram.columns * COLUMN - POOL_HEADER, (lastRow - firstRow + 1) * ROW, horizontal=True))
    for index, (externalId, _, firstCol, lastCol) in enumerate(diagram.externals):
        x0, x1 = _externalSpan(diagram, firstCol, lastCol)
        shapes.append(_diShape(externalId, x0, diagram.externalY(index), x1 - x0, EXTERNAL_POOL_H, horizontal=True))
    for sub in diagram.subprocesses:
        shapes.append(_diShape(sub.id, *sub.box(), expanded=True))
    for node in diagram.nodes:
        if node.kind != "subprocess":
            shapes.append(_diShape(node.id, *node.box()))
    for annotationId, text, col, row, _ in diagram.annotations:
        shapes.append(_diShape(annotationId, LEFT + col * COLUMN + 8, TOP + row * ROW + 10, 250, len(_wrap(text, 250)) * LINE_HEIGHT + 10))
    edges = [_diEdge(f"flow{index}", route(diagram, flow)) for index, flow in enumerate(diagram.flows)]
    for index, (nodeId, externalId, _) in enumerate(diagram.messages):
        node = diagram.node(nodeId)
        x = node.center[0] + 22
        position = [item[0] for item in diagram.externals].index(externalId)
        edges.append(_diEdge(f"message{index}", [(x, node.box()[1] + TASK_H), (x, diagram.externalY(position))]))
    for nodeId, storeId in diagram.associations:
        node, store = diagram.node(nodeId), diagram.node(storeId)
        x = node.center[0] - 22
        edges.append(_diEdge(f"assoc_{nodeId}_{storeId}", [(x, node.box()[1] + TASK_H), (x, store.box()[1])]))

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" '
        'xmlns:di="http://www.omg.org/spec/DD/20100524/DI" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        f'id="{diagram.key}Definitions" targetNamespace="https://github.com/haruoooo/SemestralRpa" exporter="tools.bpmnDiagrams" exporterVersion="1.0">\n'
        f'<bpmn:collaboration id="{diagram.key}Collaboration">{"".join(participants)}{"".join(messageFlows)}</bpmn:collaboration>\n'
        f'<bpmn:process id="{processId}" name="{escape(diagram.title)}" isExecutable="false">'
        f'<bpmn:laneSet id="{diagram.key}Lanes">{"".join(lanes)}</bpmn:laneSet>\n'
        + "\n".join(body)
        + "\n</bpmn:process>\n"
        f'<bpmndi:BPMNDiagram id="{diagram.key}Diagram"><bpmndi:BPMNPlane id="{diagram.key}Plane" bpmnElement="{diagram.key}Collaboration">\n'
        + "\n".join(shapes + edges)
        + "\n</bpmndi:BPMNPlane></bpmndi:BPMNDiagram>\n</bpmn:definitions>\n"
    )


def _diShape(elementId: str, x: float, y: float, w: float, h: float, horizontal: bool = False, expanded: bool = False) -> str:
    extra = ' isHorizontal="true"' if horizontal else ""
    extra += ' isExpanded="true"' if expanded else ""
    return f'<bpmndi:BPMNShape id="{elementId}_di" bpmnElement="{elementId}"{extra}><dc:Bounds x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}"/></bpmndi:BPMNShape>'


def _diEdge(elementId: str, points: list[tuple[float, float]]) -> str:
    waypoints = "".join(f'<di:waypoint x="{x:.0f}" y="{y:.0f}"/>' for x, y in points)
    return f'<bpmndi:BPMNEdge id="{elementId}_di" bpmnElement="{elementId}">{waypoints}</bpmndi:BPMNEdge>'


# ---------- The three flows (docs/processDesign.md) ----------


def scheduleImportDiagram() -> Diagram:
    R, S = "robot", "sp1"
    nodes = [
        Node("hrStart", "start", "Escala da semana definida", 0, 0, "hr"),
        Node("hrFill", "userTask", "Preencher a planilha no modelo do RH", 1, 0, "hr"),
        Node("hrSave", "userTask", "Salvar em data/input/", 2, 0, "hr"),
        Node("hrEnd", "end", "Planilha entregue ao robô", 3, 0, "hr"),
        Node("timer", "timerStart", "A cada 5 min", 0, 1, R),
        Node("outbox", "serviceTask", "Reenviar importações da outbox (EX06)", 1, 1, R),
        Node("list", "task", "Listar arquivos em data/input/", 2, 1, R),
        Node("hasFiles", "gateway", "Há arquivos?", 3, 1, R),
        Node("noFiles", "end", "Nada a processar", 3, 2, R),
        Node("fileStart", "start", "Arquivo", 4, 1, R, S),
        Node("hash", "task", "Calcular o hash SHA-256", 5, 1, R, S),
        Node("isDuplicate", "gateway", "Já importado? (RN02)", 6, 1, R, S),
        Node("moveDuplicate", "task", "Mover para rejected/duplicates/", 6, 2, R, S),
        Node("duplicateEnd", "end", "Ignorado", 7, 2, R, S),
        Node("validate", "task", "Abrir e validar abas, colunas e linhas (RN01, RN03 a RN08)", 7, 1, R, S),
        Node("isAccepted", "gateway", "Dentro do limite? (RN09)", 8, 1, R, S),
        Node("reject", "task", "Gerar relatório do RH e mover para rejected/ (EX02 a EX04)", 8, 2, R, S),
        Node("rejectEnd", "end", "Rejeitada", 9.6, 2, R, S),
        Node("send", "serviceTask", "Enviar à API com Idempotency-Key (3 tentativas)", 10, 1, R, S),
        Node("apiAnswered", "gateway", "API respondeu?", 11, 1, R, S),
        Node("queue", "task", "Guardar na outbox", 11, 2, R, S),
        Node("land", "serviceTask", "Gravar lote pseudonimizado na pasta de pouso", 12, 1, R, S),
        Node("report", "task", "Gerar relatório do RH e mover para processed/", 13, 1, R, S),
        Node("importedEnd", "end", "Importada", 14, 1, R, S),
        Node("summary", "task", "Registrar o resumo da execução (RunSummary)", 15, 1, R),
        Node("end", "end", "Fim", 16, 1, R),
        Node("landingStore", "dataStore", "Pasta de pouso (Big Data)", 12, 3, R),
    ]
    flows = [
        Flow("hrStart", "hrFill"), Flow("hrFill", "hrSave"), Flow("hrSave", "hrEnd"),
        Flow("timer", "outbox"), Flow("outbox", "list"), Flow("list", "hasFiles"),
        Flow("hasFiles", "noFiles", "Não"), Flow("hasFiles", "sp1", "Sim"),
        Flow("fileStart", "hash"), Flow("hash", "isDuplicate"),
        Flow("isDuplicate", "moveDuplicate", "Sim"), Flow("moveDuplicate", "duplicateEnd"), Flow("isDuplicate", "validate", "Não"),
        Flow("validate", "isAccepted"), Flow("isAccepted", "reject", "Não"), Flow("reject", "rejectEnd"), Flow("isAccepted", "send", "Sim"),
        Flow("send", "apiAnswered"), Flow("apiAnswered", "land", "Sim"), Flow("apiAnswered", "queue", "Não (EX06)"), Flow("queue", "land"),
        Flow("land", "report"), Flow("report", "importedEnd"),
        Flow("sp1", "summary"), Flow("summary", "end"),
    ]
    diagram = Diagram(
        "scheduleImportFlow", "Fluxo 1 · scheduleImportFlow",
        [("hr", "RH", 0, 0), (R, "Robô RPA", 1, 2)], 17, nodes, flows,
        [SubProcess("sp1", "Para cada arquivo", 4, 14, 1, 2, R)],
        externals=[("apiPool", "API do ForaDoPico", 0, 16)],
        messages=[("outbox", "apiPool", "POST /scheduleImports"), ("send", "apiPool", "POST /scheduleImports")],
        associations=[("land", "landingStore")],
        annotations=[("noteReport", "Planilha rejeitada: o RH lê o relatório importReport<hash>.xlsx (aba, linha, coluna e motivo), corrige e salva de novo.", 5.5, 0, "")],
    )
    return _withSubprocessNodes(diagram)


def agendaDispatchDiagram() -> Diagram:
    R, S = "robot", "sp2"
    nodes = [
        Node("hrStart", "messageStart", "Escala ou plano B pendente", 0, 0, "hr"),
        Node("hrApprove", "userTask", "Revisar e aprovar no app (RN10)", 1, 0, "hr"),
        Node("hrEnd", "end", "Aprovado", 2, 0, "hr"),
        Node("timer", "timerStart", "A cada 10 min", 0, 1, R),
        Node("outbox", "serviceTask", "Reenviar relatórios de envio da outbox", 1, 1, R),
        Node("fetch", "serviceTask", "Buscar escalas e planos B aprovados", 2, 1, R),
        Node("apiUp", "gateway", "API respondeu?", 3, 1, R),
        Node("apiDown", "end", "Tentar na próxima execução (EX06)", 3, 2, R),
        Node("itemStart", "start", "Funcionário", 4, 1, R, S),
        Node("already", "gateway", "Já recebeu esta versão? (RN11)", 5, 1, R, S),
        Node("skipEnd", "end", "Pulado", 5, 2, R, S),
        Node("compose", "task", "Montar e-mail e anexo .ics", 6, 1, R, S),
        Node("sendMail", "sendTask", "Enviar e-mail (3 tentativas)", 7, 1, R, S),
        Node("mailUp", "gateway", "Servidor de e-mail respondeu?", 8, 1, R, S),
        Node("stop", "errorEnd", "Parar os envios; restante fica pendente (EX08)", 8, 2, R, S),
        Node("record", "task", "Gravar o envio no estado do robô", 9, 1, R, S),
        Node("sentEnd", "end", "Enviado", 10, 1, R, S),
        Node("reportApi", "serviceTask", "Informar resultados à API", 11, 1, R),
        Node("reportUp", "gateway", "API respondeu?", 12, 1, R),
        Node("reportQueue", "task", "Guardar relatório na outbox", 12, 2, R),
        Node("summary", "task", "Registrar o resumo da execução", 13, 1, R),
        Node("end", "end", "Fim", 14, 1, R),
    ]
    flows = [
        Flow("hrStart", "hrApprove"), Flow("hrApprove", "hrEnd"),
        Flow("timer", "outbox"), Flow("outbox", "fetch"), Flow("fetch", "apiUp"),
        Flow("apiUp", "apiDown", "Não"), Flow("apiUp", "sp2", "Sim"),
        Flow("itemStart", "already"), Flow("already", "skipEnd", "Sim"), Flow("already", "compose", "Não"),
        Flow("compose", "sendMail"), Flow("sendMail", "mailUp"), Flow("mailUp", "stop", "Não"), Flow("mailUp", "record", "Sim"),
        Flow("record", "sentEnd"),
        Flow("sp2", "reportApi"), Flow("reportApi", "reportUp"), Flow("reportUp", "summary", "Sim"),
        Flow("reportUp", "reportQueue", "Não (EX06)"), Flow("reportQueue", "summary"), Flow("summary", "end"),
    ]
    diagram = Diagram(
        "agendaDispatchFlow", "Fluxo 2 · agendaDispatchFlow",
        [("hr", "RH", 0, 0), (R, "Robô RPA", 1, 2)], 15, nodes, flows,
        [SubProcess("sp2", "Para cada escala e plano B aprovado, para cada funcionário", 4, 10, 1, 2, R)],
        externals=[("mailPool", "Servidor de e-mail (Mailtrap) → funcionário", 5, 9), ("apiPool", "API do ForaDoPico", 0, 14)],
        messages=[("fetch", "apiPool", "GET /schedules, GET /contingencyPlans"), ("sendMail", "mailPool", "E-mail + agenda.ics"), ("reportApi", "apiPool", "POST /dispatches")],
        annotations=[("notePlan", "Plano B aprovado: o .ics cancela (remoto) ou move (nova janela) o mesmo evento da agenda da semana.", 6.2, 0, "")],
    )
    return _withSubprocessNodes(diagram)


def lineMonitorDiagram() -> Diagram:
    R, S = "robot", "sp3"
    nodes = [
        Node("hrStart", "messageStart", "Plano B pendente no app", 9, 0, "hr"),
        Node("hrDecide", "userTask", "Aprovar ou recusar o plano B (RN15)", 10, 0, "hr"),
        Node("hrEnd", "end", "Decisão registrada (fluxo 2 avisa)", 11, 0, "hr"),
        Node("timer", "timerStart", "A cada 5 min, dias úteis", 0, 1, R),
        Node("inWindow", "gateway", "Entre 05:00 e 22:00? (RN17)", 1, 1, R),
        Node("outside", "end", "Fora da janela", 1, 2, R),
        Node("fetch", "serviceTask", "Baixar a página do Metrô (3 tentativas)", 2, 1, R),
        Node("sourceUp", "gateway", "Fonte respondeu?", 3, 1, R),
        Node("stale", "task", "Usar o último estado; marcar stale após 30 min (RN16)", 3, 2, R),
        Node("staleEnd", "end", "Sem plano B novo", 4, 2, R),
        Node("parse", "task", "Interpretar o HTML", 4, 1, R),
        Node("layoutOk", "gateway", "Linhas 1 e 3 encontradas?", 5, 1, R),
        Node("layoutChanged", "errorEnd", "Layout mudou: alerta técnico (EX10)", 5, 2, R),
        Node("lineStart", "start", "Linha", 6, 1, R, S),
        Node("classify", "task", "Classificar a situação (RN12)", 7, 1, R, S),
        Node("changed", "gateway", "Status mudou? (RN13)", 8, 1, R, S),
        Node("unchanged", "end", "Sem mudança", 8, 2, R, S),
        Node("alert", "serviceTask", "Criar alerta (chave linha + status + data)", 9, 1, R, S),
        Node("needsPlan", "gateway", "Paralisada ou lenta?", 10, 1, R, S),
        Node("propose", "serviceTask", "Propor plano B a quem ainda vai embarcar (RN14)", 11, 1, R, S),
        Node("save", "task", "Gravar o novo estado da linha", 12, 1, R, S),
        Node("lineEnd", "end", "Linha tratada", 13, 1, R, S),
        Node("snapshot", "serviceTask", "Publicar a situação das linhas", 14, 1, R),
        Node("summary", "task", "Registrar o resumo da execução", 15, 1, R),
        Node("end", "end", "Fim", 16, 1, R),
    ]
    flows = [
        Flow("hrStart", "hrDecide"), Flow("hrDecide", "hrEnd"),
        Flow("timer", "inWindow"), Flow("inWindow", "outside", "Não"), Flow("inWindow", "fetch", "Sim"),
        Flow("fetch", "sourceUp"), Flow("sourceUp", "stale", "Não (EX09)"), Flow("stale", "staleEnd"), Flow("sourceUp", "parse", "Sim"),
        Flow("parse", "layoutOk"), Flow("layoutOk", "layoutChanged", "Não"), Flow("layoutOk", "sp3", "Sim"),
        Flow("lineStart", "classify"), Flow("classify", "changed"), Flow("changed", "unchanged", "Não"), Flow("changed", "alert", "Sim"),
        Flow("alert", "needsPlan"), Flow("needsPlan", "propose", "Sim"), Flow("needsPlan", "save", "Não", route="below"),
        Flow("propose", "save"), Flow("save", "lineEnd"),
        Flow("sp3", "snapshot"), Flow("snapshot", "summary"), Flow("summary", "end"),
    ]
    diagram = Diagram(
        "lineMonitorFlow", "Fluxo 3 · lineMonitorFlow",
        [("hr", "RH", 0, 0), (R, "Robô RPA", 1, 2)], 17, nodes, flows,
        [SubProcess("sp3", "Para cada linha monitorada", 6, 13, 1, 2, R)],
        externals=[("metroPool", "Site do Metrô (Direto do Metrô)", 0, 4), ("apiPool", "API do ForaDoPico", 0, 16)],
        messages=[("fetch", "metroPool", "GET direto-metro.php"), ("alert", "apiPool", "POST /alerts"), ("propose", "apiPool", "GET /assignments, POST /contingencyPlans"), ("snapshot", "apiPool", "POST /lineStatus")],
        annotations=[("noteApi", "Se a API falhar, o estado da linha não é gravado: a mesma mudança é reenviada na próxima execução (EX06).", 1.6, 0, "")],
    )
    return _withSubprocessNodes(diagram)


def _withSubprocessNodes(diagram: Diagram) -> Diagram:
    """Subprocesses take part in sequence flows: add a routing proxy whose sides match the subprocess box."""
    for sub in diagram.subprocesses:
        x, y, w, h = sub.box()
        rowCenter = TOP + sub.row0 * ROW + ROW / 2  # Flows enter and leave at the height of the main row
        diagram.nodes.append(Node(sub.id, "subprocess", sub.label, 0, 0, sub.lane, fixedCenter=(x + w / 2, rowCenter), fixedHalf=(w / 2, rowCenter - y)))
    return diagram


def build(outputDir: Path) -> list[Path]:
    outputDir.mkdir(parents=True, exist_ok=True)
    written = []
    for diagram in (scheduleImportDiagram(), agendaDispatchDiagram(), lineMonitorDiagram()):
        for suffix, content in ((".svg", renderSvg(diagram)), (".bpmn", renderBpmn(diagram))):
            path = outputDir / f"{diagram.key}{suffix}"
            path.write_text(content, encoding="utf-8")
            written.append(path)
    return written


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/bpmn")
    for item in build(target):
        print(f"Diagrama gerado: {item}")
