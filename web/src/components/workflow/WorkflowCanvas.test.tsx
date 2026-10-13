import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { WorkflowCanvas } from './WorkflowCanvas';

afterEach(() => cleanup());

describe('WorkflowCanvas', () => {
  it('uses the shared Chinese labels for stored English workflow node names', () => {
    render(<WorkflowCanvas canvasRef={{ current: null }} canvasSize={{ width: 800, height: 560 }} connectFrom={null} edges={[]} selectedEdgeKey="" selectedNodeId="" nodeStatus={{}} onCanvasPointerMove={vi.fn()} onDrop={vi.fn()} onEndPointer={vi.fn()} onStartCanvasPan={vi.fn()} onStartMove={vi.fn()} onSelectEdge={vi.fn()} onToggleConnect={vi.fn()} nodes={[{ id: 'plan', type: 'planner', name: 'Planner', x: 0, y: 0, config: {} }, { id: 'review', type: 'human_review', name: 'Human Review', x: 220, y: 0, config: {} }]} />);
    expect(screen.getByText('规划')).toBeTruthy();
    expect(screen.getByText('人工审核')).toBeTruthy();
    expect(screen.queryByText('Planner')).toBeNull();
    expect(screen.queryByText('Human Review')).toBeNull();
  });

  it('exposes the hold-and-drag canvas affordance and panning state', () => {
    const { container } = render(<WorkflowCanvas canvasRef={{ current: null }} canvasSize={{ width: 960, height: 720 }} connectFrom={null} edges={[]} selectedEdgeKey="" selectedNodeId="" nodeStatus={{}} isPanning onCanvasPointerMove={vi.fn()} onDrop={vi.fn()} onEndPointer={vi.fn()} onStartCanvasPan={vi.fn()} onStartMove={vi.fn()} onSelectEdge={vi.fn()} onToggleConnect={vi.fn()} nodes={[]} />);
    expect(screen.getByText('按住空白处拖动画布')).toBeTruthy();
    expect(container.querySelector('.workflow-canvas.panning')).toBeTruthy();
  });
});
