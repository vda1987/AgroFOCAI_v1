# Ontology NL Editor V3 — Sigma.js / ForceAtlas2

This version keeps the V2 natural-language editing, GraphState, validation, TTL parsing/serialization, undo and manual edit forms, but replaces the graph renderer with `streamlit-sigmajs`.

## Why this renderer

- ForceAtlas2 layout
- real-time spring response after dragging nodes
- smooth zoom and pan
- directed edges
- visible relationship labels
- persistent node and edge selection returned to Streamlit
- fullscreen control
- semantic node coloring with a legend
- compact property inspector

The visual families follow the previous ontology explorer: food-system actors, institutional actors, resources, flows, One Health outcomes, contexts/sites, proposed concepts, unresolved concepts and conflicts.

## Install / upgrade

Inside the existing conda environment:

```cmd
conda activate ontology_qlora
set PYTHONPATH=
set PYTHONNOUSERSITE=1
python -m pip install -r requirements.txt
```

## Run

Keep the local student API running as before, then:

```cmd
cd /D D:\hs_osnabruck\ontologias\ontology_for_agent\ontology_nl_editor_v3
python -m streamlit run app.py
```

Use the same API URL and token as V2.

## Notes

`Spring physics` uses ForceAtlas2 and enables post-drag relaxation. Turning it off preserves a static layout mode. The current V3 still uses the same GraphState/TTL layer as V2; therefore it is a UI/rendering upgrade rather than a semantic-model change.
