import { FileText, ShieldCheck, Workflow } from 'lucide-react';
import { useState } from 'react';
import { PanelTitle } from '../components/DisplayPrimitives';
import type { SuggestionRecord, WorkflowEdge, WorkflowNode } from '../types';

type Tab = 'final' | 'mentor' | 'mermaid' | 'governance';
type Props = { finalReport: string; mermaid: string; nodes: WorkflowNode[]; edges: WorkflowEdge[]; riskLevel: string; reviewRequired: boolean; nextActions: string[]; suggestions: string[]; suggestionRecords: SuggestionRecord[]; knowledgeDocumentCount: number; onOpenKnowledge: () => void; };
export function ReportsPage({ finalReport, mermaid, nodes, edges, riskLevel, reviewRequired, nextActions, suggestions, suggestionRecords, knowledgeDocumentCount, onOpenKnowledge }: Props) {
  const [tab, setTab] = useState<Tab>('final'); const source = mermaid || localMermaid(nodes, edges); const fallback = ['保存高频 Workflow 为模板', '给关键节点增加人工审核', '后续接入真实 MCP client 与向量数据库'];
  return <section className="reports-page">
    <div className="panel report-card markdown-card report-tab-card"><PanelTitle icon={<FileText size={17} />} title="报告中心" /><div className="report-tabs">{(['final', 'mentor', 'mermaid', 'governance'] as Tab[]).map((item) => <button key={item} className={tab === item ? 'active' : ''} onClick={() => setTab(item)}>{{ final: '最终报告', mentor: '架构导师视角', mermaid: 'Mermaid 图', governance: '治理建议' }[item]}</button>)}</div>{tab === 'final' ? <Markdown text={finalReport || '运行任务后，这里会显示格式化后的最终报告。'} /> : null}{tab === 'mentor' ? <Markdown text={mentor(finalReport)} /> : null}{tab === 'mermaid' ? <Mermaid source={source} /> : null}{tab === 'governance' ? <Governance riskLevel={riskLevel} reviewRequired={reviewRequired} nextActions={nextActions} suggestions={suggestions} records={suggestionRecords} /> : null}</div>
    <div className="panel report-card markdown-card"><PanelTitle icon={<FileText size={17} />} title="最终报告" /><Markdown text={finalReport || '运行当前画布后，这里会显示格式化后的最终报告。'} /></div>
    <div className="panel report-card mermaid-card"><PanelTitle icon={<Workflow size={17} />} title="Mermaid 图" /><Mermaid source={source} /></div>
    <div className="panel report-card suggestions-card"><PanelTitle icon={<ShieldCheck size={17} />} title="优化建议" /><ul className="suggestion-list">{(suggestions.length ? suggestions : fallback).map((item) => <li key={item}>{item}</li>)}</ul><div className="knowledge-summary"><strong>project-memory</strong><p>{knowledgeDocumentCount} documents saved</p><button className="secondary" onClick={onOpenKnowledge}>打开追问知识库</button></div></div>
  </section>;
}
function Markdown({ text }: { text: string }) { return <div className="markdown-view"><pre>{text}</pre></div>; }
function Mermaid({ source }: { source: string }) { return <div className="mermaid-visual"><pre>{source}</pre></div>; }
function Governance({ riskLevel, reviewRequired, nextActions, suggestions, records }: { riskLevel: string; reviewRequired: boolean; nextActions: string[]; suggestions: string[]; records: SuggestionRecord[] }) { const items = nextActions.length ? nextActions : suggestions; return <div className="governance-view"><div className="governance-summary-row"><span className={`risk-badge ${riskLevel}`}>risk_level: {riskLevel}</span><span className={`review-badge ${reviewRequired ? 'required' : ''}`}>review_required: {String(reviewRequired)}</span></div><ul className="suggestion-list">{items.map((item) => <li key={item}>{item}</li>)}</ul><div className="finding-suggestion-list">{records.map((record) => <article key={record.id ?? record.action} className="finding-suggestion-card"><strong>{record.risk_level ?? 'low'}</strong><p>{record.action}</p><small>{record.test_case}</small></article>)}</div></div>; }
function mentor(report: string) { const index = report.indexOf('LLM 架构理解'); return index >= 0 ? report.slice(index) : '# 架构导师视角\n\n当前报告里还没有单独的架构导师段落。'; }
function localMermaid(nodes: WorkflowNode[], edges: WorkflowEdge[]) { return ['graph LR', ...nodes.map((node) => `${node.id}[${node.name}]`), ...edges.map((edge) => `${edge.source} --> ${edge.target}`)].join('\n'); }
