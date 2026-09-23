import type {
  SkillApproval,
  SkillExecutionLog,
  SkillPlugin,
  SkillRecord,
  SkillTestResult,
  SkillVersionSnapshot,
} from '../types';
import { requestJson } from './http';

const API_BASE = '';
const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

export async function listSkillPlugins(): Promise<SkillPlugin[]> {
  const data = await requestJson<{ plugins?: SkillPlugin[] }>(
    `${API_BASE}/api/v1/skills/plugins`, {}, 'Skill plugins failed',
  );
  return data.plugins ?? [];
}

export async function listSkills(category = ''): Promise<SkillRecord[]> {
  const suffix = category ? `?category=${encodeURIComponent(category)}` : '';
  const data = await requestJson<{ skills?: SkillRecord[] }>(
    `${API_BASE}/api/v1/skills${suffix}`, {}, 'Skills failed',
  );
  return data.skills ?? [];
}

export async function listSkillApprovals(agentCode = ''): Promise<SkillApproval[]> {
  const suffix = agentCode ? `?agent_code=${encodeURIComponent(agentCode)}` : '';
  const data = await requestJson<{ approvals?: SkillApproval[] }>(
    `${API_BASE}/api/v1/skills/approvals${suffix}`, {}, 'Skill approvals failed',
  );
  return data.approvals ?? [];
}

export async function listSkillExecutionLogs(limit = 100, skillCode = ''): Promise<SkillExecutionLog[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (skillCode) params.set('skill_code', skillCode);
  const data = await requestJson<{ logs?: SkillExecutionLog[] }>(
    `${API_BASE}/api/v1/skills/execution-logs?${params}`, {}, 'Skill logs failed',
  );
  return data.logs ?? [];
}

export async function listSkillVersions(skillCode: string): Promise<SkillVersionSnapshot[]> {
  const data = await requestJson<{ versions?: SkillVersionSnapshot[] }>(
    `${API_BASE}/api/v1/skills/${encodeURIComponent(skillCode)}/versions`, {}, 'Skill versions failed',
  );
  return data.versions ?? [];
}

export async function rollbackSkillVersion(skillCode: string, version: string): Promise<SkillRecord> {
  const data = await requestJson<{ skill: SkillRecord }>(
    `${API_BASE}/api/v1/skills/${encodeURIComponent(skillCode)}/rollback`, json({ version }), 'Skill rollback failed',
  );
  return data.skill;
}

export async function setSkillEnabled(skillCode: string, enabled: boolean): Promise<SkillRecord> {
  const data = await requestJson<{ skill: SkillRecord }>(
    `${API_BASE}/api/v1/skills/${encodeURIComponent(skillCode)}/enabled`, json({ enabled }), 'Toggle skill failed',
  );
  return data.skill;
}

export function testSkill(payload: {
  skill_code: string;
  agent_code: string;
  test?: Record<string, unknown>;
}): Promise<SkillTestResult> {
  return requestJson(
    `${API_BASE}/api/v1/skills/${encodeURIComponent(payload.skill_code)}/test`, json(payload), 'Skill test failed',
  );
}

export async function uninstallSkillPlugin(pluginId: string): Promise<Record<string, unknown>> {
  const data = await requestJson<{ uninstall?: Record<string, unknown> }>(
    `${API_BASE}/api/v1/skills/plugins/${encodeURIComponent(pluginId)}`, { method: 'DELETE' }, 'Uninstall skill plugin failed',
  );
  return data.uninstall ?? {};
}

export async function setSkillApproval(payload: {
  skill_code: string;
  agent_code: string;
  allowed: boolean;
  reason?: string;
}): Promise<SkillApproval> {
  const data = await requestJson<{ approval: SkillApproval }>(
    `${API_BASE}/api/v1/skills/${encodeURIComponent(payload.skill_code)}/approval`, json(payload), 'Skill approval failed',
  );
  return data.approval;
}

export function executeSkill(payload: {
  skill_code: string;
  agent_code: string;
  input: Record<string, unknown>;
  task_id?: string;
}): Promise<{
  log_id: string;
  skill: SkillRecord;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  status: string;
  latency_ms: number;
}> {
  return requestJson(
    `${API_BASE}/api/v1/skills/${encodeURIComponent(payload.skill_code)}/execute`, json(payload), 'Skill execution failed',
  );
}
