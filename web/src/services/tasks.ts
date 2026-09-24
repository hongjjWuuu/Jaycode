import type { AgentEvent, AskResponse, ExecutionMode, TaskDetail, TaskSummary, WorkflowEdge, WorkflowNode } from '../types';
import { consumeSse, requestJson, responseError } from './http';

const API_BASE = '';
export type TaskRunPayload = { goal: string; project_path: string; max_files: number; require_human_review: boolean; execution_mode: ExecutionMode; workflow_name: string; input_text: string; nodes: WorkflowNode[]; edges: WorkflowEdge[] };
type TaskStreamPayload = Omit<TaskRunPayload, 'nodes'> & { nodes: Array<Pick<WorkflowNode, 'id' | 'type' | 'name' | 'config'>> };

async function stream(path: string, payload: TaskStreamPayload, onEvent: (event: AgentEvent | Record<string, unknown>) => void) {
  const response = await fetch(`${API_BASE}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  if (!response.ok) throw await responseError(response, '任务启动失败');
  await consumeSse(response, onEvent);
}

export function runTaskStream(payload: TaskRunPayload, onEvent: (event: AgentEvent | Record<string, unknown>) => void) {
  return stream('/api/v1/tasks/run/stream', { ...payload, nodes: payload.nodes.map(({ id, type, name, config }) => ({ id, type, name, config })), edges: payload.edges }, onEvent);
}

export function runCollaborationTaskStream(payload: TaskRunPayload, onEvent: (event: AgentEvent | Record<string, unknown>) => void) {
  return stream('/api/v1/tasks/collaborate/stream', { ...payload, execution_mode: 'collaboration', nodes: [], edges: [] }, onEvent);
}

export async function listTasks(): Promise<TaskSummary[]> { return (await requestJson<{ tasks?: TaskSummary[] }>('/api/v1/tasks', {}, '任务列表读取失败')).tasks ?? []; }
export function getTaskDetail(taskId: string): Promise<TaskDetail> { return requestJson(`/api/v1/tasks/${encodeURIComponent(taskId)}`, {}, 'Task detail failed'); }
export async function getTaskReport(taskId: string): Promise<string> { return (await requestJson<{ final_report?: string }>(`/api/v1/tasks/${encodeURIComponent(taskId)}/report`, {}, '报告读取失败')).final_report ?? ''; }
export async function getTaskEvents(taskId: string): Promise<AgentEvent[]> { return (await requestJson<{ events?: AgentEvent[] }>(`/api/v1/tasks/${encodeURIComponent(taskId)}/events`, {}, '事件读取失败')).events ?? []; }
export function reviewTask(taskId: string, action: 'approve' | 'reject' | 'revise', comment: string) { return requestJson(`/api/v1/tasks/${encodeURIComponent(taskId)}/${action}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ comment }) }, '审核动作提交失败'); }
export function applyReviewAction(taskId: string, action: string, comment: string, payload: Record<string, unknown> = {}) { return requestJson<{ message: string }>(`/api/v1/tasks/${encodeURIComponent(taskId)}/review-action`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action, comment, payload }) }, '审核操作失败'); }
export function askTask(taskId: string, question: string, collection = 'default'): Promise<AskResponse> { return requestJson(`/api/v1/tasks/${encodeURIComponent(taskId)}/ask`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, collection }) }, '任务追问失败'); }
