from __future__ import annotations

import copy
from graph_state import edge_id, resolve_node_ref, slug


def add_node(state: dict, node_id: str, label: str, parent: str | None, definition: str | None) -> dict:
    out = copy.deepcopy(state)
    nid = slug(node_id or label, 'NewConcept')
    if any(n.get('id') == nid for n in out.get('nodes', [])):
        raise ValueError(f"A node with id '{nid}' already exists")
    out['nodes'].append({
        'id': nid,
        'label': label or nid,
        'kind': 'class',
        'parent': parent or None,
        'definition': definition or None,
        'status': 'proposed',
        'iri': None,
        'source': 'manual',
    })
    if parent:
        out['edges'].append({
            'id': edge_id(nid, 'subClassOf', parent),
            'source': nid,
            'property': 'subClassOf',
            'target': parent,
            'label': 'subClassOf',
            'status': 'proposed',
            'edge_kind': 'hierarchy',
            'property_iri': None,
            'source': 'manual',
        })
    return out


def update_node(state: dict, node_id: str, label: str, definition: str | None) -> dict:
    out = copy.deepcopy(state)
    node = next((n for n in out.get('nodes', []) if n.get('id') == node_id), None)
    if not node:
        raise ValueError('Selected node not found')
    node['label'] = label or node_id
    node['definition'] = definition or None
    if node.get('status') == 'existing':
        node['status'] = 'proposed'
    return out


def add_edge(state: dict, source: str, prop: str, target: str, edge_kind: str = 'relation') -> dict:
    out = copy.deepcopy(state)
    if not resolve_node_ref(out, source) or not resolve_node_ref(out, target):
        raise ValueError('Source and target must exist')
    if any(e.get('source') == source and e.get('property') == prop and e.get('target') == target for e in out.get('edges', [])):
        raise ValueError('This edge already exists')
    out['edges'].append({
        'id': edge_id(source, prop, target, str(len(out.get('edges', [])))),
        'source': source,
        'property': prop,
        'target': target,
        'label': prop,
        'status': 'proposed',
        'edge_kind': edge_kind,
        'property_iri': None,
        'source': 'manual',
    })
    return out


def update_edge(state: dict, edge_id_value: str, source: str, prop: str, target: str) -> dict:
    out = copy.deepcopy(state)
    edge = next((e for e in out.get('edges', []) if e.get('id') == edge_id_value), None)
    if not edge:
        raise ValueError('Selected edge not found')
    edge['source'] = source
    edge['property'] = prop
    edge['target'] = target
    edge['label'] = prop
    edge['status'] = 'proposed'
    edge['edge_kind'] = 'relation' if edge.get('edge_kind') == 'schema' else edge.get('edge_kind', 'relation')
    return out
