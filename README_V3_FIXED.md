# Ontology NL Editor v3 fixed

This build fixes student-edge origin metadata, materializes `parent` fields as real `subClassOf` edges, adds conservative incomplete-proposal warnings, and opens the Sigma/ForceAtlas2 visualization with smaller nodes, hover-only edge labels, lower label density, more stabilization iterations, and longer post-drag relaxation.

It does not invent missing ontology relations: if the student omits requested relations, the app warns rather than fabricating them.
