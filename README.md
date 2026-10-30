# Ontology NL Editor v2

Streamlit front-end for editing a food-system ontology graph with both direct interaction and natural-language instructions.

## What changed from v1

- Loads an existing `.ttl` ontology into the editor.
- Dynamic Cytoscape.js visualization with force-directed layouts (`fcose` / `cose`), zoom, pan, fit and node dragging.
- Student output is merged as a delta instead of replacing the whole graph.
- Existing nodes are reused by identifier or normalized label.
- Missing edge endpoints become visible unresolved placeholders instead of crashing rendering.
- Domain/range checks mark incompatible generated connections as `conflict` while still rendering them.
- Mouse selection allows editing/deleting nodes and edges through forms.
- Manual creation of nodes and connections.
- Undo history.
- Turtle is serialized in the background and only exposed as a download.

## Install

Inside the environment used for Streamlit:

```cmd
python -m pip install -r requirements.txt
```

## Run

Keep the local student API running, then:

```cmd
python -m streamlit run app.py
```

Use the same API URL and token as the local FastAPI student server.

## Typical workflow

1. Upload the current ontology `.ttl`.
2. Explore it with the force-directed graph.
3. Enter a natural-language request.
4. The student proposes nodes/connections.
5. The proposal is merged into the loaded graph.
6. Incompatible domain/range relations are visibly marked as conflicts rather than blocking rendering.
7. Select nodes/edges with the mouse to edit or delete them, or issue another text instruction.
8. Download the regenerated Turtle when desired.

## Important prototype limitation

This Streamlit v2 serializes the *editable semantic graph* back to Turtle. It does not yet guarantee byte-for-byte preservation of every untouched OWL axiom/annotation from the original TTL. For production integration, wire the same GraphState/ChangeSet operations into the RDF backend of the existing ontology editor so untouched axioms are preserved exactly.

## Why the second School Canteen example is useful

The current student proposed `requiresResource` toward `FoodCompany` for the phrase “receives food products from food companies” and also produced unresolved actor references. This is a semantic decomposition error, not a rendering failure: the ontology models resource relations to `Resource`, not direct actor-to-actor transfer in that form. v2 therefore keeps the proposal visible but marks domain/range-incompatible edges as conflicts. The user can then correct them by mouse or by another text instruction.
