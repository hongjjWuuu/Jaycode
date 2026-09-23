import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { SkillsPage } from './SkillsPage';

afterEach(() => cleanup());

const skill = {
  code: 'demo.skill', plugin_id: 'demo-plugin', source_plugin: 'demo-plugin', name: 'Demo Skill', category: 'demo',
  execution_type: 'builtin', permissions: [], permission_levels: [], risk_level: 'low', input_schema: {}, output_schema: {},
  default_input: {}, dependencies: [], tests: [], version: 'v1', source_format: 'builtin', contract: {}, enabled: true,
  created_at: '', updated_at: '',
};

function renderPage(overrides: Partial<React.ComponentProps<typeof SkillsPage>> = {}) {
  return render(<SkillsPage
    plugins={[]}
    skills={[skill]}
    approvals={[]}
    logs={[]}
    selectedSkillCode="demo.skill"
    projectPath="."
    onSelectSkill={vi.fn()}
    onRefresh={vi.fn().mockResolvedValue(undefined)}
    onSkillEnabled={vi.fn().mockResolvedValue(undefined)}
    onSkillApproval={vi.fn().mockResolvedValue(undefined)}
    onExecuteSkill={vi.fn().mockResolvedValue({ output: { ok: true }, log_id: 'log-1', status: 'completed', latency_ms: 1 })}
    onAddToWorkflow={vi.fn()}
    onUninstallPlugin={vi.fn().mockResolvedValue({})}
    {...overrides}
  />);
}

describe('SkillsPage', () => {
  it('passes the selected Skill to the explicit Workflow callback', () => {
    const onAddToWorkflow = vi.fn();
    renderPage({ onAddToWorkflow });

    fireEvent.click(screen.getAllByRole('button', { name: '添加到 Workflow' })[0]);
    expect(onAddToWorkflow).toHaveBeenCalledWith(skill);
  });

  it('surfaces a rejected Skill execution in the page output', async () => {
    renderPage({ onExecuteSkill: vi.fn().mockRejectedValue(new Error('审批尚未通过')) });

    fireEvent.click(screen.getByRole('button', { name: '测试调用 Skill' }));
    expect(await screen.findByText('审批尚未通过')).toBeTruthy();
  });
});
