import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ReportsPage } from './ReportsPage';

afterEach(() => cleanup());

describe('ReportsPage', () => {
  it('switches report tabs and opens the knowledge workspace', () => {
    const onOpenKnowledge = vi.fn();
    render(<ReportsPage finalReport="# 最终报告" mermaid="graph LR\nA --> B" nodes={[]} edges={[]} riskLevel="low" reviewRequired={false} nextActions={[]} suggestions={['补充测试']} suggestionRecords={[]} knowledgeDocumentCount={2} onOpenKnowledge={onOpenKnowledge} />);
    fireEvent.click(screen.getByRole('button', { name: 'Mermaid 图' }));
    expect(document.querySelector('.mermaid-visual')).toHaveTextContent('graph LR\\nA --> B');
    fireEvent.click(screen.getByRole('button', { name: '打开追问知识库' }));
    expect(onOpenKnowledge).toHaveBeenCalledOnce();
  });

  it('shows a compatible API error when opening knowledge fails', async () => {
    render(<ReportsPage finalReport="" mermaid="" nodes={[]} edges={[]} riskLevel="low" reviewRequired={false} nextActions={[]} suggestions={[]} suggestionRecords={[]} knowledgeDocumentCount={0} onOpenKnowledge={vi.fn().mockRejectedValue({ message: '知识库不可用', error_code: 'dependency_unavailable', request_id: 'req-report-1' })} />);
    fireEvent.click(screen.getByRole('button', { name: '打开追问知识库' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('知识库不可用');
  });
});
