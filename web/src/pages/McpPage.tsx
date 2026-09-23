import { Activity, RefreshCw, Wrench } from 'lucide-react';
import { FormEvent, useState } from 'react';

import { EnabledState, FieldHelp, PanelTitle } from '../components/DisplayPrimitives';
import { ApiErrorNotice } from '../components/ApiErrorNotice';
import type { McpRegisteredTool, McpServerConfig, McpStatus, McpToolCallLog } from '../types';

type McpPageProps = {
  projectPath: string;
  status: McpStatus | null;
  servers: McpServerConfig[];
  tools: McpRegisteredTool[];
  logs: McpToolCallLog[];
  onRefresh: (serverId?: string) => Promise<void>;
  onSaveServer: (payload: { server_id: string; name: string; transport: string; command?: string; args: string[]; env: Record<string, string>; url?: string; enabled: boolean }) => Promise<void>;
  onServerEnabled: (serverId: string, enabled: boolean) => Promise<void>;
  onDiscover: (serverId: string) => Promise<void>;
  onToolEnabled: (serverId: string, toolName: string, enabled: boolean) => Promise<void>;
  onApproveTool: (agentCode: string, serverId: string, toolName: string, allowed: boolean, reason: string) => Promise<void>;
  onCallTool: (payload: { server_id?: string; tool_name: string; agent_code: string; arguments: Record<string, unknown> }) => Promise<Record<string, unknown>>;
};

export function McpPage({ projectPath, status, servers, tools, logs, onRefresh, onSaveServer, onServerEnabled, onDiscover, onToolEnabled, onApproveTool, onCallTool }: McpPageProps) {
  const [selectedServerId, setSelectedServerId] = useState('real_filesystem');
  const [selectedToolName, setSelectedToolName] = useState('read_text_file');
  const [serverDraft, setServerDraft] = useState({ server_id: 'real_filesystem', name: 'Real Filesystem MCP', transport: 'stdio', command: '.venv\\Scripts\\python.exe', argsText: JSON.stringify(['scripts/launch_mcp_filesystem.py', projectPath], null, 2), envText: '{}', url: '', enabled: true });
  const [agentCode, setAgentCode] = useState('workflow_runner');
  const [approvalReason, setApprovalReason] = useState('Approved from MCP console.');
  const [callArgsText, setCallArgsText] = useState(defaultMcpCallArguments('read_text_file', 'real_filesystem'));
  const [callResult, setCallResult] = useState<Record<string, unknown> | null>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState<unknown>(null);
  const activeServerId = selectedServerId || servers[0]?.server_id || '';
  const visibleTools = activeServerId ? tools.filter((tool) => tool.server_id === activeServerId) : tools;
  const activeToolName = selectedToolName || visibleTools[0]?.name || '';

  function loadServer(server: McpServerConfig) {
    const defaultTool = defaultMcpToolName(server.server_id);
    setSelectedServerId(server.server_id); setSelectedToolName(defaultTool); setCallArgsText(defaultMcpCallArguments(defaultTool, server.server_id));
    setServerDraft({ server_id: server.server_id, name: server.name, transport: server.transport, command: server.command ?? '', argsText: JSON.stringify(server.args ?? [], null, 2), envText: JSON.stringify(server.env ?? {}, null, 2), url: server.url ?? '', enabled: server.enabled });
    setMessage(`已载入 ${server.server_id}`);
  }
  async function runAction(label: string, action: () => Promise<unknown>) { setMessage(''); setError(null); try { await action(); setMessage(`${label} 已完成。`); } catch (cause) { setError(cause); } }
  async function submitServer(event: FormEvent) {
    event.preventDefault(); setMessage(''); setError(null);
    try {
      await onSaveServer({ server_id: serverDraft.server_id.trim(), name: serverDraft.name.trim(), transport: serverDraft.transport, command: serverDraft.command.trim(), args: parseJsonValue<string[]>(serverDraft.argsText, []), env: parseJsonValue<Record<string, string>>(serverDraft.envText, {}), url: serverDraft.url.trim(), enabled: serverDraft.enabled });
      setSelectedServerId(serverDraft.server_id.trim()); setMessage('MCP Server 已保存。');
    } catch (cause) { setError(cause); }
  }
  async function submitCall(event: FormEvent) { event.preventDefault(); await runAction('工具调用', async () => setCallResult(await onCallTool({ server_id: activeServerId || undefined, tool_name: activeToolName, agent_code: agentCode, arguments: parseJsonValue<Record<string, unknown>>(callArgsText, {}) }))); }

  return <section className="page-grid mcp-page">
    <div className="panel mcp-server-panel"><PanelTitle icon={<Wrench size={17} />} title="MCP Server" action={<button className="icon-button" onClick={() => onRefresh(activeServerId)}><RefreshCw size={15} /></button>} />
      <div className="mcp-status-row"><KpiCard label="provider" value={status?.provider ?? 'local'} /><KpiCard label="servers" value={String(status?.server_count ?? servers.length)} /><KpiCard label="tools" value={String(status?.tool_count ?? tools.length)} /></div>
      <form className="mcp-form" onSubmit={submitServer}><label>server_id<input value={serverDraft.server_id} onChange={(event) => setServerDraft({ ...serverDraft, server_id: event.target.value })} /><FieldHelp>Workflow 节点里的 server_id 要和这里一致。</FieldHelp></label><label>name<input value={serverDraft.name} onChange={(event) => setServerDraft({ ...serverDraft, name: event.target.value })} /></label><label>transport<select value={serverDraft.transport} onChange={(event) => setServerDraft({ ...serverDraft, transport: event.target.value })}><option value="stdio">stdio</option></select><FieldHelp>当前阶段支持 stdio MCP server。</FieldHelp></label><label>command<input value={serverDraft.command} onChange={(event) => setServerDraft({ ...serverDraft, command: event.target.value })} placeholder="npx / python / uvx" /></label><label>args JSON<textarea value={serverDraft.argsText} onChange={(event) => setServerDraft({ ...serverDraft, argsText: event.target.value })} /></label><label>env JSON<textarea value={serverDraft.envText} onChange={(event) => setServerDraft({ ...serverDraft, envText: event.target.value })} /></label><label className="toggle-row"><input type="checkbox" checked={serverDraft.enabled} onChange={(event) => setServerDraft({ ...serverDraft, enabled: event.target.checked })} />保存后启用</label><button className="primary" type="submit">保存 Server</button></form>
      <div className="mcp-server-list">{servers.map((server) => <button key={server.server_id} className={activeServerId === server.server_id ? 'active' : ''} onClick={() => loadServer(server)}><strong>{server.name}</strong><span className="state-with-meta"><span>{server.server_id} / {server.status}</span><EnabledState enabled={server.enabled} label="Server" /></span></button>)}{!servers.length ? <p className="empty-text">暂无 MCP server 配置。</p> : null}</div>
    </div>
    <div className="panel mcp-tool-panel"><PanelTitle icon={<Wrench size={17} />} title="Tool 注册与审批" />
      <div className="mcp-toolbar"><select value={activeServerId} onChange={(event) => { const defaultTool = defaultMcpToolName(event.target.value); setSelectedServerId(event.target.value); setSelectedToolName(defaultTool); setCallArgsText(defaultMcpCallArguments(defaultTool, event.target.value)); }}><option value="">all servers</option>{servers.map((server) => <option key={server.server_id} value={server.server_id}>{server.server_id}</option>)}</select><button className="secondary" disabled={!activeServerId} onClick={() => runAction('Discover', () => onDiscover(activeServerId))}>Discover</button><button className="secondary" disabled={!activeServerId} onClick={() => runAction('启用 Server', () => onServerEnabled(activeServerId, true))}>启用</button><button className="secondary" disabled={!activeServerId} onClick={() => runAction('停用 Server', () => onServerEnabled(activeServerId, false))}>停用</button></div>
      <div className="mcp-tool-list">{visibleTools.map((tool) => { const approvalText = tool.approval_allowed ? '审批已通过' : tool.approval_recorded ? '审批已撤销' : '未审批'; const approvalClass = tool.approval_allowed ? 'approved' : tool.approval_recorded ? 'revoked' : 'pending'; return <article key={tool.tool_id} className={`mcp-tool-card ${activeToolName === tool.name ? 'active' : ''}`}><button onClick={() => { setSelectedServerId(tool.server_id); setSelectedToolName(tool.name); setCallArgsText(defaultMcpCallArguments(tool.name, tool.server_id)); }}><strong>{tool.name}</strong><span className="state-with-meta"><span>{tool.server_id} / {tool.status}</span><EnabledState enabled={tool.enabled} label="Tool" /></span><span className={`mcp-approval-state ${approvalClass}`}>{approvalText}{tool.approval_agent_code ? ` · ${tool.approval_agent_code}` : ''}</span></button><p>{tool.description || 'No description'}</p>{tool.approval_reason ? <p className="mcp-approval-reason">{tool.approval_reason}</p> : null}<div><button className="secondary" onClick={() => runAction('工具启停', () => onToolEnabled(tool.server_id, tool.name, !tool.enabled))}>{tool.enabled ? '停用工具' : '启用工具'}</button><button className="secondary" onClick={() => runAction(tool.approval_allowed ? '重新审批' : '审批通过', () => onApproveTool(agentCode, tool.server_id, tool.name, true, approvalReason))}>{tool.approval_allowed ? '重新审批' : '审批通过'}</button><button className="secondary" disabled={!tool.approval_allowed && tool.approval_recorded} onClick={() => runAction('撤销审批', () => onApproveTool(agentCode, tool.server_id, tool.name, false, approvalReason.toLowerCase().includes('approved') ? 'Revoked from MCP console.' : approvalReason))}>{tool.approval_allowed ? '撤销审批' : '已撤销'}</button></div></article>; })}{!visibleTools.length ? <p className="empty-text">暂无已注册工具。先保存并 Discover MCP server。</p> : null}</div>
    </div>
    <div className="panel mcp-call-panel"><PanelTitle icon={<Activity size={17} />} title="调用与日志" />
      <form className="mcp-form" onSubmit={submitCall}><label>agent_code<input value={agentCode} onChange={(event) => setAgentCode(event.target.value)} /><FieldHelp>审批时使用同一个 agent_code。</FieldHelp></label><label>tool_name<input value={activeToolName} onChange={(event) => setSelectedToolName(event.target.value)} /></label><label>arguments JSON<textarea value={callArgsText} onChange={(event) => setCallArgsText(event.target.value)} /></label><label>approval reason<input value={approvalReason} onChange={(event) => setApprovalReason(event.target.value)} /></label><button className="primary" disabled={!activeToolName} type="submit">测试调用</button></form>
      {message ? <p className="mcp-message">{message}</p> : null}<ApiErrorNotice error={error} />{callResult ? <pre className="mcp-result">{JSON.stringify(callResult, null, 2)}</pre> : null}
      <div className="mcp-log-list">{logs.map((log) => <article key={log.call_id} className={`mcp-log-item ${log.status}`}><div className="mcp-log-head"><strong>{log.tool_name}</strong><span>{log.server_id || 'local'}</span><span className={`mcp-log-status ${log.status}`}>{log.status}</span><span>{log.latency_ms}ms</span></div><p className="mcp-log-brief"><span>输入</span>{summarizeMcpLogInput(log)}</p><p className="mcp-log-brief"><span>{log.status === 'failed' ? '错误' : '结果'}</span>{summarizeMcpLogOutput(log)}</p><details className="mcp-log-details"><summary><span>查看完整 JSON</span></summary><pre>{JSON.stringify(log, null, 2)}</pre></details></article>)}{!logs.length ? <p className="empty-text">暂无 MCP 调用日志。</p> : null}</div>
    </div>
  </section>;
}

function KpiCard({ label, value }: { label: string; value: string }) { return <div className="kpi-card"><span>{label}</span><strong>{value}</strong></div>; }
function parseJsonValue<T>(text: string, fallback: T): T { try { return JSON.parse(text) as T; } catch { return fallback; } }
function defaultMcpToolName(serverId: string) { return serverId === 'real_filesystem' ? 'read_text_file' : ''; }
function defaultMcpCallArguments(toolName: string, serverId: string) { if (serverId === 'real_filesystem' && toolName === 'read_text_file') return JSON.stringify({ path: 'README.md' }, null, 2); return '{}'; }
function summarizeMcpLogInput(log: McpToolCallLog) { return summarizeValue(log.input) || '无参数'; }
function summarizeMcpLogOutput(log: McpToolCallLog) { if (log.error_message) return firstLine(log.error_message); const result = log.output?.result; if (result && typeof result === 'object') { const data = result as Record<string, unknown>; const content = data.content; if (Array.isArray(content)) { const text = content.map((item) => (item && typeof item === 'object' ? String((item as Record<string, unknown>).text ?? '') : '')).filter(Boolean).join('\n'); if (text) return firstLine(text); } if (data.structuredContent) return summarizeValue(data.structuredContent); } return summarizeValue(log.output) || '无输出'; }
function summarizeValue(value: unknown) { const text = JSON.stringify(value); return text.length > 240 ? `${text.slice(0, 237)}...` : text; }
function firstLine(value?: string) { return (value ?? '').split('\n')[0]; }
