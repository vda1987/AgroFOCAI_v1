from __future__ import annotations

import copy
import hashlib
import re
from typing import Any


def empty_state() -> dict:
    return {
        'nodes': [],
        'edges': [],
        'notes': [],
        'warnings': [],
        'meta': {},
    }


def norm_text(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '').strip()).casefold()


def slug(value: str, fallback: str = 'node') -> str:
    value = str(value or fallback).strip()
    value = re.sub(r'[^A-Za-z0-9_\-]+', '_', value)
    value = re.sub(r'_+', '_', value).strip('_')
    return value or fallback


def edge_id(source: str, prop: str, target: str, suffix: str = '') -> str:
    base = f'{source}|{prop}|{target}|{suffix}'
    return 'e_' + hashlib.sha1(base.encode('utf-8')).hexdigest()[:12]


def _node_indexes(state: dict):
    by_id = {}
    by_label = {}
    for n in state.get('nodes', []):
        nid = str(n.get('id', ''))
        if nid:
            by_id[nid] = n
            by_id[nid.casefold()] = n
        label = norm_text(n.get('label'))
        if label:
            by_label.setdefault(label, n)
    return by_id, by_label


def resolve_node_ref(state: dict, ref: str | None) -> str | None:
    if not ref:
        return None
    by_id, by_label = _node_indexes(state)
    s = str(ref).strip()
    hit = by_id.get(s) or by_id.get(s.casefold())
    if hit:
        return hit['id']
    hit = by_label.get(norm_text(s))
    if hit:
        return hit['id']
    return None


def ensure_node(state: dict, ref: str, *, label: str | None = None, status: str = 'unresolved') -> str:
    resolved = resolve_node_ref(state, ref)
    if resolved:
        return resolved
    nid = slug(ref, 'UnresolvedConcept')
    existing_ids = {n['id'] for n in state.get('nodes', [])}
    base = nid
    i = 2
    while nid in existing_ids:
        nid = f'{base}_{i}'
        i += 1
    state.setdefault('nodes', []).append({
        'id': nid,
        'label': label or ref,
        'kind': 'class',
        'parent': None,
        'definition': None,
        'status': status,
        'iri': None,
        'source': 'student-placeholder',
    })
    return nid


def merge_student_proposal(state: dict, proposal: dict) -> tuple[dict, dict]:
    """Merge a model proposal into current graph instead of replacing it.

    Reuses nodes by exact id or normalized label. Missing edge endpoints become
    visible unresolved placeholders so rendering never fails closed.
    """
    new_state = copy.deepcopy(state)
    report = {'nodes_added': 0, 'nodes_reused': 0, 'edges_added': 0, 'warnings': []}

    for raw in proposal.get('nodes', []) or []:
        rid = str(raw.get('id') or raw.get('label') or 'UnresolvedConcept')
        label = raw.get('label') or rid
        resolved = resolve_node_ref(new_state, rid) or resolve_node_ref(new_state, label)
        if resolved:
            report['nodes_reused'] += 1
            node = next(n for n in new_state['nodes'] if n['id'] == resolved)
            # Do not silently overwrite ontology-backed fields with weak model guesses.
            if not node.get('definition') and raw.get('definition'):
                node['definition'] = raw.get('definition')
            continue

        nid = slug(rid)
        ids = {n['id'] for n in new_state['nodes']}
        base = nid
        i = 2
        while nid in ids:
            nid = f'{base}_{i}'
            i += 1
        parent = raw.get('parent')
        parent_resolved = resolve_node_ref(new_state, parent) if parent else None
        resolved_parent = parent_resolved or parent
        new_state['nodes'].append({
            'id': nid,
            'label': label,
            'kind': raw.get('kind') or 'class',
            'parent': resolved_parent,
            'definition': raw.get('definition'),
            'status': raw.get('status') or 'proposed',
            'iri': None,
            'origin': 'student',
        })
        report['nodes_added'] += 1

        # A parent supplied by the student is a structural change, not merely
        # display metadata. Materialize it as a real hierarchy edge so it is
        # visible in the graph and serializes to rdfs:subClassOf.
        if resolved_parent:
            parent_id = resolve_node_ref(new_state, str(resolved_parent))
            if parent_id:
                hkey = (nid, 'subClassOf', parent_id)
                existing_h = {
                    (e.get('source'), e.get('property'), e.get('target'))
                    for e in new_state.get('edges', [])
                }
                if hkey not in existing_h:
                    new_state.setdefault('edges', []).append({
                        'id': edge_id(nid, 'subClassOf', parent_id, 'hierarchy'),
                        'source': nid,
                        'property': 'subClassOf',
                        'target': parent_id,
                        'label': 'subClassOf',
                        'status': raw.get('status') or 'proposed',
                        'edge_kind': 'hierarchy',
                        'property_iri': None,
                        'origin': 'student',
                    })
                    report['edges_added'] += 1
            else:
                report['warnings'].append(
                    f'Parent reference could not be resolved for {nid}: {resolved_parent}'
                )

    existing_edge_keys = {
        (e.get('source'), e.get('property'), e.get('target')) for e in new_state.get('edges', [])
    }

    for raw in proposal.get('edges', []) or []:
        sref = raw.get('source')
        tref = raw.get('target')
        prop = str(raw.get('property') or raw.get('relation') or 'relatedTo')
        src = resolve_node_ref(new_state, sref)
        tgt = resolve_node_ref(new_state, tref)
        if not src:
            src = ensure_node(new_state, str(sref or 'UnresolvedSource'))
            report['warnings'].append(f'Created unresolved source placeholder for: {sref}')
        if not tgt:
            tgt = ensure_node(new_state, str(tref or 'UnresolvedTarget'))
            report['warnings'].append(f'Created unresolved target placeholder for: {tref}')
        key = (src, prop, tgt)
        if key in existing_edge_keys:
            continue
        eid = edge_id(src, prop, tgt, str(len(new_state.get('edges', []))))
        new_state.setdefault('edges', []).append({
            'id': eid,
            'source': src,
            'property': prop,
            'target': tgt,
            'label': raw.get('label') or prop,
            'status': raw.get('status') or 'proposed',
            'edge_kind': 'relation',
            'property_iri': None,
            'origin': 'student',
        })
        existing_edge_keys.add(key)
        report['edges_added'] += 1

    new_state['notes'] = list(dict.fromkeys((new_state.get('notes') or []) + (proposal.get('notes') or [])))
    new_state['warnings'] = list(dict.fromkeys((new_state.get('warnings') or []) + (proposal.get('warnings') or []) + report['warnings']))
    return new_state, report



def audit_proposal_completeness(instruction: str, proposal: dict, report: dict) -> list[str]:
    """Return conservative warnings when a compound request appears under-realized.

    This does not invent ontology facts or repair semantics. It only detects
    obvious mismatches between the shape of the request and the shape of the
    returned delta so partial model output is visible to the user.
    """
    text = norm_text(instruction)
    warnings: list[str] = []
    nodes = proposal.get('nodes', []) or []
    edges = proposal.get('edges', []) or []

    relation_cues = (
        'connect', 'relation', 'receiv', 'provid', 'produce', 'interact',
        'link', 'source', 'target', 'can ', 'capab', 'from ', ' to ',
    )
    hierarchy_cues = ('subclass', 'sub class', 'make it a', 'classify', 'under ')

    if nodes and any(cue in text for cue in relation_cues) and not edges:
        warnings.append(
            'Incomplete proposal: the instruction appears to request one or more '
            'relationships, but the student returned no explicit relationship edges.'
        )

    has_parent = any(n.get('parent') for n in nodes if isinstance(n, dict))
    has_hierarchy_edge = any(
        str(e.get('property') or e.get('relation') or '').casefold()
        in {'subclassof', 'subclass', 'is_a', 'isa'}
        for e in edges if isinstance(e, dict)
    )
    if any(cue in text for cue in hierarchy_cues) and not (has_parent or has_hierarchy_edge):
        warnings.append(
            'Incomplete proposal: the instruction appears to request a hierarchy change, '
            'but the student returned neither a parent nor a subclass edge.'
        )

    if report.get('nodes_added', 0) > 0 and report.get('edges_added', 0) == 0 and any(cue in text for cue in relation_cues + hierarchy_cues):
        warnings.append(
            'Only isolated node content was added. Review the proposal before treating '
            'the requested semantic structure as complete.'
        )

    return list(dict.fromkeys(warnings))

def delete_selected(state: dict, node_ids: list[str], edge_ids: list[str]) -> dict:
    new_state = copy.deepcopy(state)
    nodes_to_delete = set(node_ids)
    edges_to_delete = set(edge_ids)
    new_state['nodes'] = [n for n in new_state.get('nodes', []) if n.get('id') not in nodes_to_delete]
    new_state['edges'] = [
        e for e in new_state.get('edges', [])
        if e.get('id') not in edges_to_delete
        and e.get('source') not in nodes_to_delete
        and e.get('target') not in nodes_to_delete
    ]
    return new_state


def compact_for_student(state: dict, max_nodes: int = 80, max_edges: int = 140) -> dict:
    nodes = state.get('nodes', [])[:max_nodes]
    allowed = {n.get('id') for n in nodes}
    edges = [e for e in state.get('edges', []) if e.get('source') in allowed and e.get('target') in allowed][:max_edges]
    return {
        'nodes': [
            {k: n.get(k) for k in ('id', 'label', 'kind', 'parent', 'status')}
            for n in nodes
        ],
        'edges': [
            {k: e.get(k) for k in ('source', 'property', 'target', 'status', 'edge_kind')}
            for e in edges
        ],
    }
