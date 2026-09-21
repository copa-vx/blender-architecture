# MCP — not implemented yet (intentionally)

README §17 is explicit:

> Cuando el generador local funcione, añadir MCP. **No empezar por MCP.**
>
> Primero: `Python → Blender`
> Después: `MCP → Python → Blender`

So Milestone 1 ships **no MCP server**. What lives here is the one piece MCP
will need on day one: the data contract.

## `schemas/house_schema.json`

A real JSON Schema (draft 2020-12) for the house model. It is the same
document that `blender/model/house.py` reads and writes, so an MCP tool that
validates against this schema is guaranteed to produce something the
generator can build.

Validate an example:

```bash
pip install check-jsonschema
check-jsonschema --schemafile mcp/schemas/house_schema.json examples/*.json
```

## When MCP lands (Milestone 4)

The server should stay a thin wrapper. The tools listed in README §18
(`create_house`, `create_room`, `add_window`, `modify_roof`, …) map almost
one-to-one onto operations on the `House` dataclass, which already validates
itself — so the MCP layer's job is transport and schema enforcement, not
geometry.

Suggested shape:

```
MCP tool call
    ↓  (validate against house_schema.json)
House.from_dict()
    ↓  House.validate()   ← rejects impossible geometry before Blender sees it
generate_house()
```

Nothing in `blender/model/` imports `bpy`, so an MCP server can hold and
mutate the model in a plain Python process and only hand it to Blender when
it actually needs to render.
