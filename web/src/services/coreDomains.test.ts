import { afterEach, describe, expect, it, vi } from 'vitest';
import { listTasks, runTaskStream } from './tasks';
import { queryKnowledge } from './rag';
import { createTaskLearningPlan } from './learning';
import { saveWorkflow } from './workflows';

afterEach(() => vi.restoreAllMocks());

describe('core domain services', () => {
  it('uses the task stream payload contract and consumes SSE events', async () => {
    const body = new ReadableStream({ start(controller) { controller.enqueue(new TextEncoder().encode('data: {"type":"complete"}\n\n')); controller.close(); } });
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(body, { status: 200 }));
    const onEvent = vi.fn();
    await runTaskStream({ goal: 'review', project_path: '.', max_files: 10, require_human_review: true, execution_mode: 'workflow', workflow_name: 'wf', input_text: 'review', nodes: [{ id: 'plan', type: 'planner', name: 'Plan', x: 0, y: 0, config: {} }], edges: [] }, onEvent);
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/tasks/run/stream', expect.objectContaining({ method: 'POST' }));
    expect(onEvent).toHaveBeenCalledWith({ type: 'complete' });
  });

  it('uses shared envelope parsing for task and RAG failures', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response(JSON.stringify({ error_code: 'DEPENDENCY_UNAVAILABLE', message: 'tasks offline', request_id: 'req-core-1' }), { status: 503 }));
    await expect(listTasks()).rejects.toMatchObject({ errorCode: 'DEPENDENCY_UNAVAILABLE', requestId: 'req-core-1' });
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response(JSON.stringify({ results: [{ path: 'a.md' }] }), { status: 200 }));
    await expect(queryKnowledge('project-memory', 'architecture', 3)).resolves.toEqual([{ path: 'a.md' }]);
  });

  it('keeps Learning and Workflow JSON payloads unchanged', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ plan: { plan_id: 'p1' } }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ workflow: { workflow_id: 'wf1' } }), { status: 200 }));
    await createTaskLearningPlan('task 1', { topic: 'topic', level: 'beginner', days: 7 });
    await saveWorkflow({ name: 'Flow', nodes: [], edges: [] });
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/tasks/task%201/learning-plan');
    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/workflows');
  });
});
