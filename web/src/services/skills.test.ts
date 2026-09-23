import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from './http';
import { listSkills, setSkillApproval, testSkill } from './skills';

afterEach(() => vi.restoreAllMocks());

describe('Skills service', () => {
  it('encodes category filters and unwraps skill collections', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ skills: [{ code: 'release notes' }] }), { status: 200 }),
    );

    await expect(listSkills('release notes')).resolves.toEqual([{ code: 'release notes' }]);
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/skills?category=release%20notes', {});
  });

  it('sends a Skill test JSON payload', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ skill_code: 'lint', total: 1, passed: 1, failed: 0, results: [] }), { status: 200 }),
    );

    await expect(testSkill({ skill_code: 'lint', agent_code: 'workflow_runner' })).resolves.toMatchObject({ passed: 1 });
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/skills/lint/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ skill_code: 'lint', agent_code: 'workflow_runner' }),
    });
  });

  it('retains the compatible API error envelope when approval fails', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ error_code: 'FORBIDDEN', message: 'Admin role required.', request_id: 'req-skill-1' }), { status: 403 }),
    );

    await expect(setSkillApproval({ skill_code: 'lint', agent_code: 'workflow_runner', allowed: true }))
      .rejects.toEqual(new ApiError('FORBIDDEN', 'req-skill-1', 'Admin role required.'));
  });
});
