"""Pure placement rules mirrored by KeystoneMeta.lua.

These helpers exist so attachment, clamping, and height selection can be
tested without the WoW client. The Lua addon must keep the same names
and numeric constants.
"""

from __future__ import annotations

ATTACH_GAP = 10
SCREEN_MARGIN = 16
MAIN_W = 318
MAIN_H_PENDING = 220
MAIN_H_POPULATED = 370
MAIN_H_MAX = 480
FOOTER_LINE_GAP = 8
POPULATED_CHROME = 154
ROW_H = 28
DETAIL_W = 348
DETAIL_H = 380
SETTINGS_W = 340
ACTION_BAR_CLEARANCE = 140
TOOLTIP_MAX_WIDTH = 280
TOOLTIP_EST_H = 160


def panel_height_for_status(status: str) -> int:
    if status == "ok":
        return MAIN_H_POPULATED
    return MAIN_H_PENDING


def cutoffs_is_usable(panel: dict | None) -> bool:
    if not panel:
        return False
    return bool(panel.get("shown"))


def has_horizontal_space(
    anchor_right: float | None,
    parent_right: float | None,
    panel_width: float,
    scale: float = 1.0,
    gap: float = ATTACH_GAP,
    margin: float = SCREEN_MARGIN,
) -> bool:
    if anchor_right is None or parent_right is None:
        return False
    available = (parent_right - margin) - (anchor_right + gap)
    return available >= (panel_width * scale)


def clamp_rect(
    left: float,
    bottom: float,
    width: float,
    height: float,
    parent_left: float,
    parent_bottom: float,
    parent_right: float,
    parent_top: float,
    margin: float = SCREEN_MARGIN,
    scale: float = 1.0,
) -> tuple[float, float]:
    eff_w = width * scale
    eff_h = height * scale
    new_left = left
    new_bottom = bottom
    min_left = parent_left + margin
    min_bottom = parent_bottom + margin
    max_left = parent_right - margin - eff_w
    max_bottom = parent_top - margin - eff_h
    if new_left < min_left:
        new_left = min_left
    if new_left > max_left:
        new_left = max_left
    if new_bottom < min_bottom:
        new_bottom = min_bottom
    if new_bottom > max_bottom:
        new_bottom = max_bottom
    if new_left < min_left:
        new_left = min_left
    if new_bottom < min_bottom:
        new_bottom = min_bottom
    return new_left, new_bottom


def default_standalone_point(
    parent_width: float,
    parent_height: float,
    panel_width: float = MAIN_W,
    panel_height: float = MAIN_H_PENDING,
    scale: float = 1.0,
    margin: float = SCREEN_MARGIN,
) -> tuple[float, float]:
    eff_w = panel_width * scale
    left = parent_width - margin - eff_w - 32
    bottom = max(margin + ACTION_BAR_CLEARANCE, (parent_height - panel_height * scale) / 2)
    return clamp_rect(
        left,
        bottom,
        panel_width,
        panel_height,
        0,
        0,
        parent_width,
        parent_height,
        margin,
        scale,
    )


def choose_placement(
    challenges_shown: bool,
    challenges_right: float | None,
    cutoffs: dict | None,
    parent_right: float | None,
    panel_width: float = MAIN_W,
    scale: float = 1.0,
    hold_standalone: bool = False,
) -> str:
    """Return attach_challenges, attach_cutoffs, pending_attach, or standalone. Never attach_below."""
    if hold_standalone or not challenges_shown:
        return "standalone"
    if cutoffs_is_usable(cutoffs):
        return "attach_cutoffs"
    if challenges_right is None:
        return "pending_attach"
    return "attach_challenges"


def choose_detail_side(
    main_left: float | None,
    main_right: float | None,
    parent_left: float | None,
    parent_right: float | None,
    detail_w: float = DETAIL_W,
    scale: float = 1.0,
    margin: float = SCREEN_MARGIN,
    objectives_left: float | None = None,
    objectives_right: float | None = None,
) -> str:
    need = detail_w * scale + margin
    right_room = main_right is not None and parent_right is not None and (parent_right - main_right) >= need
    left_room = main_left is not None and parent_left is not None and (main_left - parent_left) >= need
    right_hits_obj = False
    if objectives_left is not None and objectives_right is not None and main_right is not None:
        placed_left = main_right + 4
        placed_right = placed_left + (detail_w * scale)
        right_hits_obj = placed_left < objectives_right and placed_right > objectives_left
    if right_hits_obj and left_room:
        return "left"
    if right_room:
        return "right"
    if left_room:
        return "left"
    return "standalone"


def _overlap_area(a: dict, b: dict) -> float:
    if a["left"] >= b["right"] or a["right"] <= b["left"] or a["bottom"] >= b["top"] or a["top"] <= b["bottom"]:
        return 0.0
    width = min(a["right"], b["right"]) - max(a["left"], b["left"])
    height = min(a["top"], b["top"]) - max(a["bottom"], b["bottom"])
    return max(0.0, width) * max(0.0, height)


def choose_tooltip_side(
    owner_left: float,
    owner_right: float,
    owner_top: float,
    owner_bottom: float,
    parent_left: float = 0,
    parent_right: float = 1600,
    parent_top: float = 900,
    parent_bottom: float = 0,
    tooltip_w: float = TOOLTIP_MAX_WIDTH,
    tooltip_h: float = TOOLTIP_EST_H,
    main_rect: dict | None = None,
    objectives_rect: dict | None = None,
    margin: float = SCREEN_MARGIN,
) -> str:
    def placed(side: str) -> dict:
        if side == "right":
            left = owner_right + 6
            right = left + tooltip_w
        else:
            right = owner_left - 6
            left = right - tooltip_w
        top = owner_top + 6
        return {"left": left, "right": right, "top": top, "bottom": top - tooltip_h, "side": side}

    def has_room(side: str) -> bool:
        if side == "right":
            return parent_right - owner_right >= (tooltip_w + margin)
        return owner_left - parent_left >= (tooltip_w + margin)

    def score(rect: dict) -> float:
        value = (parent_right - owner_right) if rect["side"] == "right" else (owner_left - parent_left)
        if rect["left"] < parent_left + margin or rect["right"] > parent_right - margin:
            value -= 10000
        if objectives_rect and _overlap_area(rect, objectives_rect) > 0:
            value -= 5000
        if main_rect:
            main_area = max(1.0, (main_rect["right"] - main_rect["left"]) * (main_rect["top"] - main_rect["bottom"]))
            covered = _overlap_area(rect, main_rect)
            if covered > (main_area * 0.45):
                value -= 8000
            else:
                value -= covered * 0.02
        return value

    right = placed("right")
    left = placed("left")
    if objectives_rect:
        if _overlap_area(right, objectives_rect) > 0 and has_room("left"):
            return "left"
        if _overlap_area(left, objectives_rect) > 0 and has_room("right"):
            return "right"
    if score(left) > score(right):
        return "left"
    return "right"
