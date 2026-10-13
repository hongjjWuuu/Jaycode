import { describe, expect, it } from 'vitest';
import { inspectWorkflowRequirements } from './workflowRequirements';

describe('inspectWorkflowRequirements', () => {
  it('detects project agents and project-scoped knowledge', () => {
    const result = inspectWorkflowRequirements([
      { id: 'analyze', type: 'agent', name: '分析', x: 0, y: 0, config: { agent_type: 'project_analyzer' } },
      { id: 'rag', type: 'rag', name: '知识', x: 0, y: 0, config: { knowledge_scope: 'project' } },
    ]);
    expect(result.requiresProject).toBe(true);
    expect(result.knowledgeScopeMissing).toBe(false);
  });

  it('flags old knowledge nodes without an explicit scope', () => {
    const result = inspectWorkflowRequirements([
      { id: 'rag', type: 'rag', name: '旧知识', x: 0, y: 0, config: { collection: 'project-memory' } },
    ]);
    expect(result.knowledgeScopeMissing).toBe(true);
  });

  it('allows planner and reporter only workflows without a project', () => {
    const result = inspectWorkflowRequirements([
      { id: 'plan', type: 'planner', name: '规划', x: 0, y: 0, config: {} },
      { id: 'report', type: 'reporter', name: '报告', x: 0, y: 0, config: {} },
    ]);
    expect(result.requiresProject).toBe(false);
  });
});
