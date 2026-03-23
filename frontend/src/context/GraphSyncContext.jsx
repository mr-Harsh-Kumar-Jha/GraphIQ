import React, { createContext, useContext, useState, useCallback } from 'react'

/**
 * GraphSyncContext — shared state for graph ↔ chat highlight sync.
 *
 * When a query result comes back, the chat panel pushes node_ids and
 * edge_sequence into this context. The GraphCanvas reads them and
 * highlights/animates the relevant nodes and edges.
 */
const GraphSyncContext = createContext(null)

export function GraphSyncProvider({ children }) {
  const [highlightedNodeIds, setHighlightedNodeIds] = useState(new Set())
  const [edgeSequence, setEdgeSequence] = useState([])
  const [selectedNodeId, setSelectedNodeId] = useState(null)

  const syncFromResult = useCallback((nodeIds, edgeSeq) => {
    setHighlightedNodeIds(new Set(nodeIds || []))
    setEdgeSequence(edgeSeq || [])
    setSelectedNodeId(nodeIds?.[0] || null)
  }, [])

  const clearSync = useCallback(() => {
    setHighlightedNodeIds(new Set())
    setEdgeSequence([])
    setSelectedNodeId(null)
  }, [])

  return (
    <GraphSyncContext.Provider
      value={{
        highlightedNodeIds,
        edgeSequence,
        selectedNodeId,
        syncFromResult,
        clearSync,
        setSelectedNodeId,
      }}
    >
      {children}
    </GraphSyncContext.Provider>
  )
}

export function useGraphSync() {
  const ctx = useContext(GraphSyncContext)
  if (!ctx) throw new Error('useGraphSync must be used within GraphSyncProvider')
  return ctx
}
