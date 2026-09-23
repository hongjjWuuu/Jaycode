import type {
  McpRegisteredTool,
  McpServerConfig,
  McpStatus,
  McpToolCallLog,
} from '../types';
import { requestJson } from './http';

const API_BASE = '';

function jsonRequest(body: unknown): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  };
}

export async function listProjectFiles(
  rootPath: string,
  maxFiles = 800,
): Promise<{ root: string; files: string[] }> {
  const data = await requestJson<{ root?: string; files?: string[] }>(
    `${API_BASE}/api/v1/mcp/filesystem/list`,
    jsonRequest({ root_path: rootPath, max_files: maxFiles }),
    'File list failed',
  );
  return { root: data.root ?? rootPath, files: data.files ?? [] };
}

export function getMcpStatus(): Promise<McpStatus> {
  return requestJson(`${API_BASE}/api/v1/mcp/status`, {}, 'MCP status failed');
}

export async function listMcpServers(): Promise<McpServerConfig[]> {
  const data = await requestJson<{ servers?: McpServerConfig[] }>(
    `${API_BASE}/api/v1/mcp/servers`,
    {},
    'MCP servers failed',
  );
  return data.servers ?? [];
}

export async function saveMcpServer(payload: {
  server_id: string;
  name: string;
  transport: string;
  command?: string;
  args: string[];
  env: Record<string, string>;
  url?: string;
  enabled: boolean;
}): Promise<McpServerConfig> {
  const data = await requestJson<{ server: McpServerConfig }>(
    `${API_BASE}/api/v1/mcp/servers`,
    jsonRequest(payload),
    'Save MCP server failed',
  );
  return data.server;
}

export async function setMcpServerEnabled(
  serverId: string,
  enabled: boolean,
): Promise<McpServerConfig> {
  const data = await requestJson<{ server: McpServerConfig }>(
    `${API_BASE}/api/v1/mcp/servers/${encodeURIComponent(serverId)}/enabled`,
    jsonRequest({ enabled }),
    'Toggle MCP server failed',
  );
  return data.server;
}

export function discoverMcpServer(serverId: string): Promise<{
  server_id: string;
  status: string;
  tools: McpRegisteredTool[];
  latency_ms: number;
}> {
  return requestJson(
    `${API_BASE}/api/v1/mcp/servers/${encodeURIComponent(serverId)}/discover`,
    { method: 'POST' },
    'Discover MCP tools failed',
  );
}

export async function listMcpRegisteredTools(
  serverId = '',
  agentCode = 'workflow_runner',
): Promise<McpRegisteredTool[]> {
  const params = new URLSearchParams();
  if (serverId) params.set('server_id', serverId);
  if (agentCode) params.set('agent_code', agentCode);
  const data = await requestJson<{ tools?: McpRegisteredTool[] }>(
    `${API_BASE}/api/v1/mcp/registered-tools?${params.toString()}`,
    {},
    'MCP tools failed',
  );
  return data.tools ?? [];
}

export async function setMcpRegisteredToolEnabled(
  serverId: string,
  toolName: string,
  enabled: boolean,
): Promise<McpRegisteredTool> {
  const data = await requestJson<{ tool: McpRegisteredTool }>(
    `${API_BASE}/api/v1/mcp/registered-tools/${encodeURIComponent(serverId)}/${encodeURIComponent(toolName)}/enabled`,
    jsonRequest({ enabled }),
    'Toggle MCP tool failed',
  );
  return data.tool;
}

export function setMcpToolApproval(payload: {
  agent_code: string;
  server_id: string;
  tool_name: string;
  allowed: boolean;
  reason?: string;
}): Promise<Record<string, unknown>> {
  return requestJson(
    `${API_BASE}/api/v1/mcp/tools/approval`,
    jsonRequest(payload),
    'MCP approval failed',
  );
}

export function callMcpTool(payload: {
  server_id?: string;
  tool_name: string;
  agent_code: string;
  arguments: Record<string, unknown>;
}): Promise<Record<string, unknown>> {
  return requestJson(
    `${API_BASE}/api/v1/mcp/tools/call`,
    jsonRequest(payload),
    'MCP call failed',
  );
}

export async function listMcpToolCallLogs(
  limit = 100,
  serverId = '',
): Promise<McpToolCallLog[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (serverId) params.set('server_id', serverId);
  const data = await requestJson<{ logs?: McpToolCallLog[] }>(
    `${API_BASE}/api/v1/mcp/tool-call-logs?${params.toString()}`,
    {},
    'MCP logs failed',
  );
  return data.logs ?? [];
}
