import React, { useState } from 'react'
import { useGraphSync } from '../context/GraphSyncContext'

export default function NodeCard({ node, onExpand, onExpandError }) {
  const { setSelectedNodeId } = useGraphSync()
  const [loading, setLoading] = useState(false)

  if (!node) return null

  const handleExpand = async () => {
    setLoading(true)
    try {
      const res = await fetch(`/graph/neighbors/${encodeURIComponent(node.id)}`)
      const data = await res.json()
      onExpand(data.edges || [])
    } catch (err) {
      if (onExpandError) onExpandError(err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      position: 'absolute', top: 16, left: 16, width: 320,
      background: '#0f172a', border: '1px solid #1e293b',
      borderRadius: 12, padding: 16, color: '#f1f5f9',
      boxShadow: '0 10px 15px -3px rgba(0,0,0,0.5)', zIndex: 10
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
        <div style={{ overflow: 'hidden' }}>
          <div style={{ fontSize: 13, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: 1 }}>{node.label}</div>
          <div style={{ fontSize: 18, fontWeight: 600, marginTop: 4, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{node.id}</div>
        </div>
        <button onClick={() => setSelectedNodeId(null)} style={{
          background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', fontSize: 16
        }}>✕</button>
      </div>

      <div style={{ background: '#1e293b', borderRadius: 8, padding: 12, marginBottom: 16, maxHeight: 240, overflowY: 'auto' }}>
        {Object.entries(node).map(([k, v]) => {
          if (k === 'id' || k === 'label') return null
          return (
            <div key={k} style={{ display: 'flex', borderBottom: '1px solid #334155', padding: '6px 0', fontSize: 13 }}>
              <span style={{ color: '#94a3b8', width: '40%' }}>{k.replace(/_/g, ' ')}</span>
              <span style={{ color: '#cbd5e1', width: '60%', wordBreak: 'break-all' }}>{String(v)}</span>
            </div>
          )
        })}
      </div>

      <button onClick={handleExpand} disabled={loading} style={{
        width: '100%', background: '#6366f1', color: '#fff', border: 'none',
        borderRadius: 8, padding: '10px 0', fontWeight: 600, cursor: 'pointer',
        opacity: loading ? 0.7 : 1
      }}>
        {loading ? 'Expanding...' : 'Expand Neighbors'}
      </button>
    </div>
  )
}
