"""Registry dispatcher for deterministic Monday SVG visual generation."""
from __future__ import annotations

from . import (
    angle_circle,
    angle_relation,
    equation_circle,
    function_graph,
    inverse_graph,
    radian_sector,
    right_triangle,
    special_angles_circle,
    triangle_general,
    vector_rotation,
    wave_graph,
    wave_sum_product,
)
from .formula_diagrams import render_missing_formula

REGISTRY = {
    "angle_circle": angle_circle.render,
    "angle_relation": angle_relation.render,
    "radian_sector": radian_sector.render,
    "right_triangle": right_triangle.render,
    "special_angles_circle": special_angles_circle.render,
    "vector_rotation": vector_rotation.render,
    "wave_graph": wave_graph.render,
    "wave_sum_product": wave_sum_product.render,
    "inverse_graph": inverse_graph.render,
    "equation_circle": equation_circle.render,
    "triangle_general": triangle_general.render,
    "function_graph": function_graph.render,
}


def render_visual(vtype: str, params: dict, aria_label: str = "") -> str:
    fn = REGISTRY.get(vtype)
    if not fn:
        raise KeyError(f"Unknown registry visual type: {vtype}")
    return fn(params or {}, aria_label=aria_label)


__all__ = ["REGISTRY", "render_visual", "render_missing_formula"]
