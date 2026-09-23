import { requestJson } from './http';
import type { LlmPromptAbTestResult, LlmPromptPayload, LlmPromptVersion, LlmTrace, LlmUsageDashboard } from '../types';

const API_BASE = '';
const json = (body: unknown): RequestInit => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

export async function listLlmTraces(limit = 50, agent = ''): Promise<LlmTrace[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (agent) params.set('agent', agent);
  const data = await requestJson<{ traces?: LlmTrace[] }>(`${API_BASE}/api/v1/llm/traces?${params}`, {}, 'LLM traces failed');
  return data.traces ?? [];
}

export async function listLlmPrompts(agent = ''): Promise<LlmPromptVersion[]> {
  const suffix = agent ? `?agent=${encodeURIComponent(agent)}` : '';
  const data = await requestJson<{ prompts?: LlmPromptVersion[] }>(`${API_BASE}/api/v1/llm/prompts${suffix}`, {}, 'LLM prompts failed');
  return data.prompts ?? [];
}

export async function saveLlmPrompt(payload: LlmPromptPayload): Promise<LlmPromptVersion> {
  const data = await requestJson<{ prompt: LlmPromptVersion }>(`${API_BASE}/api/v1/llm/prompts`, json(payload), 'Save prompt failed');
  return data.prompt;
}

export async function setActiveLlmPrompt(agent: string, promptVersion: string): Promise<LlmPromptVersion> {
  const data = await requestJson<{ prompt: LlmPromptVersion }>(`${API_BASE}/api/v1/llm/prompts/active`, json({ agent, prompt_version: promptVersion }), 'Set active prompt failed');
  return data.prompt;
}

export function runLlmPromptAbTest(payload: { agent: string; prompt_a: string; prompt_b: string; system_prompt: string; user_prompt: string; fallback: string }): Promise<LlmPromptAbTestResult> {
  return requestJson(`${API_BASE}/api/v1/llm/prompts/ab-test`, json(payload), 'Prompt A/B test failed');
}

export function getLlmUsage(limit = 500, agent = ''): Promise<LlmUsageDashboard> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (agent) params.set('agent', agent);
  return requestJson(`${API_BASE}/api/v1/llm/usage?${params}`, {}, 'LLM usage failed');
}
