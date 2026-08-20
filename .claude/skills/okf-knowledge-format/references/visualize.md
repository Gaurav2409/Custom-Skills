# Visualize an OKF Bundle

Loaded when the user wants a graph view, viewer, or visualization of an OKF bundle.

## Google's Reference Visualizer (Self-Contained HTML)

```bash
cd knowledge-catalog/okf
.venv/bin/python -m enrichment_agent visualize \
    --bundle ./bundles/<name> \
    --out ./bundles/<name>/viz.html \
    --name "<Display Name>"
```

Open `viz.html` in any browser — no backend, no install on viewer side, no data leaves the page.

### What it shows

- **Force-directed graph** — concept nodes colored by `type`, directed edges from cross-links
- **Detail panel** — frontmatter + rendered markdown body; internal links rewired for in-viewer navigation
- **"Cited by" backlinks** — reverse of the link graph
- **Search box** — matches title, concept ID, tags
- **Type filter** + 5 layout modes (cose / concentric / breadth-first / circle / grid)

### Tech stack

The HTML embeds the bundle as a JSON blob and uses:
- [Cytoscape.js](https://js.cytoscape.org/) for the graph
- [marked](https://marked.js.org/) for markdown rendering
- Both CDN-loaded; bundle is parsed once at generation time and serialized into the file

## Custom Visualizer (when Google's agent isn't available)

### Option A: Cytoscape.js (matching Google's approach)

```python
import json, re, yaml
from pathlib import Path

def build_graph_data(bundle_root):
    bundle_root = Path(bundle_root)
    nodes, edges = [], []
    for f in bundle_root.rglob("*.md"):
        if f.name in {"index.md", "log.md"}:
            continue
        content = f.read_text(errors='ignore')
        if not content.startswith("---"):
            continue
        fm_end = content.find("---", 3)
        fm = yaml.safe_load(content[3:fm_end]) or {}
        body = content[fm_end+3:]
        cid = str(f.relative_to(bundle_root))[:-3]
        nodes.append({
            "data": {
                "id": cid,
                "label": fm.get("title", cid),
                "type": fm.get("type", "unknown"),
                "tags": fm.get("tags", []),
                "description": fm.get("description", ""),
            }
        })
        for m in re.finditer(r'\]\((/[^)]+\.md)\)', body):
            target = m.group(1).lstrip("/")[:-3]
            edges.append({"data": {"source": cid, "target": target}})
    return {"nodes": nodes, "edges": edges}

graph = build_graph_data("./bundles/sales")
print(json.dumps(graph, indent=2))
```

Embed in HTML:
```html
<!DOCTYPE html>
<html>
<head>
  <script src="https://unpkg.com/cytoscape/dist/cytoscape.min.js"></script>
  <style>#cy { width: 100vw; height: 100vh; }</style>
</head>
<body>
  <div id="cy"></div>
  <script>
    const data = /* paste graph JSON here */;
    cytoscape({
      container: document.getElementById('cy'),
      elements: data,
      layout: { name: 'cose', animate: false },
      style: [
        { selector: 'node', style: {
          'label': 'data(label)',
          'background-color': 'mapData(type, "concept", "#4285F4", "entity", "#EA4335", "topic", "#FBBC04", "analysis", "#34A853", "#888")',
        }},
        { selector: 'edge', style: { 'curve-style': 'bezier', 'target-arrow-shape': 'triangle' }},
      ],
    });
  </script>
</body>
</html>
```

### Option B: Quick D3 force-directed (simpler)

```html
<script src="https://d3js.org/d3.v7.min.js"></script>
<svg id="graph" width="1200" height="800"></svg>
<script>
const data = /* graph JSON */;
const svg = d3.select("#graph");
const sim = d3.forceSimulation(data.nodes)
  .force("link", d3.forceLink(data.edges).id(d => d.data.id))
  .force("charge", d3.forceManyBody().strength(-300))
  .force("center", d3.forceCenter(600, 400));

const link = svg.append("g").selectAll("line").data(data.edges).join("line").attr("stroke", "#999");
const node = svg.append("g").selectAll("circle").data(data.nodes).join("circle")
  .attr("r", 8).attr("fill", d => ({concept: "#4285F4", entity: "#EA4335", topic: "#FBBC04"})[d.data.type] || "#888");

sim.on("tick", () => {
  link.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
      .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
  node.attr("cx", d => d.x).attr("cy", d => d.y);
});
</script>
```

### Option C: Use okf_read.py --graph for a text-mode view

```bash
python3 /Users/I321170/.claude/skills/okf-knowledge-format/okf_read.py "$KB" --graph
# Prints: source -> target edges
# Pipe to graphviz for rendering:
python3 ... --graph | awk -F' -> ' 'BEGIN{print "digraph G {"} {print "  \""$1"\" -> \""$2"\""} END{print "}"}' | dot -Tpng > graph.png
```

## Visualizing in Obsidian (zero setup if KB lives in `~/Documents/LLM knowledge base/`)

Just open the KB root as an Obsidian vault. Obsidian's built-in graph view renders the same `[[wikilinks]]` cross-link structure. Use the type field via the **Dataview** plugin:

```dataview
TABLE type, tags
FROM "wiki/concepts"
WHERE type = "concept"
SORT title ASC
```
