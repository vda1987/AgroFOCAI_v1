# Review of the second example

User request:

> Add a school canteen as a food-system actor. It receives food products from food companies and provides them to consumers. Use existing ontology classes and relations whenever possible.

Observed behavior in the screenshot:

- `School Canteen` was proposed as an `OperationalActor`-like new concept.
- The student did not simply fail; it produced a renderable graph.
- It selected `requiresResource` in a connection involving `FoodCompany`.
- It also used `providesResource` in a connection to `Consumer`.
- At least some endpoints appeared as unresolved placeholders.

Interpretation:

The main problem is semantic decomposition. Relations such as `requiresResource`, `receivesResource`, and `providesResource` are actor/resource relations in the current ontology. The natural-language sentence describes an actor-to-actor transfer mediated by a food resource. A robust ontology editor should therefore normally introduce/reuse a `Resource`/`FoodProduct` node and connect actors through that resource rather than forcing the actor names directly into resource-valued edge targets.

This is exactly the kind of error that should *not* prevent rendering. The v2 app keeps the graph visible, checks declared property domain/range, marks incompatible relations as `conflict`, and lets the expert repair them manually or through another natural-language instruction.
