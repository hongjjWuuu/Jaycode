import { describe, expect, it, vi } from 'vitest';
import { listLlmTraces, saveLlmPrompt } from './llm';

describe('LLM service', () => {
  it('encodes trace query parameters and returns traces', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ traces: [{ trace_id: 't1' }] }), { status: 200 }));
    await expect(listLlmTraces(5, 'planner')).resolves.toEqual([{ trace_id: 't1' }]);
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/llm/traces?limit=5&agent=planner', {});
    fetchMock.mockRestore();
  });

  it('uses the P2 error envelope for failed prompt saves', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ error_code: 'VALIDATION_FAILED', message: 'invalid prompt', request_id: 'req-1' }), { status: 422 }));
    await expect(saveLlmPrompt({ agent: 'planner', prompt_version: 'v1', title: 'x', system_suffix: 's' })).rejects.toMatchObject({ errorCode: 'VALIDATION_FAILED', requestId: 'req-1', message: 'invalid prompt' });
    fetchMock.mockRestore();
  });
});
