import React, { useEffect, useRef, useCallback } from 'react'
import * as d3 from 'd3'
import { useGraphSync } from '../context/GraphSyncContext'

/** Color palette by node label */
const LABEL_COLORS = {
  Customer:     '#6366f1',  // violet
  SalesOrder:   '#22d3ee',  // cyan
  Delivery:     '#34d399',  // emerald
  Invoice:      '#f59e0b',  // amber
  JournalEntry: '#f97316',  // orange
  Payment:      '#10b981',  // green
  Product:      '#a78bfa',  // purple
  Plant:        '#64748b',  // slate
}

const NODE_RADIUS = 14
const HIGHLIGHT_RADIUS = 20

export default function GraphCanvas({ nodes, edges }) {
  const svgRef = useRef(null)
  const simRef = useRef(null)
  const { highlightedNodeIds, edgeSequence, setSelectedNodeId } = useGraphSync()

  // ── Build graph when data changes ─────────────────────────────────────────
  useEffect(() => {
    if (!nodes?.length || !svgRef.current) return

    const width = svgRef.current.clientWidth || 900
    const height = svgRef.current.clientHeight || 600

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    // Defs: arrowhead
    const defs = svg.append('defs')
    defs.append('marker')
      .attr('id', 'arrow')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 22).attr('refY', 0)
      .attr('markerWidth', 6).attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-5L10,0L0,5')
      .attr('fill', '#4b5563')

    const g = svg.append('g')

    // Zoom
    svg.call(d3.zoom().scaleExtent([0.1, 4]).on('zoom', e => g.attr('transform', e.transform)))

    // Simulation
    const simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(edges).id(d => d.id).distance(100))
      .force('charge', d3.forceManyBody().strength(-250))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide(30))
    simRef.current = simulation

    // Edges
    const link = g.append('g').selectAll('line').data(edges)
      .join('line')
      .attr('stroke', '#2d3748')
      .attr('stroke-width', 1.5)
      .attr('marker-end', 'url(#arrow)')

    // Edge labels
    const linkLabel = g.append('g').selectAll('text').data(edges)
      .join('text')
      .attr('fill', '#6b7280')
      .attr('font-size', 9)
      .attr('text-anchor', 'middle')
      .text(d => d.rel_type || '')

    // Nodes
    const node = g.append('g').selectAll('g').data(nodes)
      .join('g')
      .attr('class', 'graph-node')
      .style('cursor', 'pointer')
      .on('click', (_, d) => setSelectedNodeId(d.id))
      .call(
        d3.drag()
          .on('start', (e, d) => { if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y })
          .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y })
          .on('end', (e, d) => { if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null })
      )

    node.append('circle')
      .attr('r', d => highlightedNodeIds.has(d.id) ? HIGHLIGHT_RADIUS : NODE_RADIUS)
      .attr('fill', d => LABEL_COLORS[d.label] || '#6b7280')
      .attr('stroke', d => highlightedNodeIds.has(d.id) ? '#fff' : 'transparent')
      .attr('stroke-width', 2)
      .attr('opacity', d => (highlightedNodeIds.size === 0 || highlightedNodeIds.has(d.id)) ? 1 : 0.25)

    node.append('text')
      .attr('dy', 4)
      .attr('text-anchor', 'middle')
      .attr('fill', '#fff')
      .attr('font-size', 9)
      .attr('pointer-events', 'none')
      .text(d => (d.id || '').slice(-6))

    // Tooltip
    node.append('title').text(d => `${d.label}: ${d.id}`)

    simulation.on('tick', () => {
      link
        .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x).attr('y2', d => d.target.y)
      linkLabel
        .attr('x', d => (d.source.x + d.target.x) / 2)
        .attr('y', d => (d.source.y + d.target.y) / 2)
      node.attr('transform', d => `translate(${d.x},${d.y})`)
    })

    return () => simulation.stop()
  }, [nodes, edges])

  // ── Re-highlight on sync changes without full rebuild ─────────────────────
  useEffect(() => {
    if (!svgRef.current) return
    d3.select(svgRef.current).selectAll('.graph-node circle')
      .attr('r', d => highlightedNodeIds.has(d.id) ? HIGHLIGHT_RADIUS : NODE_RADIUS)
      .attr('stroke', d => highlightedNodeIds.has(d.id) ? '#fff' : 'transparent')
      .attr('opacity', d => (highlightedNodeIds.size === 0 || highlightedNodeIds.has(d.id)) ? 1 : 0.25)
  }, [highlightedNodeIds])

  return (
    <svg
      ref={svgRef}
      style={{ width: '100%', height: '100%', background: '#111827', borderRadius: 12 }}
    />
  )
}
