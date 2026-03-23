import React, { useState, useRef, useEffect } from 'react'
import { useGraphSync } from '../context/GraphSyncContext'

const SUGGESTIONS = [
  'Top 5 products by billing amount',
  'Which orders have no deliveries?',
  'Trace order 12345 to payment',
  'List all blocked customers',
  'Total billing per currency this year',
]

function MessageBubble({ msg }) {
  const [expanded, setExpanded] = useState(false)
  const isUser = msg.role === 'user'

  return (
    <div style={{
      display: 'flex',
      flexDirection: isUser ? 'row-reverse' : 'row',
      marginBottom: 16,
      gap: 10,
      alignItems: 'flex-start',
    }}>
      {/* Avatar */}
      <div style={{
        width: 32, height: 32, borderRadius: '50%', flexShrink: 0,
        background: isUser ? '#6366f1' : '#1e293b',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 14, color: '#fff',
      }}>
        {isUser ? '👤' : '⬡'}
      </div>

      {/* Content */}
      <div style={{ maxWidth: '78%' }}>
        <div style={{
          background: isUser ? '#6366f1' : '#1e293b',
          borderRadius: isUser ? '18px 18px 4px 18px' : '18px 18px 18px 4px',
          padding: '10px 14px',
          color: '#f1f5f9',
          fontSize: 14,
          lineHeight: 1.55,
          whiteSpace: 'pre-wrap',
        }}>
          {msg.text}
        </div>

        {/* Metadata pill */}
        {msg.metadata && (
          <div style={{ marginTop: 6, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {msg.metadata.intent_type && (
              <span style={pillStyle('#0f172a', '#334155')}>{msg.metadata.intent_type}</span>
            )}
            {msg.metadata.store_used && (
              <span style={pillStyle('#0f172a', '#334155')}>{msg.metadata.store_used}</span>
            )}
            {msg.metadata.row_count != null && (
              <span style={pillStyle('#0f172a', '#334155')}>{msg.metadata.row_count} rows</span>
            )}
            {msg.metadata.query_ms != null && (
              <span style={pillStyle('#0f172a', '#334155')}>{msg.metadata.query_ms}ms</span>
            )}
            {msg.metadata.sync_lag_seconds != null && msg.metadata.sync_lag_seconds > 0 && (
              <span style={pillStyle('#0f172a', '#b45309')}>graph sync lag: {Math.round(msg.metadata.sync_lag_seconds)}s</span>
            )}
          </div>
        )}

        {/* Collapsible data table */}
        {msg.data?.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <button onClick={() => setExpanded(e => !e)} style={toggleBtnStyle}>
              {expanded ? '▲ Hide' : '▼ Show'} {msg.data.length} row{msg.data.length !== 1 ? 's' : ''}
            </button>
            {expanded && (
              <div style={{ overflowX: 'auto', marginTop: 6 }}>
                <table style={tableStyle}>
                  <thead>
                    <tr>
                      {Object.keys(msg.data[0]).map(k => (
                        <th key={k} style={thStyle}>{k}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {msg.data.slice(0, 50).map((row, i) => (
                      <tr key={i}>
                        {Object.values(row).map((v, j) => (
                          <td key={j} style={tdStyle}>{v ?? '—'}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {msg.data.length > 50 && (
                  <p style={{ color: '#6b7280', fontSize: 12, marginTop: 4 }}>
                    Showing first 50 of {msg.data.length} rows
                  </p>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function pillStyle(bg, border) {
  return {
    background: bg, border: `1px solid ${border}`, borderRadius: 9999,
    padding: '2px 8px', fontSize: 11, color: '#94a3b8',
  }
}

const toggleBtnStyle = {
  background: 'none', border: '1px solid #334155', borderRadius: 6,
  color: '#94a3b8', fontSize: 12, cursor: 'pointer', padding: '3px 8px',
}

const tableStyle = { borderCollapse: 'collapse', fontSize: 12, width: '100%' }
const thStyle = { padding: '4px 8px', background: '#1e293b', color: '#94a3b8', borderBottom: '1px solid #334155', textAlign: 'left', whiteSpace: 'nowrap' }
const tdStyle = { padding: '3px 8px', borderBottom: '1px solid #1e293b', color: '#cbd5e1', whiteSpace: 'nowrap' }


export default function ChatSidebar() {
  const [messages, setMessages] = useState([
    { id: 0, role: 'assistant', text: 'Hi! Ask me anything about your O2C data — orders, deliveries, billing, payments, and more.' }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const messagesEndRef = useRef(null)
  const { syncFromResult } = useGraphSync()

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = async (question) => {
    const q = question || input.trim()
    if (!q || loading) return

    setInput('')
    setMessages(prev => [...prev, { id: Date.now(), role: 'user', text: q }])
    setLoading(true)

    try {
      const res = await fetch('/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q }),
      })
      const data = await res.json()

      // Sync graph highlights
      if (data.metadata?.node_ids?.length) {
        syncFromResult(data.metadata.node_ids, data.metadata.edge_sequence)
      }

      setMessages(prev => [...prev, {
        id: Date.now() + 1,
        role: 'assistant',
        text: data.answer || 'No answer returned.',
        data: data.data || [],
        metadata: data.metadata,
      }])
    } catch (err) {
      setMessages(prev => [...prev, {
        id: Date.now() + 1,
        role: 'assistant',
        text: 'Connection error. Make sure the GraphIQ backend is running on port 8000.',
      }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', height: '100%', overflowY: 'scroll',
      background: '#0f172a', borderLeft: '1px solid #1e293b',
    }}>
      {/* Header */}
      <div style={{ padding: '16px 20px', borderBottom: '1px solid #1e293b', display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ fontSize: 20 }}>⬡</span>
        <div>
          <div style={{ color: '#f1f5f9', fontWeight: 700, fontSize: 15 }}>GraphIQ</div>
          <div style={{ color: '#64748b', fontSize: 12 }}>O2C Intelligence</div>
        </div>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'scroll', padding: '16px 12px' }}>
        {messages.map(msg => <MessageBubble key={msg.id} msg={msg} />)}
        {loading && (
          <div style={{ color: '#64748b', fontSize: 13, padding: '8px 12px', textAlign: 'center' }}>
            Thinking…
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggestions */}
      {messages.length <= 1 && !loading && (
        <div style={{ padding: '0 12px 12px', display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {SUGGESTIONS.map(s => (
            <button key={s} onClick={() => sendMessage(s)} style={{
              background: '#1e293b', border: '1px solid #334155', borderRadius: 9999,
              color: '#94a3b8', fontSize: 12, padding: '5px 12px', cursor: 'pointer',
              transition: 'all 0.15s',
            }}>
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <div style={{ padding: '12px', borderTop: '1px solid #1e293b', display: 'flex', gap: 8 }}>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && sendMessage()}
          placeholder="Ask about orders, billing, deliveries…"
          disabled={loading}
          style={{
            flex: 1, background: '#1e293b', border: '1px solid #334155', borderRadius: 10,
            color: '#f1f5f9', padding: '10px 14px', fontSize: 14, outline: 'none',
          }}
        />
        <button onClick={() => sendMessage()} disabled={loading || !input.trim()} style={{
          background: '#6366f1', border: 'none', borderRadius: 10, color: '#fff',
          padding: '10px 18px', fontSize: 15, cursor: 'pointer', opacity: loading ? 0.5 : 1,
        }}>
          ↑
        </button>
      </div>
    </div>
  )
}
