from __future__ import annotations

import copy
import json

import streamlit as st

from api_client import health, interpret
from graph_view import render_graph
from graph_state import audit_proposal_completeness, compact_for_student, delete_selected, empty_state, merge_student_proposal
from manual_edit import add_edge, add_node, update_edge, update_node
from ontology_validation import validate_edges
from ttl_io import compile_state_to_ttl, parse_ttl_bytes

st.set_page_config(page_title='Food-system ontology editor', layout='wide')


def _secret(name: str, default: str = '') -> str:
    try:
        return str(st.secrets.get(name, default))
    except Exception:
        return default


def snapshot():
    st.session_state.history.append(copy.deepcopy(st.session_state.graph_state))
    if len(st.session_state.history) > 30:
        st.session_state.history = st.session_state.history[-30:]


def set_state(new_state: dict):
    st.session_state.graph_state = validate_edges(new_state)


if 'graph_state' not in st.session_state:
    st.session_state.graph_state = empty_state()
if 'history' not in st.session_state:
    st.session_state.history = []
if 'ttl_source_name' not in st.session_state:
    st.session_state.ttl_source_name = None
if 'last_merge_report' not in st.session_state:
    st.session_state.last_merge_report = None
if 'graph_revision' not in st.session_state:
    st.session_state.graph_revision = 0

st.title('Food-system ontology editor')
st.caption('Load an ontology, edit the spring-based graph directly, or describe changes in ordinary language. Turtle stays in the backend.')

with st.sidebar:
    st.subheader('Student API')
    api_url = st.text_input('API URL', value=_secret('STUDENT_API_URL', 'http://127.0.0.1:8000'))
    api_token = st.text_input('API token', value=_secret('STUDENT_API_TOKEN', 'change-me'), type='password')
    if st.button('Check connection', use_container_width=True):
        try:
            st.success('API reachable')
            st.json(health(api_url))
        except Exception as e:
            st.error(f'Connection failed: {e}')

    st.divider()
    st.subheader('View')
    physics = st.checkbox('Spring physics', value=True)
    show_schema = st.checkbox('Property schema edges', value=True)
    show_hierarchy = st.checkbox('Hierarchy', value=True)
    show_restrictions = st.checkbox('Restrictions / proposed relations', value=True)

    st.divider()
    if st.button('Undo', disabled=not st.session_state.history, use_container_width=True):
        st.session_state.graph_state = st.session_state.history.pop()
        st.session_state.graph_revision += 1
        st.rerun()
    if st.button('Start empty graph', use_container_width=True):
        snapshot()
        st.session_state.graph_state = empty_state()
        st.session_state.ttl_source_name = None
        st.session_state.graph_revision += 1
        st.rerun()

# --- Load ontology ---------------------------------------------------------
st.subheader('1 · Load the current ontology')
load_col, info_col = st.columns([1.2, 1], gap='large')
with load_col:
    uploaded = st.file_uploader('Upload Turtle (.ttl)', type=['ttl'], accept_multiple_files=False)
    if uploaded is not None and st.button('Load ontology into editor', type='primary'):
        try:
            state, _ = parse_ttl_bytes(uploaded.getvalue(), uploaded.name)
            snapshot()
            set_state(state)
            st.session_state.ttl_source_name = uploaded.name
            st.session_state.graph_revision += 1
            st.success(f'Loaded {uploaded.name}')
            st.rerun()
        except Exception as e:
            st.error(f'Could not parse Turtle: {e}')
with info_col:
    gs = st.session_state.graph_state
    st.metric('Nodes', len(gs.get('nodes', [])))
    st.metric('Edges', len(gs.get('edges', [])))
    if st.session_state.ttl_source_name:
        st.caption(f"Current source: {st.session_state.ttl_source_name}")

# --- Natural-language editing --------------------------------------------
st.subheader('2 · Describe a change')
text = st.text_area(
    'Natural-language instruction',
    height=115,
    placeholder=(
        'Example: Add a school canteen as a food-system actor. It receives food products from food companies '
        'and provides them to consumers. Reuse existing ontology concepts and relations whenever possible.'
    ),
    label_visibility='collapsed',
)
text_b1, text_b2 = st.columns([1, 4])
with text_b1:
    run_text = st.button('Apply text change', type='primary', use_container_width=True, disabled=not text.strip())
with text_b2:
    st.caption('The student proposes a delta; existing graph content is preserved and the result is validated before display.')

if run_text:
    try:
        previous = compact_for_student(st.session_state.graph_state)
        with st.spinner('Interpreting with the local student...'):
            result = interpret(api_url, api_token, text, previous)
        snapshot()
        proposal = result['proposal']
        merged, report = merge_student_proposal(st.session_state.graph_state, proposal)
        completeness_warnings = audit_proposal_completeness(text, proposal, report)
        if completeness_warnings:
            report['warnings'] = list(dict.fromkeys((report.get('warnings') or []) + completeness_warnings))
            merged['warnings'] = list(dict.fromkeys((merged.get('warnings') or []) + completeness_warnings))
            report['proposal_complete'] = False
        else:
            report['proposal_complete'] = True
        set_state(merged)
        st.session_state.last_merge_report = report
        st.session_state.graph_revision += 1
        st.success(f"Applied proposal: +{report['nodes_added']} nodes, +{report['edges_added']} edges, {report['nodes_reused']} reused nodes.")
        st.rerun()
    except Exception as e:
        st.error(f'The student API could not complete the request: {e}')

if st.session_state.last_merge_report:
    report = st.session_state.last_merge_report
    if report.get('proposal_complete') is False:
        st.warning(
            'The latest student proposal appears incomplete. The recoverable changes were applied, '
            'but review the warnings and graph before accepting the semantic edit.'
        )
    with st.expander('Last student merge details'):
        st.json(report)

# --- Dynamic graph --------------------------------------------------------
st.subheader('3 · Inspect and edit the graph')
state = st.session_state.graph_state
if not state.get('nodes'):
    st.info('Load a TTL or create a graph with natural language/manual controls.')
    selection = {'nodes': [], 'edges': []}
else:
    selection = render_graph(
        state,
        physics=physics,
        show_schema=show_schema,
        show_hierarchy=show_hierarchy,
        show_restrictions=show_restrictions,
    ) or {'nodes': [], 'edges': []}

node_ids = {n.get('id') for n in state.get('nodes', []) if n.get('id')}
edge_ids = {e.get('id') for e in state.get('edges', []) if e.get('id')}

if isinstance(selection, dict):
    selected_nodes = [nid for nid in selection.get('nodes', []) if nid in node_ids]
    selected_edges = [eid for eid in selection.get('edges', []) if eid in edge_ids]
else:
    selected_nodes = [selection] if selection in node_ids else []
    selected_edges = [selection] if selection in edge_ids else []

if selected_nodes or selected_edges:
    st.caption(f"Selected nodes: {', '.join(selected_nodes) or '—'} · selected edges: {', '.join(selected_edges) or '—'}")

edit_tab, add_node_tab, add_edge_tab, warnings_tab = st.tabs(['Edit selection', 'Add node', 'Add connection', 'Validation'])

with edit_tab:
    if len(selected_nodes) == 1:
        nid = selected_nodes[0]
        node = next((n for n in state.get('nodes', []) if n.get('id') == nid), None)
        if node:
            with st.form(f'edit_node_{nid}'):
                st.write(f"**Node:** `{nid}`")
                label = st.text_input('Label', value=node.get('label') or nid)
                definition = st.text_area('Definition', value=node.get('definition') or '', height=90)
                save_node = st.form_submit_button('Save node')
            if save_node:
                snapshot()
                set_state(update_node(state, nid, label, definition))
                st.session_state.graph_revision += 1
                st.rerun()
    elif len(selected_edges) == 1:
        eid = selected_edges[0]
        edge = next((e for e in state.get('edges', []) if e.get('id') == eid), None)
        if edge:
            ids = [n['id'] for n in state.get('nodes', [])]
            with st.form(f'edit_edge_{eid}'):
                st.write(f"**Connection:** `{edge.get('property')}`")
                src = st.selectbox('Source', ids, index=ids.index(edge['source']) if edge.get('source') in ids else 0)
                prop = st.text_input('Property', value=edge.get('property') or 'relatedTo')
                tgt = st.selectbox('Target', ids, index=ids.index(edge['target']) if edge.get('target') in ids else 0)
                save_edge = st.form_submit_button('Save connection')
            if save_edge:
                snapshot()
                set_state(update_edge(state, eid, src, prop, tgt))
                st.session_state.graph_revision += 1
                st.rerun()
    else:
        st.info('Click one node or one edge in the graph to edit it. Drag nodes directly in the graph to explore the layout.')

    if selected_nodes or selected_edges:
        if st.button('Delete selected elements', type='secondary'):
            snapshot()
            set_state(delete_selected(state, selected_nodes, selected_edges))
            st.session_state.graph_revision += 1
            st.rerun()

with add_node_tab:
    ids = [n['id'] for n in state.get('nodes', [])]
    with st.form('add_node_form'):
        new_id = st.text_input('Identifier', placeholder='SchoolCanteen')
        new_label = st.text_input('Label', placeholder='School Canteen')
        parent_options = [''] + ids
        parent = st.selectbox('Parent class (optional)', parent_options)
        definition = st.text_area('Definition (optional)', height=80)
        create_node = st.form_submit_button('Add node')
    if create_node:
        try:
            snapshot()
            set_state(add_node(state, new_id, new_label, parent or None, definition))
            st.session_state.graph_revision += 1
            st.rerun()
        except Exception as e:
            st.error(str(e))

with add_edge_tab:
    ids = [n['id'] for n in state.get('nodes', [])]
    if len(ids) < 2:
        st.info('At least two nodes are needed.')
    else:
        with st.form('add_edge_form'):
            src = st.selectbox('Source node', ids, key='new_edge_src')
            prop = st.text_input('Relation/property', placeholder='providesResource')
            tgt = st.selectbox('Target node', ids, index=min(1, len(ids)-1), key='new_edge_tgt')
            create_edge = st.form_submit_button('Add connection')
        if create_edge:
            try:
                snapshot()
                set_state(add_edge(state, src, prop, tgt))
                st.session_state.graph_revision += 1
                st.rerun()
            except Exception as e:
                st.error(str(e))

with warnings_tab:
    warnings = state.get('warnings') or []
    conflicts = [e for e in state.get('edges', []) if e.get('validation') == 'conflict' or e.get('status') == 'conflict']
    c1, c2 = st.columns(2)
    c1.metric('Warnings', len(warnings))
    c2.metric('Conflicting connections', len(conflicts))
    if warnings:
        for w in warnings:
            st.warning(w)
    else:
        st.success('No current validation warnings.')
    if conflicts:
        st.dataframe(
            [{'source': e.get('source'), 'property': e.get('property'), 'target': e.get('target')} for e in conflicts],
            use_container_width=True,
            hide_index=True,
        )

# --- Background TTL -------------------------------------------------------
st.subheader('4 · Save')
st.caption('Turtle is generated in the background from the current editable graph; it is not shown in the normal interface.')
try:
    ttl = compile_state_to_ttl(state)
    st.download_button(
        'Download current TTL',
        data=ttl.encode('utf-8'),
        file_name='food_system_edited.ttl',
        mime='text/turtle',
        disabled=not bool(state.get('nodes')),
    )
except Exception as e:
    st.error(f'Could not serialize current graph: {e}')

with st.expander('Developer diagnostics'):
    st.json({'selection': selection, 'graph_meta': state.get('meta', {}), 'warnings': state.get('warnings', [])})
