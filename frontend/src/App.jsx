import React, { useState, useEffect } from 'react'
import GraphCanvas from './components/GraphCanvas'
import ChatSidebar from './components/ChatSidebar'
import NodeCard from './components/NodeCard'
import { GraphSyncProvider, useGraphSync } from './context/GraphSyncContext'

function LegendItem({ label, color }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{ width: 10, height: 10, borderRadius: '50%', background: color }} />
      <span style={{ color: '#94a3b8', fontSize: 12 }}>{label}</span>
    </div>
  )
}

const LABEL_COLORS = {
  Customer: '#6366f1', SalesOrder: '#22d3ee', Delivery: '#34d399',
  Invoice: '#f59e0b', JournalEntry: '#f97316', Payment: '#10b981',
  Product: '#a78bfa', Plant: '#64748b',
}

function GraphArea({ graphData, setGraphData, loadingGraph }) {
  const { selectedNodeId } = useGraphSync()
  const node = selectedNodeId ? graphData.nodes.find(n => n.id === selectedNodeId) : null

  const handleExpand = (rawEdges) => {
    const newNodes = new Map(graphData.nodes.map(n => [n.id, n]))
    const newEdges = [...graphData.edges]

    rawEdges.forEach(e => {
       const sourceId = e.from_props.id
       const targetId = e.to_props.id
       
       if (!newNodes.has(sourceId)) {
          newNodes.set(sourceId, { id: sourceId, label: e.from_label, ...e.from_props })
       }
       if (!newNodes.has(targetId)) {
          newNodes.set(targetId, { id: targetId, label: e.to_label, ...e.to_props })
       }

       // check if edge already exists
       const edgeExists = newEdges.some(ex => 
          (ex.source.id === sourceId && ex.target.id === targetId) || 
          (ex.source === sourceId && ex.target === targetId)
       )
       if (!edgeExists) {
          newEdges.push({ source: sourceId, target: targetId, rel_type: e.rel_type })
       }
    })

    setGraphData({ nodes: Array.from(newNodes.values()), edges: newEdges })
  }

  return (
    <div style={{ position: 'relative', overflow: 'hidden', padding: 16, height: '100%' }}>
      {loadingGraph ? (
        <div style={{
          position: 'absolute', inset: 0, display: 'flex',
          alignItems: 'center', justifyContent: 'center',
          color: '#64748b', fontSize: 14,
        }}>
          Loading graph…
        </div>
      ) : graphData.nodes.length === 0 ? (
        <div style={{
          position: 'absolute', inset: 0, display: 'flex',
          flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          color: '#334155', gap: 12,
        }}>
          <span style={{ fontSize: 48 }}>⬡</span>
          <span style={{ fontSize: 14 }}>No graph data yet</span>
          <span style={{ fontSize: 12, color: '#1e293b' }}>
            Run scripts/neo4j_bootstrap.py to populate the graph
          </span>
        </div>
      ) : (
        <>
          <GraphCanvas nodes={graphData.nodes} edges={graphData.edges} />
          {node && <NodeCard node={node} onExpand={handleExpand} />}
        </>
      )}
    </div>
  )
}

export default function App() {
  const [graphData, setGraphData] = useState({ nodes: [], edges: [] })
  const [loadingGraph, setLoadingGraph] = useState(true)
  const [health, setHealth] = useState(null)

  useEffect(() => {
    // Load initial graph nodes
    fetch('/graph/nodes')
      .then(r => r.json())
      .then(data => {
        setGraphData({ nodes: data.nodes || [], edges: data.edges || [] })
        setLoadingGraph(false)
      })
      .catch(() => setLoadingGraph(false))

    // Health check
    fetch('/health')
      .then(r => r.json())
      .then(setHealth)
      .catch(() => {})
  }, [])

  return (
    <GraphSyncProvider>
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 380px',
        gridTemplateRows: '48px 1fr',
        height: '100vh',
        background: '#0a0f1e',
        fontFamily: "'Inter', 'Segoe UI', system-ui, sans-serif",
      }}>
        {/* ── Top bar ─────────────────────────────────────────────────────── */}
        <div style={{
          gridColumn: '1 / -1',
          background: '#0f172a',
          borderBottom: '1px solid #1e293b',
          display: 'flex',
          alignItems: 'center',
          padding: '0 20px',
          gap: 16,
        }}>
          <span style={{ fontSize: 22, lineHeight: 1 }}>⬡</span>
          <span style={{ color: '#f1f5f9', fontWeight: 800, fontSize: 16, letterSpacing: '-0.02em' }}>
            GraphIQ
          </span>
          <span style={{ color: '#334155', fontSize: 14 }}>|</span>
          <span style={{ color: '#64748b', fontSize: 13 }}>O2C Intelligence</span>

          <div style={{ flex: 1 }} />

          {/* Legend */}
          {Object.entries(LABEL_COLORS).map(([l, c]) => (
            <LegendItem key={l} label={l} color={c} />
          ))}

          {/* Health indicators */}
          {health && (
            <>
              <div style={{ color: health.postgres ? '#10b981' : '#ef4444', fontSize: 12 }}>
                {health.postgres ? '✓' : '✗'} PG
              </div>
              <div style={{ color: health.neo4j ? '#10b981' : '#ef4444', fontSize: 12 }}>
                {health.neo4j ? '✓' : '✗'} Neo4j
              </div>
            </>
          )}
        </div>

        {/* ── Graph canvas ─────────────────────────────────────────────────── */}
        <GraphArea graphData={graphData} setGraphData={setGraphData} loadingGraph={loadingGraph} />

        {/* ── Chat sidebar ─────────────────────────────────────────────────── */}
        <ChatSidebar />
      </div>
    </GraphSyncProvider>
  )
}
