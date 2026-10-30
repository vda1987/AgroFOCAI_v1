from __future__ import annotations

from typing import Any

import streamlit as st

try:
    from st_sigma import DisplayConfig, GraphConfig, LayoutConfig, sigma_graph
except Exception as exc:  # pragma: no cover - UI fallback
    DisplayConfig = GraphConfig = LayoutConfig = sigma_graph = None
    _SIGMA_IMPORT_ERROR = exc
else:
    _SIGMA_IMPORT_ERROR = None


# Visual families adapted from the previous ontology explorer.
ACTOR_CLASSES = {
    "FoodSystemActor", "OperationalActor", "InputManufacturer", "Producer",
    "FoodCompany", "RetailFoodService", "Consumer", "Processor", "Supplier",
}
INSTITUTIONAL_CLASSES = {
    "InstitutionalActor", "EducationActor", "Government", "FinanceActor", "NGO",
}
RESOURCE_CLASSES = {
    "Resource", "InputResource", "PrimaryFoodAndBiomass", "FoodProduct", "FoodOnReference",
}
FLOW_CLASSES = {"Flow", "ProductFlow", "InfluenceDemandFlow"}
OUTCOME_CLASSES = {
    "OneHealthOutcome", "HumanHealthNutritionOutcome", "EnvironmentalNaturalResourceOutcome",
}
CONTEXT_CLASSES = {
    "SystemContext", "RegulatoryInstitutionalSocialEnvironment", "FoodEnvironment",
    "EnvironmentalCondition", "ProductionSite",
}


def _parent_index(state: dict) -> dict[str, str | None]:
    return {str(n.get("id")): n.get("parent") for n in state.get("nodes", []) if n.get("id")}


def _ancestor_names(node_id: str, parents: dict[str, str | None], max_depth: int = 20) -> set[str]:
    out: set[str] = set()
    cur = node_id
    for _ in range(max_depth):
        parent = parents.get(cur)
        if not parent or parent in out:
            break
        out.add(str(parent))
        cur = str(parent)
    return out


def _semantic_category(node: dict, parents: dict[str, str | None]) -> str:
    node_id = str(node.get("id") or "")
    status = str(node.get("status") or "existing")
    if status == "conflict":
        return "Conflict"
    if status == "unresolved":
        return "Unresolved"
    if status == "proposed":
        return "Proposed"

    ancestry = _ancestor_names(node_id, parents) | {node_id}
    if ancestry & INSTITUTIONAL_CLASSES:
        return "Institutional actor"
    if ancestry & ACTOR_CLASSES:
        return "Food-system actor"
    if ancestry & RESOURCE_CLASSES:
        return "Resource"
    if ancestry & FLOW_CLASSES:
        return "Flow"
    if ancestry & OUTCOME_CLASSES:
        return "One Health outcome"
    if ancestry & CONTEXT_CLASSES:
        return "Context / site"
    if node.get("kind") == "individual":
        return "Individual"
    return "Concept"


def _visible_edges(
    state: dict,
    *,
    show_schema: bool,
    show_hierarchy: bool,
    show_restrictions: bool,
) -> list[dict]:
    result = []
    node_ids = {str(n.get("id")) for n in state.get("nodes", []) if n.get("id")}
    seen_ids: set[str] = set()

    for i, e in enumerate(state.get("edges", [])):
        kind = str(e.get("edge_kind") or "relation")
        if kind == "schema" and not show_schema:
            continue
        if kind == "hierarchy" and not show_hierarchy:
            continue
        if kind in {"restriction", "relation"} and not show_restrictions:
            continue
        src = str(e.get("source") or "")
        tgt = str(e.get("target") or "")
        if src not in node_ids or tgt not in node_ids:
            continue
        eid = str(e.get("id") or f"edge_{i}")
        if eid in seen_ids:
            eid = f"{eid}__{i}"
        seen_ids.add(eid)
        result.append({**e, "id": eid})
    return result


def _to_property_graph(
    state: dict,
    *,
    show_schema: bool,
    show_hierarchy: bool,
    show_restrictions: bool,
) -> dict:
    parents = _parent_index(state)
    nodes = []
    for n in state.get("nodes", []):
        nid = str(n.get("id") or "")
        if not nid:
            continue
        category = _semantic_category(n, parents)
        nodes.append({
            "id": nid,
            "labels": [category],
            "properties": {
                "name": n.get("label") or nid,
                "category": category,
                "status": n.get("status") or "existing",
                "kind": n.get("kind") or "class",
                "parent": n.get("parent") or "",
                "definition": n.get("definition") or "",
            },
        })

    edges = []
    for e in _visible_edges(
        state,
        show_schema=show_schema,
        show_hierarchy=show_hierarchy,
        show_restrictions=show_restrictions,
    ):
        kind = str(e.get("edge_kind") or "relation")
        prop = str(e.get("label") or e.get("property") or "relatedTo")
        edges.append({
            "id": str(e.get("id")),
            "source": str(e.get("source")),
            "target": str(e.get("target")),
            "type": prop,
            "directed": True,
            "properties": {
                "property": str(e.get("property") or prop),
                "kind": kind,
                "status": str(e.get("status") or "existing"),
                "validation": str(e.get("validation") or ""),
            },
        })
    return {"nodes": nodes, "edges": edges}


def _normalize_selection(result: Any) -> dict[str, list[str]]:
    empty = {"nodes": [], "edges": []}
    if result is None:
        return empty

    selection = getattr(result, "selection", None)
    if selection is None and isinstance(result, dict):
        selection = result.get("selection", result)

    if selection is None:
        clicked = getattr(result, "clicked", None)
        if isinstance(clicked, dict):
            ident = clicked.get("id")
            typ = clicked.get("type")
            if ident and typ == "node":
                return {"nodes": [str(ident)], "edges": []}
            if ident and typ == "edge":
                return {"nodes": [], "edges": [str(ident)]}
        return empty

    if isinstance(selection, dict):
        return {
            "nodes": [str(x) for x in (selection.get("nodes") or [])],
            "edges": [str(x) for x in (selection.get("edges") or [])],
        }

    nodes = getattr(selection, "nodes", None)
    edges = getattr(selection, "edges", None)
    return {
        "nodes": [str(x) for x in (nodes or [])],
        "edges": [str(x) for x in (edges or [])],
    }


def render_graph(
    state: dict,
    *,
    show_schema: bool = True,
    show_hierarchy: bool = True,
    show_restrictions: bool = True,
    physics: bool = True,
    height: int = 760,
):
    """Render a spring-based interactive graph and return persistent selection.

    Sigma.js is used because it provides ForceAtlas2, smooth drag/pan/zoom,
    edge/node selection returned to Python, fullscreen, and post-drag spring
    relaxation.
    """
    if sigma_graph is None:
        st.error(
            "The graph renderer is not installed. Run: "
            "python -m pip install streamlit-sigmajs>=0.3.0"
        )
        if _SIGMA_IMPORT_ERROR:
            st.caption(str(_SIGMA_IMPORT_ERROR))
        return {"nodes": [], "edges": []}

    graph = _to_property_graph(
        state,
        show_schema=show_schema,
        show_hierarchy=show_hierarchy,
        show_restrictions=show_restrictions,
    )

    display = DisplayConfig(
        node_size_mode="auto",
        node_size=11,
        node_color_field="category",
        node_label_field="name",
        node_labels="auto",
        edge_labels="hover",
        node_label_size=11,
        edge_label_size=7,
        label_density=0.72,
        label_rendered_size_threshold=5,
        properties_panel="compact",
        show_legend=True,
        legend_collapsed=False,
        show_fullscreen_button=True,
        selection_dimming=0.58,
        hide_edges_on_move=False,
    )

    layout = LayoutConfig(
        name="forceatlas2" if physics else "none",
        iterations=700 if physics else 1,
        dynamic_after_drag=bool(physics),
        drag_relaxation_ms=1500 if physics else 0,
    )
    config = GraphConfig(display=display, layout=layout)

    result = sigma_graph(
        graph,
        height=height,
        theme="humanistic",
        config=config,
        key="food-system-ontology-graph",
    )
    return _normalize_selection(result)
