import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { NodeConfig } from './NodeConfig';

afterEach(() => cleanup());

describe('NodeConfig', () => {
  it('shows the node role as a fixed Chinese summary with its dedicated controls', () => {
    render(<NodeConfig node={{ id: 'knowledge', type: 'rag', name: 'Knowledge Query', x: 0, y: 0, config: { knowledge_scope: 'custom', collection: 'project-memory', top_k: 5 } }} approvals={[]} onNodeChange={vi.fn()} onConfigChange={vi.fn()} onApproveSkill={vi.fn(async () => undefined)} onDelete={vi.fn()} />);
    expect(screen.getByText('知识检索')).toBeTruthy();
    expect(screen.getByText('从知识库中检索与任务相关的资料。')).toBeTruthy();
    expect(screen.getByDisplayValue('project-memory')).toBeTruthy();
    expect(screen.queryByRole('option', { name: 'planner' })).toBeNull();
  });
});
