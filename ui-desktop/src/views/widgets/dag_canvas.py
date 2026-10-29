"""Interactive HSDG Subgraph Canvas (`QGraphicsScene` + OpenGL/Hardware Antialiased `QGraphicsView`)."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
    QWidget,
)


@dataclass
class HsdgNodeSpec:
    node_id: str
    node_type: str  # StorageNode, FunctionNode, ConditionNode, ExternalCallNode
    label: str
    detail: str
    pos: Tuple[float, float]
    active: bool = False


@dataclass
class HsdgEdgeSpec:
    src_id: str
    dst_id: str
    relation: str  # ReadsFrom, WritesTo, Guards, Invokes
    detail: str = ""
    curve_offset: float = -16.0
    label_pct: float = 0.50


NODE_COLORS: Dict[str, Tuple[str, str]] = {
    "StorageNode": ("#1f3a60", "#58a6ff"),       # 64-dim storage node (Blue)
    "FunctionNode": ("#122d1f", "#3fb950"),      # 64-dim function node (Green)
    "ConditionNode": ("#342209", "#d29922"),     # 48-dim condition guard (Amber)
    "ExternalCallNode": ("#2b193d", "#d2a8ff"),  # 32-dim external call (Purple)
}

NODE_FEATURE_SCHEMAS: Dict[str, str] = {
    "StorageNode": "Tensor [N_storage, 64] (Kind::Float -> BF16): [0..18] SoliditySlotType, [18..26] SemanticRole, [26..32] Packing, [32..64] Dynamic SIMD U256 Log2 & Sinusoidal",
    "FunctionNode": "Tensor [N_func, 64] (Kind::Float -> BF16): [0..8] Visibility/Mutability, [8..16] Modifiers/Assembly, [16..24] CFG Complexity, [24..64] 4-Byte Selector & Opcode Hist",
    "ConditionNode": "Tensor [N_cond, 48] (Kind::Float -> BF16): [0..6] Guard Origin, [6..16] Comparison Op, [16..24] Literal Scale, [24..32] Runtime JUMPI d_branch & SMT Flag, [32..48] AST Tree",
    "ExternalCallNode": "Tensor [N_ext, 32] (Kind::Float -> BF16): [0..6] CALL/DELEGATECALL/STATICCALL, [6..14] Target Class, [14..18] Reentrancy Risk CEI Flags, [18..32] Gas/Value Flow",
}

EDGE_COLORS: Dict[str, str] = {
    "ReadsFrom": "#58a6ff",
    "WritesTo": "#f85149",
    "Guards": "#d29922",
    "Invokes": "#d2a8ff",
}


class HsdgNodeItem(QGraphicsItem):
    """Draggable interactive HSDG graph node item."""

    WIDTH = 176.0
    HEIGHT = 56.0

    def __init__(self, spec: HsdgNodeSpec) -> None:
        super().__init__()
        self.spec = spec
        self.setPos(spec.pos[0], spec.pos[1])
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(2.0)

    def boundingRect(self) -> QRectF:
        return QRectF(-self.WIDTH / 2, -self.HEIGHT / 2, self.WIDTH, self.HEIGHT)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # type: ignore[override]
        bg_hex, border_hex = NODE_COLORS.get(self.spec.node_type, ("#161b22", "#8b949e"))
        rect = self.boundingRect()

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen_width = 2.6 if (self.spec.active or self.isSelected()) else 1.4
        border_col = QColor("#ff7b72") if self.spec.active else QColor(border_hex)
        painter.setPen(QPen(border_col, pen_width))
        painter.setBrush(QBrush(QColor(bg_hex)))
        painter.drawRoundedRect(rect, 7.0, 7.0)

        dim_map = {
            "StorageNode": "64-d",
            "FunctionNode": "64-d",
            "ConditionNode": "48-d",
            "ExternalCallNode": "32-d",
        }
        dim_badge = dim_map.get(self.spec.node_type, "")
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        painter.setPen(QColor(border_hex))
        painter.drawText(
            rect.adjusted(8, 4, -8, -32),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"{self.spec.node_type} [{dim_badge}]",
        )

        painter.setFont(QFont("Cascadia Code", 9, QFont.Weight.Bold))
        painter.setPen(QColor("#ffffff"))
        painter.drawText(
            rect.adjusted(8, 19, -8, -16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.spec.label,
        )

        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(QColor("#c9d1d9"))
        painter.drawText(
            rect.adjusted(8, 35, -8, -4),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.spec.detail,
        )


class HsdgEdgeItem(QGraphicsPathItem):
    """Directed edge with relation label between two HsdgNodeItems."""

    def __init__(self, src_item: HsdgNodeItem, dst_item: HsdgNodeItem, spec: HsdgEdgeSpec) -> None:
        super().__init__()
        self.src_item = src_item
        self.dst_item = dst_item
        self.spec = spec
        self.setZValue(1.0)
        self.update_path()

    @staticmethod
    def _clip_to_node_border(center: QPointF, target: QPointF) -> QPointF:
        dx = target.x() - center.x()
        dy = target.y() - center.y()
        if abs(dx) < 1e-4 and abs(dy) < 1e-4:
            return center
        hw = HsdgNodeItem.WIDTH / 2.0 + 3.0
        hh = HsdgNodeItem.HEIGHT / 2.0 + 3.0
        tx = hw / abs(dx) if abs(dx) > 1e-4 else float("inf")
        ty = hh / abs(dy) if abs(dy) > 1e-4 else float("inf")
        t = min(tx, ty)
        return QPointF(center.x() + dx * t, center.y() + dy * t)

    def update_path(self) -> None:
        c1 = self.src_item.pos()
        c2 = self.dst_item.pos()
        p1 = self._clip_to_node_border(c1, c2)
        p2 = self._clip_to_node_border(c2, c1)
        path = QPainterPath(p1)
        ctrl = QPointF((p1.x() + p2.x()) / 2.0, (p1.y() + p2.y()) / 2.0 + self.spec.curve_offset)
        path.quadTo(ctrl, p2)
        self.setPath(path)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # type: ignore[override]
        self.update_path()
        color = QColor(EDGE_COLORS.get(self.spec.relation, "#8b949e"))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(color, 1.8, Qt.PenStyle.SolidLine))
        path = self.path()
        painter.drawPath(path)

        pct = self.spec.label_pct
        mid = path.pointAtPercent(pct)
        angle = math.radians(-path.angleAtPercent(pct))
        arrow_size = 7.0
        p_a = mid - QPointF(
            math.cos(angle - math.pi / 6) * arrow_size,
            math.sin(angle - math.pi / 6) * arrow_size,
        )
        p_b = mid - QPointF(
            math.cos(angle + math.pi / 6) * arrow_size,
            math.sin(angle + math.pi / 6) * arrow_size,
        )
        painter.setBrush(QBrush(color))
        painter.drawPolygon(QPolygonF([mid, p_a, p_b]))

        font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        painter.setFont(font)
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(self.spec.relation) + 10
        th = fm.height() + 2
        lbl_rect = QRectF(mid.x() - tw / 2.0, mid.y() - th - 5.0, tw, th)
        painter.setPen(QPen(color, 1.0))
        painter.setBrush(QBrush(QColor(9, 12, 16, 230)))
        painter.drawRoundedRect(lbl_rect, 3.0, 3.0)
        painter.setPen(color)
        painter.drawText(lbl_rect, Qt.AlignmentFlag.AlignCenter, self.spec.relation)


class HsdgDagCanvas(QGraphicsView):
    """Interactive Heterogeneous State-Dependency Graph (HSDG) Visualizer (OpenGL / QGraphicsScene)."""

    node_selected = Signal(dict)  # Emits node metadata and feature tensor schema

    def __init__(self, use_opengl: bool = False, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        if use_opengl and os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            self.enable_opengl_viewport(True)

        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setMinimumHeight(215)
        self._node_items: Dict[str, HsdgNodeItem] = {}
        self._edge_items: List[HsdgEdgeItem] = []

        self._scene.selectionChanged.connect(self._on_selection_changed)
        self.load_step_subgraph(0)

    def enable_opengl_viewport(self, enabled: bool = True) -> bool:
        """Attach hardware-accelerated QOpenGLWidget viewport when requested on desktop GPUs."""
        if not enabled or os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            return False
        try:
            from PySide6.QtOpenGLWidgets import QOpenGLWidget

            self.setViewport(QOpenGLWidget())
            return True
        except Exception:
            return False

    def wheelEvent(self, event: QWheelEvent) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        self.scale(factor, factor)

    def _on_selection_changed(self) -> None:
        selected = self._scene.selectedItems()
        for item in selected:
            if isinstance(item, HsdgNodeItem):
                spec = item.spec
                self.node_selected.emit(
                    {
                        "node_id": spec.node_id,
                        "node_type": spec.node_type,
                        "label": spec.label,
                        "detail": spec.detail,
                        "schema": NODE_FEATURE_SCHEMAS.get(spec.node_type, ""),
                    }
                )
                break

    def load_step_subgraph(self, step_idx: int, step: Optional[Any] = None) -> None:
        """Render the HSDG subgraph highlighting active nodes and edges for `step_idx` and `step`."""
        self._scene.clear()
        self._node_items.clear()
        self._edge_items.clear()

        if step is not None:
            # Dynamically derive nodes from the inspected trajectory step
            target_contract = getattr(step, "target_contract", "TargetContract")
            fn_sig = getattr(step, "function_signature", "function()")
            calldata = getattr(step, "concrete_calldata_hex", "0x00000000")
            sel = calldata[:10] if len(calldata) >= 10 else "0x"
            caller_role = getattr(step, "caller_role", "Attacker")
            storage_deltas = getattr(step, "storage_deltas", [])
            smt_guard = getattr(step, "smt_guard", None)

            nodes: List[HsdgNodeSpec] = [
                HsdgNodeSpec(
                    node_id="fn_active",
                    node_type="FunctionNode",
                    label=f"{target_contract}.{fn_sig}"[:26],
                    detail=f"sel: {sel} | {caller_role}",
                    pos=(-385.0, -68.0),
                    active=True,
                )
            ]
            edges: List[HsdgEdgeSpec] = []

            # Add storage nodes from step deltas or fallback
            if storage_deltas:
                for i, d in enumerate(storage_deltas[:2]):
                    slot_hex = str(d.get("slot", f"0x0{i}"))
                    var_name = str(d.get("variable", f"slot_{i}"))
                    role = str(d.get("role", "StateVariable"))
                    y_pos = -68.0 if i == 0 else 68.0
                    st_id = "st_assets" if i == 0 else f"st_slot_{i}"
                    nodes.append(
                        HsdgNodeSpec(
                            node_id=st_id,
                            node_type="StorageNode",
                            label=f"Slot {slot_hex[:6]}: {var_name}"[:26],
                            detail=f"Role: {role} (uint256)",
                            pos=(0.0, y_pos),
                            active=True,
                        )
                    )
                    edges.append(
                        HsdgEdgeSpec(
                            "fn_active",
                            st_id,
                            "WritesTo",
                            curve_offset=-14.0 if i == 0 else 14.0,
                            label_pct=0.48,
                        )
                    )
            else:
                nodes.append(
                    HsdgNodeSpec(
                        node_id="st_assets",
                        node_type="StorageNode",
                        label="Slot 0x00: contractState",
                        detail="Role: ProtocolState (uint256)",
                        pos=(0.0, -68.0),
                        active=True,
                    )
                )
                edges.append(
                    HsdgEdgeSpec("fn_active", "st_assets", "WritesTo", curve_offset=-14.0, label_pct=0.48)
                )

            # Condition Node
            if smt_guard:
                ast_node = str(smt_guard.get("ast_node", "d_norm <= threshold"))
                solver_res = str(smt_guard.get("solver_result", "SAT"))
                nodes.append(
                    HsdgNodeSpec(
                        node_id="cond_guard",
                        node_type="ConditionNode",
                        label=f"Guard: {ast_node}"[:26],
                        detail=f"SMT: {solver_res} | QF_BV",
                        pos=(385.0, -68.0),
                        active=True,
                    )
                )
                edges.append(
                    HsdgEdgeSpec("cond_guard", "st_assets", "Guards", curve_offset=-12.0, label_pct=0.40)
                )

            # External call / Counterparty node
            nodes.append(
                HsdgNodeSpec(
                    node_id="ext_actor",
                    node_type="ExternalCallNode",
                    label=f"Caller: {caller_role}",
                    detail=f"Target: {target_contract}",
                    pos=(-385.0, 68.0),
                    active=True,
                )
            )
            edges.append(
                HsdgEdgeSpec("ext_actor", "fn_active", "Invokes", curve_offset=0.0, label_pct=0.50)
            )

            # Target State Transition Node
            nodes.append(
                HsdgNodeSpec(
                    node_id="fn_target",
                    node_type="FunctionNode",
                    label=f"{target_contract}.stateTransition",
                    detail=f"Step #{step_idx} Transition",
                    pos=(385.0, 68.0),
                    active=True,
                )
            )
            target_st2 = "st_slot_1" if len(storage_deltas) > 1 else "st_assets"
            edges.append(
                HsdgEdgeSpec(target_st2, "fn_target", "ReadsFrom", curve_offset=14.0, label_pct=0.52)
            )
        else:
            # Canonical fallback nodes
            nodes = [
                HsdgNodeSpec(
                    node_id="fn_deposit",
                    node_type="FunctionNode",
                    label="Vault.deposit(uint256)",
                    detail="sel: 0x6e553f65 | External",
                    pos=(-385.0, -68.0),
                    active=(step_idx in (0, 2)),
                ),
                HsdgNodeSpec(
                    node_id="st_assets",
                    node_type="StorageNode",
                    label="Slot 0x00: totalAssets",
                    detail="Role: PoolReserve (uint256)",
                    pos=(0.0, -68.0),
                    active=True,
                ),
                HsdgNodeSpec(
                    node_id="st_supply",
                    node_type="StorageNode",
                    label="Slot 0x01: totalSupply",
                    detail="Role: TotalSupply (uint256)",
                    pos=(0.0, 68.0),
                    active=(step_idx in (0, 1, 3)),
                ),
                HsdgNodeSpec(
                    node_id="cond_shares",
                    node_type="ConditionNode",
                    label="shares = mulDiv(a, S, A)",
                    detail="d_branch=0.92 | SMT: SAT",
                    pos=(385.0, -68.0),
                    active=(step_idx in (1, 2)),
                ),
                HsdgNodeSpec(
                    node_id="ext_erc20",
                    node_type="ExternalCallNode",
                    label="ERC20.transfer / redeem",
                    detail="CALL -> UnderlyingAsset",
                    pos=(-385.0, 68.0),
                    active=(step_idx in (1, 3)),
                ),
                HsdgNodeSpec(
                    node_id="fn_redeem",
                    node_type="FunctionNode",
                    label="Vault.redeem(uint256)",
                    detail="sel: 0xba087652 | External",
                    pos=(385.0, 68.0),
                    active=(step_idx == 3),
                ),
            ]

            edges = [
                HsdgEdgeSpec("fn_deposit", "st_assets", "WritesTo", curve_offset=-14.0, label_pct=0.48),
                HsdgEdgeSpec("fn_deposit", "st_supply", "WritesTo", curve_offset=-12.0, label_pct=0.38),
                HsdgEdgeSpec("cond_shares", "st_assets", "ReadsFrom", curve_offset=-14.0, label_pct=0.48),
                HsdgEdgeSpec("cond_shares", "st_supply", "ReadsFrom", curve_offset=-10.0, label_pct=0.36),
                HsdgEdgeSpec("fn_deposit", "ext_erc20", "Invokes", curve_offset=0.0, label_pct=0.52),
                HsdgEdgeSpec("ext_erc20", "st_assets", "WritesTo", curve_offset=16.0, label_pct=0.64),
                HsdgEdgeSpec("fn_redeem", "st_supply", "ReadsFrom", curve_offset=14.0, label_pct=0.52),
                HsdgEdgeSpec("fn_redeem", "st_assets", "WritesTo", curve_offset=16.0, label_pct=0.64),
            ]

        for n in nodes:
            item = HsdgNodeItem(n)
            self._scene.addItem(item)
            self._node_items[n.node_id] = item

        for e in edges:
            if e.src_id in self._node_items and e.dst_id in self._node_items:
                edge_item = HsdgEdgeItem(self._node_items[e.src_id], self._node_items[e.dst_id], e)
                self._scene.addItem(edge_item)
                self._edge_items.append(edge_item)

        self._scene.setSceneRect(-510, -135, 1020, 270)
