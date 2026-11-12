import { useEffect, useMemo, useState } from "react";
import dagre from "@dagrejs/dagre";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  useNodesState,
} from "@xyflow/react";
import { KeyRound, Link2 } from "lucide-react";

import { foreignKeys, friendlyType } from "../lib/data.js";

const NODE_WIDTH = 270;
const HEADER = 52;
const ROW = 30;

function TableNode({ data }) {
  const { name, rows, columns, fks, dim, active } = data;
  return (
    <div className={`er-node ${dim ? "er-node--dim" : ""} ${active ? "er-node--active" : ""}`}>
      <div className="er-node__head">
        <span className="er-node__name">{name}</span>
        <span className="er-node__rows">{rows.toLocaleString()} rows</span>
      </div>
      <ul>
        {columns.map((c) => {
          const isFk = fks.has(`${name}.${c.name}`);
          return (
            <li key={c.name} className="er-node__col">
              <Handle type="target" position={Position.Left} id={`${c.name}-in`} className="er-handle" />
              <span className="er-node__icon" aria-hidden="true">
                {c.is_key ? <KeyRound size={12} className="ico-key" /> : isFk ? <Link2 size={12} className="ico-link" /> : null}
              </span>
              <span className="er-node__colname">{c.name}</span>
              <span className="er-node__type">{friendlyType(c.type)}</span>
              <Handle type="source" position={Position.Right} id={`${c.name}-out`} className="er-handle" />
            </li>
          );
        })}
      </ul>
    </div>
  );
}

const nodeTypes = { table: TableNode };

function layout(schema) {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "LR", nodesep: 40, ranksep: 120 });
  g.setDefaultEdgeLabel(() => ({}));

  Object.entries(schema.tables).forEach(([t, info]) => {
    g.setNode(t, { width: NODE_WIDTH, height: HEADER + ROW * info.columns.length });
  });
  schema.relationships.forEach((r) => g.setEdge(r.from_table, r.to_table));
  dagre.layout(g);

  const positions = {};
  g.nodes().forEach((t) => {
    const n = g.node(t);
    positions[t] = { x: n.x - n.width / 2, y: n.y - n.height / 2 };
  });
  return positions;
}

export default function ErMap({ schema }) {
  const [selected, setSelected] = useState(null);
  const positions = useMemo(() => (schema ? layout(schema) : {}), [schema]);
  const fks = useMemo(() => foreignKeys(schema), [schema]);

  // Tables linked to the selected one stay bright; the rest fade back.
  const linked = useMemo(() => {
    if (!selected || !schema) return null;
    const s = new Set([selected]);
    schema.relationships.forEach((r) => {
      if (r.from_table === selected) s.add(r.to_table);
      if (r.to_table === selected) s.add(r.from_table);
    });
    return s;
  }, [selected, schema]);

  // React Flow owns the nodes so dragging works; we rebuild them when the schema changes
  const [nodes, setNodes, onNodesChange] = useNodesState([]);

  useEffect(() => {
    if (!schema) return;
    setNodes(
      Object.entries(schema.tables).map(([t, info]) => ({
        id: t,
        type: "table",
        position: positions[t] || { x: 0, y: 0 },
        data: { name: t, rows: info.rows, columns: info.columns, fks, dim: false, active: false },
      }))
    );
  }, [schema, positions, fks, setNodes]);

  // Highlighting only changes each node's data, so dragged positions are kept
  useEffect(() => {
    setNodes((current) =>
      current.map((n) => ({
        ...n,
        data: { ...n.data, dim: linked ? !linked.has(n.id) : false, active: selected === n.id },
      }))
    );
  }, [linked, selected, setNodes]);

  const edges = useMemo(() => {
    if (!schema) return [];
    return schema.relationships.map((r, i) => {
      const touches = selected && (r.from_table === selected || r.to_table === selected);
      const faded = selected && !touches;
      return {
        id: `e${i}`,
        source: r.from_table,
        sourceHandle: `${r.from_column}-out`,
        target: r.to_table,
        targetHandle: `${r.to_column}-in`,
        type: "smoothstep",
        animated: Boolean(touches),
        label: r.from_column === r.to_column ? r.from_column : `${r.from_column} = ${r.to_column}`,
        labelBgPadding: [6, 3],
        labelBgBorderRadius: 6,
        labelStyle: { fontSize: 12, fill: "#1F2140" },
        style: { stroke: faded ? "#C9CCE0" : "#6C4CF5", strokeWidth: touches ? 2.5 : 1.75 },
        markerEnd: { type: MarkerType.ArrowClosed, color: faded ? "#C9CCE0" : "#6C4CF5" },
      };
    });
  }, [schema, selected]);

  if (!schema) return <div className="panel-empty">Loading your data map…</div>;

  const count = schema.relationships.length;

  return (
    <div className="map">
      <div className="map__note">
        <p>
          {count
            ? `Found ${count} ${count === 1 ? "link" : "links"} between your tables. Click a table to highlight its links. Drag to rearrange.`
            : "No links found between your tables yet. Links appear when two tables share a matching ID column."}
        </p>
        <p className="legend">
          <KeyRound size={13} className="ico-key" aria-hidden="true" /> unique key
          <Link2 size={13} className="ico-link" aria-hidden="true" /> points to another table
        </p>
      </div>
      <div className="map__canvas">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.3}
          onNodeClick={(_, node) => setSelected((cur) => (cur === node.id ? null : node.id))}
          onPaneClick={() => setSelected(null)}
          nodesConnectable={false}
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={24} color="#DADDF0" />
          <Controls showInteractive={false} />
          <MiniMap pannable zoomable nodeColor="#6C4CF5" maskColor="rgba(247,248,252,0.7)" />
        </ReactFlow>
      </div>
    </div>
  );
}
