import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { WorkflowPage } from './WorkflowPage';

afterEach(() => cleanup());

const canvas = {
  canvasRef: { current: null }, canvasSize: { width: 800, height: 560 }, connectFrom: null,
  edges: [], nodes: [], nodeStatus: {}, selectedEdgeKey: '', selectedNodeId: '',
  onCanvasPointerMove: vi.fn(), onDrop: vi.fn(), onEndPointer: vi.fn(), onStartCanvasPan: vi.fn(),
  onStartMove: vi.fn(), onSelectEdge: vi.fn(), onToggleConnect: vi.fn(),
};
const nodeConfig = { node: undefined, approvals: [], onNodeChange: vi.fn(), onConfigChange: vi.fn(), onApproveSkill: vi.fn(async () => undefined), onDelete: vi.fn() };
const edgeConfig = { edge: undefined, nodes: [], onChange: vi.fn(), onDelete: vi.fn() };

function renderPage(overrides: Partial<React.ComponentProps<typeof WorkflowPage>> = {}) {
  return render(<WorkflowPage name="默认流程" description="描述" validation={null} workflows={[{ workflow_id: 'wf-1', name: '已保存流程', description: '', nodes: [], edges: [], created_at: '', updated_at: '' }]} canvas={canvas} nodeConfig={nodeConfig} edgeConfig={edgeConfig} onNameChange={vi.fn()} onDescriptionChange={vi.fn()} onNew={vi.fn()} onAddNode={vi.fn()} onSave={vi.fn()} onValidate={vi.fn()} onLoad={vi.fn()} onDelete={vi.fn()} onRefresh={vi.fn()} {...overrides} />);
}

describe('WorkflowPage', () => {
  it('composes the canvas and configuration components while invoking editor callbacks', () => {
    const onSave = vi.fn(); const onValidate = vi.fn(); const onLoad = vi.fn(); const onNew = vi.fn(); const onAddNode = vi.fn();
    renderPage({ onSave, onValidate, onLoad, onNew, onAddNode });
    expect(document.querySelector('.workflow-canvas')).toBeTruthy();
    expect(screen.getByText('选择一个流程节点后配置参数。')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '保存 Workflow' }));
    fireEvent.click(screen.getByRole('button', { name: '校验 Workflow' }));
    fireEvent.click(screen.getByRole('button', { name: '新建画布流程' }));
    fireEvent.click(screen.getByRole('button', { name: '规划' }));
    fireEvent.click(screen.getByRole('button', { name: /^已保存流程/ }));
    expect(onSave).toHaveBeenCalledOnce(); expect(onValidate).toHaveBeenCalledOnce(); expect(onNew).toHaveBeenCalledOnce(); expect(onAddNode).toHaveBeenCalledWith('planner'); expect(onLoad).toHaveBeenCalledWith(expect.objectContaining({ workflow_id: 'wf-1' }));
  });

  it('presents numeric saved workflow names as readable cards', () => {
    renderPage({ workflows: [{ workflow_id: 'wf-2', name: '2', description: '项目分析', nodes: [{ id: 'plan', type: 'planner', name: 'Planner', x: 0, y: 0, config: {} }], edges: [], created_at: '', updated_at: '' }] });
    expect(screen.getByText('流程 2')).toBeTruthy();
    expect(screen.getByText('1 个节点 · 0 条连线')).toBeTruthy();
  });

  it('confirms before deleting a saved workflow', () => {
    const onDelete = vi.fn();
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderPage({ onDelete });
    fireEvent.click(screen.getByRole('button', { name: '删除 已保存流程' }));
    expect(confirm).toHaveBeenCalledOnce();
    expect(onDelete).toHaveBeenCalledWith('wf-1');
  });

  it('shows validation output and refreshes stored workflows', () => {
    const onRefresh = vi.fn();
    renderPage({ onRefresh, validation: { valid: false, errors: ['存在循环'], warnings: [], node_count: 2, edge_count: 2, parallel_sources: [] } });
    expect(document.querySelector('.workflow-validation')).toHaveTextContent('存在循环');
    fireEvent.click(screen.getByRole('button', { name: '刷新' }));
    expect(onRefresh).toHaveBeenCalledOnce();
  });

  it('renders a compatible service error when saving fails', async () => {
    renderPage({ onSave: vi.fn().mockRejectedValue({ message: '流程保存失败', error_code: 'CONFLICT', request_id: 'req-workflow-1' }) });
    fireEvent.click(screen.getByRole('button', { name: '保存 Workflow' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('流程保存失败');
    expect(screen.getByRole('button', { name: '复制 request_id: req-workflow-1' })).toBeTruthy();
  });
});
