import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ChatWorkspacePage } from './ChatPage';

afterEach(() => cleanup());

function renderPage(overrides: Partial<React.ComponentProps<typeof ChatWorkspacePage>> = {}) {
  return render(<ChatWorkspacePage chatInput="问题" chatMessages={[]} chatMode="task" chatSources={[]} knowledgeDocs={[]} knowledgeNote="" memories={[]} learningPlans={[]} latestTaskId="task-1" tasks={[]} selectedTaskId="task-1" onChatInputChange={vi.fn()} onChatModeChange={vi.fn()} onKnowledgeNoteChange={vi.fn()} onMemoryConfirm={vi.fn()} onMemoryDelete={vi.fn()} onMemoryReject={vi.fn()} onLearningPlanStatus={vi.fn()} onOpenTask={vi.fn()} onRefreshTasks={vi.fn()} onSaveKnowledgeNote={vi.fn()} onSend={vi.fn()} {...overrides} />);
}

describe('ChatWorkspacePage', () => {
  it('shows a compatible API error when sending a question fails', async () => {
    renderPage({ onSend: vi.fn().mockRejectedValue({ message: '追问被拒绝', error_code: 'validation_error', request_id: 'req-chat-1' }) });
    fireEvent.click(screen.getByRole('button', { name: '发送追问' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('追问被拒绝');
    expect(screen.getByRole('alert')).toHaveTextContent('req-chat-1');
  });
});
