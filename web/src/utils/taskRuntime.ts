import type { AgentEvent, AgentOutput, ResumeSnapshot, TaskResultPayload, ToolCall, WorkflowNode } from '../types';

export function deriveModules(files: string[]) {
  const modules = new Set<string>();
  for (const file of files) {
    const parts = file.split('/').filter(Boolean);
    if (parts.length > 1) modules.add(parts[0]);
  }
  return [...modules].sort((a, b) => a.localeCompare(b));
}

export function joinProjectPath(root: string, child: string) {
  const normalizedRoot = root.replace(/[\\/]+$/, '');
  return `${normalizedRoot}/${child}`;
}

export function buildFocusedFileWorkflow(filePath: string): WorkflowNode[] {
  return [
    { id: 'plan_focus', type: 'planner', name: 'Focus Planner', x: 64, y: 92, config: {} },
    { id: 'review_focus_file', type: 'agent', name: 'File Review Agent', x: 292, y: 92, config: { agent_type: 'file_reviewer', file_path: filePath, max_chars: 20000 } },
    { id: 'report_focus_file', type: 'reporter', name: 'Reporter', x: 520, y: 92, config: {} },
  ];
}

export function normalizeNodes(nodes: WorkflowNode[]): WorkflowNode[] {
  return (nodes ?? []).map((node, index) => ({ ...node, x: Number.isFinite(node.x) ? node.x : 64 + index * 228, y: Number.isFinite(node.y) ? node.y : 92, config: node.config ?? {} }));
}

export function firstLine(value?: string) { return (value ?? '').split('\n')[0].slice(0, 140); }

export function deriveToolCalls(events: AgentEvent[]): ToolCall[] {
  return events.filter((event) => event.status === 'completed' && event.data?.node_type === 'mcp_tool').map((event) => ({ node_id: String(event.data?.node_id ?? event.node ?? ''), tool_name: String(event.data?.node_name ?? event.agent ?? 'tool'), status: event.status, result: event.data?.output }));
}

export function deriveAgentOutputs(events: AgentEvent[]): AgentOutput[] {
  return events.filter((event) => event.status === 'completed' && event.data?.node_type !== 'mcp_tool').filter((event) => Boolean(event.content)).map((event) => ({ node_id: String(event.data?.node_id ?? event.node ?? ''), node_name: String(event.data?.node_name ?? event.node ?? event.type ?? 'node'), agent: String(event.agent ?? event.data?.node_type ?? 'agent'), content: event.content }));
}

export function formatToolCall(item: ToolCall) {
  const detail = summarizeValue(item.result);
  return `${item.tool_name ?? 'tool'}: ${item.status ?? 'done'}${detail ? ` - ${detail}` : ''}`;
}

export function formatAgentOutput(item: AgentOutput) { return `${item.node_name ?? item.agent ?? 'Agent'}: ${firstLine(item.content)}`; }

export function extractTaskResultArtifact(artifacts: Array<{ artifact_type: string; name: string; content?: unknown }>): Partial<TaskResultPayload> {
  const graphResult = [...artifacts].reverse().find((artifact) => artifact.artifact_type === 'graph_result' && artifact.name === 'result');
  if (graphResult?.content && typeof graphResult.content === 'object') return graphResult.content as Partial<TaskResultPayload>;
  const governance = [...artifacts].reverse().find((artifact) => artifact.artifact_type === 'governance');
  if (governance?.content && typeof governance.content === 'object') {
    const content = governance.content as Partial<TaskResultPayload>;
    return { governance: content.governance, risk_level: content.risk_level ?? content.governance?.risk_level, review_required: content.review_required ?? content.governance?.review_required, next_actions: content.next_actions ?? content.governance?.next_actions, suggestion_records: content.suggestion_records, suggestions: content.suggestions };
  }
  return {};
}

export function extractResumeSnapshots(artifacts: Array<{ artifact_type: string; name: string; content?: unknown }>): ResumeSnapshot[] {
  return artifacts.filter((artifact) => artifact.artifact_type === 'workflow_resume' && artifact.content && typeof artifact.content === 'object').map((artifact) => artifact.content as ResumeSnapshot);
}

export function summarizeValue(value: unknown) {
  if (!value || typeof value !== 'object') return value ? String(value).slice(0, 120) : '';
  const data = value as Record<string, unknown>;
  if (Array.isArray(data.files)) return `${data.files.length} files`;
  if (Array.isArray(data.commits)) return `${data.commits.length} commits`;
  if (Array.isArray(data.results)) return `${data.results.length} results`;
  if (typeof data.content === 'string') return firstLine(data.content);
  if (typeof data.root === 'string') return data.root;
  return JSON.stringify(data).slice(0, 120);
}
