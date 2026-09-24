import type { LearningChatResponse, LearningPlanRecord } from '../types';
import { requestJson } from './http';

const json = (body: unknown): RequestInit => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
export function chatLearningCoach(payload: { topic: string; level: string; question: string; answer?: string; task_id?: string; turn?: number }): Promise<LearningChatResponse> { return requestJson('/api/v1/learning/coach/chat', json(payload), 'Learning chat failed'); }
export async function createTaskLearningPlan(taskId: string, payload: { topic: string; level: string; days: number; goal?: string; comment?: string }): Promise<LearningPlanRecord> { return (await requestJson<{ plan: LearningPlanRecord }>(`/api/v1/tasks/${encodeURIComponent(taskId)}/learning-plan`, json(payload), 'Learning plan failed')).plan; }
export async function listLearningPlans(taskId?: string): Promise<LearningPlanRecord[]> { return (await requestJson<{ plans?: LearningPlanRecord[] }>(`/api/v1/learning/plans${taskId ? `?task_id=${encodeURIComponent(taskId)}` : ''}`, {}, 'Learning plans failed')).plans ?? []; }
export async function updateLearningPlanStatus(planId: string, status: LearningPlanRecord['status']): Promise<LearningPlanRecord> { return (await requestJson<{ plan: LearningPlanRecord }>(`/api/v1/learning/plans/${encodeURIComponent(planId)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }) }, 'Learning plan status failed')).plan; }
