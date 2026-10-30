from __future__ import annotations

import copy
import re
from io import BytesIO
from typing import Iterable

from rdflib import BNode, Graph, Literal, Namespace, OWL, RDF, RDFS, URIRef

from graph_state import edge_id, empty_state, slug

DEFAULT_NS = 'https://food-system-ontology-explorer.streamlit.app/ontology/food-system#'


def local_name(uri) -> str:
    s = str(uri)
    if '#' in s:
        return s.rsplit('#', 1)[1]
    return s.rstrip('/').rsplit('/', 1)[-1]


def _first_literal(g: Graph, subject, predicates: Iterable[URIRef]) -> str | None:
    for p in predicates:
        for o in g.objects(subject, p):
            if isinstance(o, Literal):
                return str(o)
    return None


def detect_namespace(g: Graph) -> str:
    for prefix, ns in g.namespaces():
        if prefix in {'', 'fs', 'food', 'fso'}:
            return str(ns)
    for s in g.subjects(RDF.type, OWL.Class):
        if isinstance(s, URIRef):
            text = str(s)
            if '#' in text:
                return text.rsplit('#', 1)[0] + '#'
            return text.rsplit('/', 1)[0] + '/'
    return DEFAULT_NS


def parse_ttl_bytes(data: bytes, filename: str = 'ontology.ttl') -> tuple[dict, str]:
    g = Graph()
    g.parse(data=data, format='turtle')
    ns = detect_namespace(g)
    state = empty_state()
    state['meta'] = {'namespace': ns, 'filename': filename, 'triple_count': len(g)}

    classes = set(g.subjects(RDF.type, OWL.Class))
    # Some ontologies use rdfs:Class explicitly.
    classes |= set(g.subjects(RDF.type, RDFS.Class))
    classes = {c for c in classes if isinstance(c, URIRef)}

    for c in sorted(classes, key=lambda x: local_name(x).casefold()):
        cid = local_name(c)
        label = _first_literal(g, c, [RDFS.label]) or cid
        definition = _first_literal(g, c, [RDFS.comment])
        parents = [o for o in g.objects(c, RDFS.subClassOf) if isinstance(o, URIRef)]
        state['nodes'].append({
            'id': cid,
            'label': label,
            'kind': 'class',
            'parent': local_name(parents[0]) if parents else None,
            'definition': definition,
            'status': 'existing',
            'iri': str(c),
            'source': 'ttl',
        })

    ids = {n['id'] for n in state['nodes']}
    # Named subclass edges.
    for c in classes:
        for parent in g.objects(c, RDFS.subClassOf):
            if isinstance(parent, URIRef) and local_name(parent) in ids:
                src, tgt = local_name(c), local_name(parent)
                state['edges'].append({
                    'id': edge_id(src, 'subClassOf', tgt),
                    'source': src,
                    'property': 'subClassOf',
                    'target': tgt,
                    'label': 'subClassOf',
                    'status': 'existing',
                    'edge_kind': 'hierarchy',
                    'property_iri': str(RDFS.subClassOf),
                    'origin': 'ttl',
                })

    # Object property schema edges: one edge for each domain/range pair.
    obj_props = {p for p in g.subjects(RDF.type, OWL.ObjectProperty) if isinstance(p, URIRef)}
    for p in sorted(obj_props, key=lambda x: local_name(x).casefold()):
        domains = [d for d in g.objects(p, RDFS.domain) if isinstance(d, URIRef)]
        ranges = [r for r in g.objects(p, RDFS.range) if isinstance(r, URIRef)]
        for d in domains:
            for r in ranges:
                did, rid = local_name(d), local_name(r)
                if did in ids and rid in ids:
                    pid = local_name(p)
                    state['edges'].append({
                        'id': edge_id(did, pid, rid, 'schema'),
                        'source': did,
                        'property': pid,
                        'target': rid,
                        'label': pid,
                        'status': 'existing',
                        'edge_kind': 'schema',
                        'property_iri': str(p),
                        'origin': 'ttl',
                    })

    # Existential/allValues restrictions as semantic edges.
    for c in classes:
        cid = local_name(c)
        for restriction in g.objects(c, RDFS.subClassOf):
            if not isinstance(restriction, BNode):
                continue
            prop = next(iter(g.objects(restriction, OWL.onProperty)), None)
            target = next(iter(g.objects(restriction, OWL.someValuesFrom)), None)
            quant = 'someValuesFrom'
            if target is None:
                target = next(iter(g.objects(restriction, OWL.allValuesFrom)), None)
                quant = 'allValuesFrom'
            if isinstance(prop, URIRef) and isinstance(target, URIRef) and local_name(target) in ids:
                pid, tid = local_name(prop), local_name(target)
                state['edges'].append({
                    'id': edge_id(cid, pid, tid, quant),
                    'source': cid,
                    'property': pid,
                    'target': tid,
                    'label': pid,
                    'status': 'existing',
                    'edge_kind': 'restriction',
                    'restriction_kind': quant,
                    'property_iri': str(prop),
                    'origin': 'ttl',
                })

    return state, data.decode('utf-8', errors='replace')


def _safe_fragment(value: str) -> str:
    return slug(value, 'UnresolvedConcept')


def compile_state_to_ttl(state: dict, namespace: str | None = None) -> str:
    """Compile the editable graph to valid Turtle.

    This intentionally serializes the editable semantic graph, not every untouched
    axiom from the original ontology. For production integration, apply these
    changes to the application's existing RDF backend instead.
    """
    ns = namespace or state.get('meta', {}).get('namespace') or DEFAULT_NS
    g = Graph()
    NS = Namespace(ns)
    g.bind('fs', NS)
    g.bind('owl', OWL)
    g.bind('rdfs', RDFS)

    nodes = {n['id']: n for n in state.get('nodes', [])}
    for n in state.get('nodes', []):
        uri = URIRef(n.get('iri')) if n.get('iri') else NS[_safe_fragment(n['id'])]
        if n.get('kind') == 'individual':
            g.add((uri, RDF.type, OWL.NamedIndividual))
        else:
            g.add((uri, RDF.type, OWL.Class))
        if n.get('label'):
            g.add((uri, RDFS.label, Literal(n['label'])))
        if n.get('definition'):
            g.add((uri, RDFS.comment, Literal(n['definition'])))

    for e in state.get('edges', []):
        src_n = nodes.get(e.get('source'))
        tgt_n = nodes.get(e.get('target'))
        if not src_n or not tgt_n:
            continue
        src = URIRef(src_n.get('iri')) if src_n.get('iri') else NS[_safe_fragment(src_n['id'])]
        tgt = URIRef(tgt_n.get('iri')) if tgt_n.get('iri') else NS[_safe_fragment(tgt_n['id'])]
        kind = e.get('edge_kind')
        prop_id = e.get('property') or 'relatedTo'

        if kind == 'hierarchy' or prop_id == 'subClassOf':
            g.add((src, RDFS.subClassOf, tgt))
            continue

        prop = URIRef(e.get('property_iri')) if e.get('property_iri') else NS[_safe_fragment(prop_id)]
        g.add((prop, RDF.type, OWL.ObjectProperty))

        if kind == 'schema':
            g.add((prop, RDFS.domain, src))
            g.add((prop, RDFS.range, tgt))
        elif src_n.get('kind', 'class') == 'class' and tgt_n.get('kind', 'class') == 'class':
            r = BNode()
            g.add((src, RDFS.subClassOf, r))
            g.add((r, RDF.type, OWL.Restriction))
            g.add((r, OWL.onProperty, prop))
            if e.get('restriction_kind') == 'allValuesFrom':
                g.add((r, OWL.allValuesFrom, tgt))
            else:
                g.add((r, OWL.someValuesFrom, tgt))
        else:
            g.add((src, prop, tgt))

    return g.serialize(format='turtle')
