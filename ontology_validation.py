from __future__ import annotations

import copy
from collections import defaultdict, deque


def _node_map(state: dict):
    return {n.get('id'): n for n in state.get('nodes', [])}


def _parents(state: dict):
    parents = defaultdict(set)
    for e in state.get('edges', []):
        if e.get('edge_kind') == 'hierarchy' or e.get('property') == 'subClassOf':
            parents[e.get('source')].add(e.get('target'))
    return parents


def is_same_or_subclass(child: str, parent: str, state: dict) -> bool:
    if child == parent:
        return True
    ps = _parents(state)
    seen = set()
    q = deque([child])
    while q:
        cur = q.popleft()
        for p in ps.get(cur, []):
            if p == parent:
                return True
            if p not in seen:
                seen.add(p)
                q.append(p)
    return False


def validate_edges(state: dict) -> dict:
    """Annotate model/manual relation edges using domain/range schema when available."""
    out = copy.deepcopy(state)
    schema = defaultdict(list)
    for e in out.get('edges', []):
        if e.get('edge_kind') == 'schema':
            schema[e.get('property')].append((e.get('source'), e.get('target')))

    nodes = _node_map(out)
    warnings = list(out.get('warnings') or [])
    for e in out.get('edges', []):
        if e.get('edge_kind') in {'schema', 'hierarchy'}:
            continue
        prop = e.get('property')
        candidates = schema.get(prop, [])
        if not candidates:
            if e.get('status') == 'existing':
                continue
            e['validation'] = 'unverified'
            continue
        src = e.get('source')
        tgt = e.get('target')
        ok = any(is_same_or_subclass(src, dom, out) and is_same_or_subclass(tgt, rng, out) for dom, rng in candidates)
        if ok:
            e['validation'] = 'valid'
        else:
            e['validation'] = 'conflict'
            e['status'] = 'conflict'
            expected = '; '.join(f'{d} → {r}' for d, r in candidates)
            warnings.append(
                f"Relation '{prop}' on {src} → {tgt} conflicts with declared domain/range ({expected})."
            )
    out['warnings'] = list(dict.fromkeys(warnings))
    return out
