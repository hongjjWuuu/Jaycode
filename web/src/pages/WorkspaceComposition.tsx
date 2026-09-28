import { Activity, BarChart3, FileText, History, LayoutDashboard, MessageSquare, Puzzle, Workflow, Wrench } from 'lucide-react';
import type { WorkflowEdge, WorkflowNode } from '../types';
import { useViewNavigation, type ViewKey } from '../hooks/useViewNavigation';
import { useWorkspaceCoordinator } from '../hooks/useWorkspaceCoordinator';
import { FocusPicker } from '../components/run/FocusPicker';
import { BenchmarkPage } from './BenchmarkPage';
import { ChatWorkspacePage } from './ChatPage';
import { HistoryPage } from './HistoryPage';
import { LlmPage } from './LlmPage';
import { MarketplacePage } from './MarketplacePage';
import { McpPage } from './McpPage';
import { OperationsPage } from './OperationsPage';
import { ReportsPage } from './ReportsPage';
import { RunPage } from './RunPage';
import { SkillsPage } from './SkillsPage';
import { WorkflowPage } from './WorkflowPage';
import { pageFrames } from './workspacePageFrames';

const navItems: Array<{ view: ViewKey; label: string; icon: typeof LayoutDashboard }> = [
  { view: 'run', label: '运行', icon: LayoutDashboard }, { view: 'workflow', label: '编排', icon: Workflow },
  { view: 'reports', label: '报告', icon: FileText }, { view: 'chat', label: '追问', icon: MessageSquare },
  { view: 'history', label: '历史', icon: History }, { view: 'operations', label: '运营', icon: Activity },
  { view: 'llm', label: 'LLM', icon: BarChart3 }, { view: 'mcp', label: 'MCP', icon: Wrench },
  { view: 'skills', label: 'Skills', icon: Puzzle }, { view: 'marketplace', label: 'Market', icon: Puzzle },
  { view: 'benchmark', label: 'Bench', icon: Activity },
];
const initialNodes: WorkflowNode[] = [
  { id: 'plan', type: 'planner', name: 'Planner', x: 64, y: 92, config: {} },
  { id: 'analyze', type: 'agent', name: 'Project Agent', x: 292, y: 92, config: { agent_type: 'project_analyzer', max_files: 100 } },
  { id: 'review', type: 'human_review', name: 'Human Review', x: 520, y: 92, config: { require_comment: false } },
  { id: 'report', type: 'reporter', name: 'Reporter', x: 748, y: 92, config: {} },
];
const initialEdges: WorkflowEdge[] = [{ source: 'plan', target: 'analyze' }, { source: 'analyze', target: 'review' }, { source: 'review', target: 'report' }];

/** Pure workbench shell: navigation, page selection, and the application-level focus modal. */
export function WorkspaceComposition() {
  const { activeView, setActiveView } = useViewNavigation();
  const ActivePage = pageFrames[activeView];
  const pages = useWorkspaceCoordinator({ activeView, setActiveView, initialNodes, initialEdges });

  return <div className="app-shell">
    <aside className="side-nav"><div className="brand-mark">D</div><nav>{navItems.map((item) => {
      const Icon = item.icon;
      return <button key={item.view} className={activeView === item.view ? 'active' : ''} onClick={() => pages.navigate(item.view)} title={item.label}><Icon size={22} /><span>{item.label}</span></button>;
    })}</nav></aside>
    <main className="app-main">
      <header className="topbar"><div><h1>Jaycode</h1><span>可视化 Workflow 任务工作台</span></div><div className="topbar-actions"><div className={`status-pill ${pages.activeStatus}`}>{pages.activeStatus}</div></div></header>
      <ActivePage>
        {activeView === 'run' ? <RunPage {...pages.runPage} /> : null}
        {activeView === 'workflow' ? <WorkflowPage {...pages.workflowPage} /> : null}
        {activeView === 'reports' ? <ReportsPage {...pages.reportsPage} /> : null}
        {activeView === 'chat' ? <ChatWorkspacePage {...pages.chatPage} /> : null}
        {activeView === 'history' ? <HistoryPage {...pages.historyPage} /> : null}
        {activeView === 'operations' ? <OperationsPage {...pages.operationsPage} /> : null}
        {activeView === 'llm' ? <LlmPage {...pages.llmPage} /> : null}
        {activeView === 'mcp' ? <McpPage {...pages.mcpPage} /> : null}
        {activeView === 'skills' ? <SkillsPage {...pages.skillsPage} /> : null}
        {activeView === 'marketplace' ? <MarketplacePage {...pages.marketplacePage} /> : null}
        {activeView === 'benchmark' ? <BenchmarkPage {...pages.benchmarkPage} /> : null}
      </ActivePage>
      {pages.focusPicker.open ? <FocusPicker files={pages.focusPicker.files} loading={pages.focusPicker.loading} error={pages.focusPicker.error} modules={pages.focusPicker.modules} onClose={pages.focusPicker.onClose} onSelect={pages.focusPicker.onSelect} /> : null}
    </main>
  </div>;
}
