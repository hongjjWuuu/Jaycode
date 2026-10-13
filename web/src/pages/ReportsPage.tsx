import { FileText, ShieldCheck, Workflow } from 'lucide-react';
import { useId, useMemo, useState } from 'react';
import { PanelTitle } from '../components/DisplayPrimitives';
import { ApiErrorNotice } from '../components/ApiErrorNotice';
import type { SuggestionRecord, WorkflowEdge, WorkflowNode } from '../types';

type Tab = 'final' | 'mentor' | 'mermaid' | 'governance';
type Props = { finalReport: string; mermaid: string; nodes: WorkflowNode[]; edges: WorkflowEdge[]; riskLevel: string; reviewRequired: boolean; nextActions: string[]; suggestions: string[]; suggestionRecords: SuggestionRecord[]; knowledgeDocumentCount: number; onOpenKnowledge: () => void | Promise<void>; };
type GraphNode = { id: string; label: string };
type GraphEdge = { source: string; target: string; label?: string };
type MermaidGraph = { direction: 'LR' | 'RL' | 'TB' | 'TD' | 'BT'; nodes: GraphNode[]; edges: GraphEdge[]; error?: string };

export function ReportsPage({ finalReport, mermaid, nodes, edges, riskLevel, reviewRequired, nextActions, suggestions, suggestionRecords, knowledgeDocumentCount, onOpenKnowledge }: Props) {
  const [tab, setTab] = useState<Tab>('final'); const source = mermaid || localMermaid(nodes, edges); const fallback = ['保存高频 Workflow 为模板', '给关键节点增加人工审核', '后续接入真实 MCP client 与向量数据库'];
  const [error, setError] = useState<unknown>(null);
  function openKnowledge() { setError(null); try { Promise.resolve(onOpenKnowledge()).catch(setError); } catch (cause) { setError(cause); } }
  return <section className="reports-page">
    <div className="panel report-card markdown-card report-tab-card"><PanelTitle icon={<FileText size={17} />} title="报告中心" /><div className="report-tabs">{(['final', 'mentor', 'mermaid', 'governance'] as Tab[]).map((item) => <button key={item} className={tab === item ? 'active' : ''} onClick={() => setTab(item)}>{{ final: '最终报告', mentor: '架构导师视角', mermaid: 'Mermaid 图', governance: '治理建议' }[item]}</button>)}</div>{tab === 'final' ? <Markdown text={finalReport || '运行任务后，这里会显示格式化后的最终报告。'} /> : null}{tab === 'mentor' ? <Markdown text={mentor(finalReport)} /> : null}{tab === 'mermaid' ? <Mermaid source={source} /> : null}{tab === 'governance' ? <Governance riskLevel={riskLevel} reviewRequired={reviewRequired} nextActions={nextActions} suggestions={suggestions} records={suggestionRecords} /> : null}</div>
    <div className="panel report-card markdown-card"><PanelTitle icon={<FileText size={17} />} title="最终报告" /><Markdown text={finalReport || '运行当前画布后，这里会显示格式化后的最终报告。'} /></div>
    <div className="panel report-card mermaid-card"><PanelTitle icon={<Workflow size={17} />} title="Mermaid 图" /><Mermaid source={source} /></div>
    <div className="panel report-card suggestions-card"><PanelTitle icon={<ShieldCheck size={17} />} title="优化建议" /><ApiErrorNotice error={error} /><ul className="suggestion-list">{(suggestions.length ? suggestions : fallback).map((item) => <li key={item}>{item}</li>)}</ul><div className="knowledge-summary"><strong>project-memory</strong><p>{knowledgeDocumentCount} documents saved</p><button className="secondary" onClick={openKnowledge}>打开追问知识库</button></div></div>
  </section>;
}

function Markdown({ text }: { text: string }) { return <div className="markdown-view"><pre>{text}</pre></div>; }

function Mermaid({ source }: { source: string }) {
  const graph = useMemo(() => parseMermaid(source), [source]);
  const markerId = useId().replace(/:/g, '');
  if (!source.trim()) return <div className="mermaid-visual mermaid-empty"><p>运行任务后将在这里生成流程图。</p></div>;
  if (graph.error) return <div className="mermaid-visual mermaid-error" role="alert"><strong>流程图无法渲染</strong><p>{graph.error}</p><details><summary>查看 Mermaid 源码</summary><pre>{source}</pre></details></div>;
  const horizontal = graph.direction === 'LR' || graph.direction === 'RL';
  const stepX = 206; const stepY = 118; const nodeWidth = 166; const nodeHeight = 66;
  const ordered = graph.direction === 'RL' || graph.direction === 'BT' ? [...graph.nodes].reverse() : graph.nodes;
  const locations = new Map(ordered.map((node, index) => [node.id, {
    x: horizontal ? 34 + index * stepX : 38,
    y: horizontal ? 44 : 32 + index * stepY,
  }]));
  const width = horizontal ? Math.max(360, 68 + ordered.length * stepX) : 330;
  const height = horizontal ? 156 : Math.max(150, 64 + ordered.length * stepY);
  return <div className="mermaid-visual"><svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Workflow Mermaid 流程图"><defs><marker id={markerId} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#52748a" /></marker></defs>{graph.edges.map((edge, index) => {
    const start = locations.get(edge.source); const end = locations.get(edge.target); if (!start || !end) return null;
    const sameRow = horizontal;
    const x1 = sameRow ? start.x + nodeWidth : start.x + nodeWidth / 2; const y1 = sameRow ? start.y + nodeHeight / 2 : start.y + nodeHeight;
    const x2 = sameRow ? end.x : end.x + nodeWidth / 2; const y2 = sameRow ? end.y + nodeHeight / 2 : end.y;
    const middle = sameRow ? (x1 + x2) / 2 : (y1 + y2) / 2;
    const path = sameRow ? `M ${x1} ${y1} C ${middle} ${y1}, ${middle} ${y2}, ${x2} ${y2}` : `M ${x1} ${y1} C ${x1} ${middle}, ${x2} ${middle}, ${x2} ${y2}`;
    return <g key={`${edge.source}-${edge.target}-${index}`}><path className="mermaid-edge" d={path} markerEnd={`url(#${markerId})`} />{edge.label ? <text className="mermaid-edge-label" x={sameRow ? middle : x1 + 8} y={sameRow ? y1 - 9 : middle} textAnchor={sameRow ? 'middle' : 'start'}>{edge.label}</text> : null}</g>;
  })}{ordered.map((node) => {
    const point = locations.get(node.id)!; const lines = wrapLabel(node.label);
    return <g key={node.id} className="mermaid-node-group"><rect className="mermaid-node" x={point.x} y={point.y} width={nodeWidth} height={nodeHeight} rx="10" /><text x={point.x + nodeWidth / 2} y={point.y + 29} textAnchor="middle">{lines.map((line, index) => <tspan key={`${node.id}-${index}`} x={point.x + nodeWidth / 2} dy={index ? 16 : 0}>{line}</tspan>)}</text></g>;
  })}</svg><details className="mermaid-source"><summary>查看 Mermaid 源码</summary><pre>{source}</pre></details></div>;
}

function Governance({ riskLevel, reviewRequired, nextActions, suggestions, records }: { riskLevel: string; reviewRequired: boolean; nextActions: string[]; suggestions: string[]; records: SuggestionRecord[] }) { const items = nextActions.length ? nextActions : suggestions; return <div className="governance-view"><div className="governance-summary-row"><span className={`risk-badge ${riskLevel}`}>risk_level: {riskLevel}</span><span className={`review-badge ${reviewRequired ? 'required' : ''}`}>review_required: {String(reviewRequired)}</span></div><ul className="suggestion-list">{items.map((item) => <li key={item}>{item}</li>)}</ul><div className="finding-suggestion-list">{records.map((record) => <article key={record.id ?? record.action} className="finding-suggestion-card"><strong>{record.risk_level ?? 'low'}</strong><p>{record.action}</p><small>{record.test_case}</small></article>)}</div></div>; }

function parseMermaid(source: string): MermaidGraph {
  // Older report payloads can contain escaped line breaks; normalize them before parsing.
  const lines = source.replace(/\\n/g, '\n').split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const header = lines.shift()?.match(/^(?:flowchart|graph)\s+(LR|RL|TB|TD|BT)$/i);
  if (!header) return { direction: 'LR', nodes: [], edges: [], error: '仅支持以 “flowchart LR/TD” 或 “graph LR/TD” 开头的流程图。' };
  const nodes = new Map<string, GraphNode>(); const edges: GraphEdge[] = [];
  for (const line of lines) {
    const declaration = line.match(/^([\w-]+)\s*(?:\[([^\]]+)\]|\(([^)]+)\)|\{([^}]+)\})\s*$/);
    if (declaration) { const [, id, square, round, diamond] = declaration; nodes.set(id, { id, label: (square ?? round ?? diamond ?? id).trim() }); continue; }
    const edge = line.match(/^([\w-]+)\s*--(?:\s*\|?([^>|]+?)\|?\s*)?>\s*([\w-]+)\s*$/);
    if (edge) { const [, sourceId, label, targetId] = edge; if (!nodes.has(sourceId)) nodes.set(sourceId, { id: sourceId, label: sourceId }); if (!nodes.has(targetId)) nodes.set(targetId, { id: targetId, label: targetId }); edges.push({ source: sourceId, target: targetId, label: label?.trim() || undefined }); continue; }
    return { direction: 'LR', nodes: [], edges: [], error: `第 ${lines.indexOf(line) + 2} 行不是可识别的 Mermaid 流程图语法。` };
  }
  if (!nodes.size) return { direction: 'LR', nodes: [], edges: [], error: '流程图中没有可渲染的节点。' };
  return { direction: header[1].toUpperCase() as MermaidGraph['direction'], nodes: [...nodes.values()], edges };
}

function wrapLabel(label: string) { return label.length <= 18 ? [label] : [label.slice(0, 18), label.slice(18, 36) + (label.length > 36 ? '…' : '')]; }
function mentor(report: string) { const index = report.indexOf('LLM 架构理解'); return index >= 0 ? report.slice(index) : '# 架构导师视角\n\n当前报告里还没有单独的架构导师段落。'; }
function localMermaid(nodes: WorkflowNode[], edges: WorkflowEdge[]) { return nodes.length ? ['flowchart LR', ...nodes.map((node) => `${node.id}[${node.name}]`), ...edges.map((edge) => `${edge.source} --> ${edge.target}`)].join('\n') : ''; }
