import {
  Activity,
  ArrowRight,
  BarChart3,
  BookOpen,
  Boxes,
  Check,
  ClipboardList,
  Database,
  FileText,
  FileSearch,
  FolderOpen,
  History,
  LayoutDashboard,
  MessageSquare,
  Play,
  Puzzle,
  RefreshCw,
  Save,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
  Workflow,
  Wrench,
  X,
} from 'lucide-react';
import { FormEvent, PointerEvent, ReactNode, Ref, useEffect, useMemo, useRef, useState } from 'react';
import type { ComponentType } from 'react';
import {
  applyReviewAction, askTask, getTaskDetail, getTaskEvents, listTasks, reviewTask,
  runCollaborationTaskStream, runTaskStream,
} from '../services/tasks';
import {
  addKnowledgeNote, confirmMemory, deleteMemory, deleteRagGoldCase, extractMemoryCandidates,
  listKnowledgeDocuments, listMemories, listRagGoldCases, queryKnowledge, rejectMemory, saveRagGoldCase,
} from '../services/rag';
import { chatLearningCoach, createTaskLearningPlan, listLearningPlans, updateLearningPlanStatus } from '../services/learning';
import { listProjectFiles } from '../services/projectFiles';
import { listWorkflows, saveWorkflow, updateWorkflow, validateWorkflow } from '../services/workflows';
import {
  AgentEvent,
  AgentOutput,
  AskResponse,
  BenchmarkCase,
  BenchmarkRun,
  BenchmarkType,
  ExecutionMode,
  LearningChatResponse,
  LearningPlanRecord,
  LlmPromptAbTestResult,
  LlmPromptPayload,
  LlmPromptVersion,
  LlmTrace,
  LlmUsageDashboard,
  MarketplaceCatalogItem,
  MarketplaceInstall,
  MarketplacePreview,
  McpRegisteredTool,
  McpServerConfig,
  McpStatus,
  McpToolCallLog,
  MemoryRecord,
  NodeStatus,
  RagDocument,
  RagGoldCase,
  RagResult,
  ResumeSnapshot,
  SkillApproval,
  SkillExecutionLog,
  SkillPlugin,
  SkillRecord,
  SkillTestResult,
  SkillVersionSnapshot,
  SuggestionRecord,
  TaskResultPayload,
  TaskSummary,
  ToolCall,
  WorkflowEdge,
  WorkflowNode,
  WorkflowRecord,
  WorkflowValidation,
} from '../types';

import { ViewKey, useViewNavigation } from '../hooks/useViewNavigation';
import { useTaskWorkspace } from '../hooks/useTaskWorkspace';
import { useWorkflowEditor } from '../hooks/useWorkflowEditor';
import { ChatMessage, ChatMode, useKnowledgeChat } from '../hooks/useKnowledgeChat';
import { useGovernanceConsole } from '../hooks/useGovernanceConsole';
import { EnabledState, FieldHelp, PanelTitle, RiskBadge } from '../components/DisplayPrimitives';
import { PageBoundary } from '../components/PageBoundary';
import { BenchmarkPage as BenchmarkConsolePage } from './BenchmarkPage';
import { ChatWorkspacePage as ChatConsolePage } from './ChatPage';
import { HistoryPage as HistoryWorkspacePage } from './HistoryPage';
import { LlmPage as LlmConsolePage } from './LlmPage';
import { MarketplacePage } from './MarketplacePage';
import { McpPage as McpConsolePage } from './McpPage';
import { ReportsPage as ReportsWorkspacePage } from './ReportsPage';
import { RunPage } from './RunPage';
import { SkillsPage as SkillsConsolePage } from './SkillsPage';
import { WorkflowPage } from './WorkflowPage';
type FocusKind = 'module' | 'file';
type ReportTab = 'final' | 'mentor' | 'mermaid' | 'governance';

const defaultProjectPath = '.';
const dragPayloadMime = 'application/jaycode-node';

const modeItems: Array<{ mode: ExecutionMode; label: string; icon: typeof Boxes }> = [
  { mode: 'agent', label: 'Agent', icon: Boxes },
  { mode: 'workflow', label: 'Workflow', icon: Workflow },
  { mode: 'planner', label: 'Planner', icon: ClipboardList },
  { mode: 'collaboration', label: 'Collab', icon: Activity },
  { mode: 'tool', label: 'Tool', icon: Wrench },
  { mode: 'knowledge', label: 'Knowledge', icon: Database },
];

const modeHelp: Record<ExecutionMode, { title: string; description: string; button: string }> = {
  agent: {
    title: 'Agent 模式',
    description: '不使用当前画布；后端运行默认小工作流：Planner → Project Analyzer → Reporter。',
    button: '运行 Agent 模式',
  },
  workflow: {
    title: 'Workflow 模式',
    description: '使用当前可视化画布的节点和连线执行；拖拽编排后的流程只在这个模式生效。',
    button: '运行当前画布',
  },
  planner: {
    title: 'Planner 模式',
    description: '不使用当前画布；根据目标自动生成 Workflow，执行完成后把生成的流程刷新到画布。',
    button: '生成并运行 Workflow',
  },
  collaboration: {
    title: 'Collab 模式',
    description: '不使用当前画布；调用固定 collaboration_graph：Planner → Project Analyzer → Code Reviewer → RAG Processor → Supervisor → Reporter。',
    button: '运行多 Agent 协作',
  },
  tool: {
    title: 'Tool 模式',
    description: '不使用当前画布；后端运行默认工具工作流：Planner → MCP Tool → Reporter。',
    button: '运行 Tool 模式',
  },
  knowledge: {
    title: 'Knowledge 模式',
    description: '不使用当前画布；后端运行默认知识检索工作流：Planner → RAG Query → Reporter。',
    button: '运行 Knowledge 模式',
  },
};

const navItems: Array<{ view: ViewKey; label: string; icon: typeof LayoutDashboard }> = [
  { view: 'run', label: '运行', icon: LayoutDashboard },
  { view: 'workflow', label: '编排', icon: Workflow },
  { view: 'reports', label: '报告', icon: FileText },
  { view: 'chat', label: '追问', icon: MessageSquare },
  { view: 'history', label: '历史', icon: History },
  { view: 'llm', label: 'LLM', icon: BarChart3 },
  { view: 'mcp', label: 'MCP', icon: Wrench },
  { view: 'skills', label: 'Skills', icon: Puzzle },
  { view: 'marketplace', label: 'Market', icon: Puzzle },
  { view: 'benchmark', label: 'Bench', icon: Activity },
];

const palette = [
  { type: 'planner', name: 'Planner', icon: ClipboardList, config: {} },
  { type: 'agent', name: 'Project Agent', icon: FileSearch, config: { agent_type: 'project_analyzer', max_files: 100 } },
  { type: 'agent', name: 'Code Review', icon: ShieldCheck, config: { agent_type: 'code_reviewer', max_files: 100 } },
  { type: 'agent', name: 'File Review', icon: FileText, config: { agent_type: 'file_reviewer', file_path: 'README.md', max_chars: 20000 } },
  { type: 'agent', name: 'RAG Processor', icon: BookOpen, config: { agent_type: 'rag_processor', max_files: 100, ingest: true, collection: 'project-memory' } },
  { type: 'rag', name: 'Knowledge Query', icon: Database, config: { collection: 'default', top_k: 5 } },
  { type: 'mcp_tool', name: 'MCP Tool', icon: Wrench, config: { tool_name: 'filesystem.list' } },
  { type: 'skill', name: 'Skill', icon: Puzzle, config: { skill_code: 'code.review', agent_code: 'workflow_runner' } },
  { type: 'supervisor', name: 'Supervisor', icon: Activity, config: {} },
  { type: 'human_review', name: 'Human Review', icon: Check, config: { require_comment: false } },
  { type: 'reporter', name: 'Reporter', icon: FileSearch, config: {} },
];

const initialNodes: WorkflowNode[] = [
  { id: 'plan', type: 'planner', name: 'Planner', x: 64, y: 92, config: {} },
  { id: 'analyze', type: 'agent', name: 'Project Agent', x: 292, y: 92, config: { agent_type: 'project_analyzer', max_files: 100 } },
  { id: 'review', type: 'human_review', name: 'Human Review', x: 520, y: 92, config: { require_comment: false } },
  { id: 'report', type: 'reporter', name: 'Reporter', x: 748, y: 92, config: {} },
];

const initialEdges: WorkflowEdge[] = [
  { source: 'plan', target: 'analyze' },
  { source: 'analyze', target: 'review' },
  { source: 'review', target: 'report' },
];

const MarketplaceFrame = ({ children }: { children: ReactNode }) => (
  <PageBoundary name="marketplace">{children}</PageBoundary>
);
const SkillsFrame = ({ children }: { children: ReactNode }) => (
  <PageBoundary name="skills">{children}</PageBoundary>
);
const McpFrame = ({ children }: { children: ReactNode }) => (
  <PageBoundary name="mcp">{children}</PageBoundary>
);
const LlmFrame = ({ children }: { children: ReactNode }) => (
  <PageBoundary name="llm">{children}</PageBoundary>
);
const BenchmarkFrame = ({ children }: { children: ReactNode }) => (
  <PageBoundary name="benchmark">{children}</PageBoundary>
);
const ReportsFrame = ({ children }: { children: ReactNode }) => (
  <PageBoundary name="reports">{children}</PageBoundary>
);
const HistoryFrame = ({ children }: { children: ReactNode }) => (
  <PageBoundary name="history">{children}</PageBoundary>
);
const ChatFrame = ({ children }: { children: ReactNode }) => (
  <PageBoundary name="chat">{children}</PageBoundary>
);

const pageFrames: Record<ViewKey, ComponentType<{ children: ReactNode }>> = {
  run: RunPage,
  workflow: WorkflowPage,
  reports: ReportsFrame,
  chat: ChatFrame,
  history: HistoryFrame,
  llm: LlmFrame,
  mcp: McpFrame,
  skills: SkillsFrame,
  marketplace: MarketplaceFrame,
  benchmark: BenchmarkFrame,
};

export function WorkspaceApp() {
  const { activeView, setActiveView } = useViewNavigation();
  const ActivePage = pageFrames[activeView];
  const taskWorkspace = useTaskWorkspace();
  const workflowEditor = useWorkflowEditor(initialNodes, initialEdges);
  const knowledgeChat = useKnowledgeChat();
  const governance = useGovernanceConsole();
  const {
    tasks, setTasks, selectedTaskId, setSelectedTaskId, events, setEvents,
    finalReport, setFinalReport, refreshTasks,
  } = taskWorkspace;
  const {
    workflowId, setWorkflowId, workflowName, setWorkflowName, workflowDescription, setWorkflowDescription,
    savedWorkflows, setSavedWorkflows, nodes, setNodes, edges, setEdges, selectedNodeId, setSelectedNodeId,
    selectedEdgeKey, setSelectedEdgeKey, connectFrom, setConnectFrom, workflowValidation, setWorkflowValidation,
    refreshWorkflows, persistWorkflow, checkWorkflow,
  } = workflowEditor;
  const {
    knowledgeDocs, setKnowledgeDocs, knowledgeResults, setKnowledgeResults, knowledgeNote, setKnowledgeNote,
    memories, chatMode, setChatMode, chatInput, setChatInput, chatMessages, setChatMessages, chatSources, setChatSources,
    learningPlans, refreshMemories, refreshLearningPlans, confirm: confirmMemoryCandidate,
    reject: rejectMemoryCandidate, remove: removeMemoryCandidate, setPlanStatus,
  } = knowledgeChat;
  const {
    llmTraces, llmTraceAgent, llmPrompts, llmUsage, llmAgentFilter,
    mcpStatus, mcpServers, mcpTools, mcpLogs, skillPlugins, skills, skillApprovals, skillLogs, selectedSkillCode, setSelectedSkillCode,
    marketplaceCatalog, marketplaceInstalls, marketplacePreview, lastMarketplaceInstall,
    benchmarkRuns, selectedBenchmark, benchmarkType, benchmarkRunning, benchmarkError,
    executeBenchmark, openBenchmark, changeBenchmarkType, refreshLlmTraces, refreshLlmGovernance, refreshMcp, refreshSkills, refreshMarketplace, refreshBenchmarks,
    changeLlmAgent, changeLlmTraceAgent, refreshLlm, activateLlmPrompt, savePrompt, runPromptAbTest,
    saveServer, setServerEnabled, discoverServer, setToolEnabled, setToolApproval, invokeTool,
    setSkillStatus, loadSkillApprovals, updateSkillApproval, runSkill, removeSkillPlugin, previewPackage, installPackage, removePackage,
  } = governance;
  const [executionMode, setExecutionMode] = useState<ExecutionMode>('workflow');
  const [goal, setGoal] = useState('分析这个项目并给出重构建议');
  const [projectPath, setProjectPath] = useState(defaultProjectPath);
  const [maxFiles, setMaxFiles] = useState(100);
  const [requireReview, setRequireReview] = useState(true);
  const [running, setRunning] = useState(false);
  const [reviewComment, setReviewComment] = useState('');
  const [error, setError] = useState('');

  const [resumeSnapshots, setResumeSnapshots] = useState<ResumeSnapshot[]>([]);

  const [mermaid, setMermaid] = useState('');
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [suggestionRecords, setSuggestionRecords] = useState<SuggestionRecord[]>([]);
  const [riskLevel, setRiskLevel] = useState('low');
  const [reviewRequired, setReviewRequired] = useState(false);
  const [nextActions, setNextActions] = useState<string[]>([]);
  const [reportTab, setReportTab] = useState<ReportTab>('final');
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  const [agentOutputs, setAgentOutputs] = useState<AgentOutput[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<AgentEvent | null>(null);
  const [askQuestion, setAskQuestion] = useState('这个项目我应该先理解哪些模块？');
  const [askResult, setAskResult] = useState<AskResponse | null>(null);
  const [knowledgeQuestion, setKnowledgeQuestion] = useState('项目结构');
  const [coachAnswer, setCoachAnswer] = useState('');
  const [coachReply, setCoachReply] = useState<LearningChatResponse | null>(null);
  const [coachTurn, setCoachTurn] = useState(0);
  const [focusPickerOpen, setFocusPickerOpen] = useState(false);
  const [focusFiles, setFocusFiles] = useState<string[]>([]);
  const [focusLoading, setFocusLoading] = useState(false);
  const [focusError, setFocusError] = useState('');

  const canvasRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<{ id: string; dx: number; dy: number } | null>(null);
  const panRef = useRef<{ x: number; y: number; scrollLeft: number; scrollTop: number } | null>(null);

  const selectedNode = nodes.find((node) => node.id === selectedNodeId);
  const latestTaskId = useMemo(() => {
    const item = [...events].reverse().find((event) => event.task_id);
    return item?.task_id ?? selectedTaskId;
  }, [events, selectedTaskId]);
  const latestStatus = [...events].reverse().find((event) => event.status)?.status ?? 'idle';
  const visibleToolCalls = useMemo(
    () => (toolCalls.length ? toolCalls : deriveToolCalls(events)),
    [toolCalls, events],
  );
  const visibleAgentOutputs = useMemo(
    () => (agentOutputs.length ? agentOutputs : deriveAgentOutputs(events)),
    [agentOutputs, events],
  );
  const taskNeedsReview =
    latestStatus === 'waiting_review' || tasks.find((task) => task.task_id === latestTaskId)?.status === 'waiting_review';

  const nodeStatus = useMemo(() => {
    const status: Record<string, NodeStatus> = {};
    for (const node of nodes) status[node.id] = 'idle';
    for (const event of events) {
      const nodeId = String(event.data?.node_id ?? event.node ?? '');
      if (nodeId && status[nodeId] !== undefined && event.status) status[nodeId] = event.status as NodeStatus;
    }
    return status;
  }, [events, nodes]);

  const canvasSize = useMemo(() => {
    const maxX = Math.max(960, ...nodes.map((node) => node.x + 260));
    const maxY = Math.max(460, ...nodes.map((node) => node.y + 150));
    return { width: maxX, height: maxY };
  }, [nodes]);
  const focusModules = useMemo(() => deriveModules(focusFiles), [focusFiles]);

  useEffect(() => {
    refreshTasks().catch(() => undefined);
    refreshWorkflows().catch(() => undefined);
    refreshLearningPlans().catch(() => undefined);
    refreshLlmTraces().catch(() => undefined);
    refreshLlmGovernance().catch(() => undefined);
    refreshMcp('real_filesystem').catch(() => undefined);
    refreshSkills().catch(() => undefined);
    refreshMarketplace().catch(() => undefined);
    refreshBenchmarks('mcp').catch(() => undefined);
    refreshMemories().catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!['reports', 'chat', 'history'].includes(activeView) || selectedTaskId || !tasks.length) return;
    loadTaskContext(tasks[0].task_id).catch(() => undefined);
  }, [activeView, selectedTaskId, tasks]);

  async function handleMemoryConfirm(memoryId: string) {
    await confirmMemoryCandidate(memoryId);
  }

  async function handleMemoryReject(memoryId: string) {
    await rejectMemoryCandidate(memoryId);
  }

  async function handleMemoryDelete(memoryId: string) {
    await removeMemoryCandidate(memoryId);
  }

  function handleNavigate(view: ViewKey) {
    setActiveView(view);
    if (view === 'workflow' || view === 'skills' || view === 'marketplace') refreshSkills(selectedSkillCode).catch(() => undefined);
    if (view === 'marketplace') refreshMarketplace().catch(() => undefined);
  }

  async function handleSkillEnabled(skillCode: string, enabled: boolean) {
    await setSkillStatus(skillCode, enabled);
  }

  async function handleSkillApproval(skillCode: string, agentCode: string, allowed: boolean, reason: string) {
    await updateSkillApproval(skillCode, agentCode, allowed, reason);
  }

  async function handleExecuteSkill(skillCode: string, agentCode: string, input: Record<string, unknown>) {
    return runSkill({ skill_code: skillCode, agent_code: agentCode, input, task_id: latestTaskId || undefined });
  }

  function handleAddSkillToWorkflow(skill: SkillRecord) {
    const id = `skill_${Date.now()}`;
    const previous = nodes[nodes.length - 1];
    const nextNode: WorkflowNode = {
      id,
      type: 'skill',
      name: skill.name,
      x: previous ? previous.x + 220 : 80,
      y: previous ? previous.y : 120,
      config: {
        skill_code: skill.code,
        agent_code: 'skill_console',
        input: skill.default_input ?? {},
      },
    };
    setNodes((items) => [...items, nextNode]);
    if (previous) setEdges((items) => [...items, { source: previous.id, target: id }]);
    setSelectedNodeId(id);
    setActiveView('workflow');
  }

  function handleOpenMarketplaceSkill(skillCode: string) {
    setSelectedSkillCode(skillCode);
    refreshSkills(skillCode).catch(() => undefined);
    setActiveView('skills');
  }

  async function handleApproveAndTestMarketplaceSkill(skillCode: string) {
    const skill = skills.find((item) => item.code === skillCode);
    if (!skill) throw new Error(`Skill not found: ${skillCode}`);
    await updateSkillApproval(skillCode, 'skill_console', true, 'Approved from Marketplace install result.');
    await runSkill({
      skill_code: skillCode,
      agent_code: 'skill_console',
      input: skill.default_input ?? {},
      task_id: latestTaskId || undefined,
    });
    setSelectedSkillCode(skillCode);
    await refreshSkills(skillCode);
    setActiveView('skills');
  }

  async function handleCreateMarketplaceSkillWorkflow(skillCode: string) {
    const skill = skills.find((item) => item.code === skillCode);
    if (!skill) throw new Error(`Skill not found: ${skillCode}`);
    const id = `skill_${Date.now()}`;
    setNodes([
      {
        id,
        type: 'skill',
        name: skill.name,
        x: 120,
        y: 140,
        config: {
          skill_code: skill.code,
          agent_code: 'workflow_runner',
          input: skill.default_input ?? {},
        },
      },
    ]);
    setEdges([]);
    setSelectedNodeId(id);
    setActiveView('workflow');
    await refreshSkills(skillCode);
  }

  async function handlePreviewMarketplace(sourceUrl: string) {
    return previewPackage(sourceUrl);
  }

  async function handleInstallMarketplace(sourceUrl: string) {
    const install = await installPackage(sourceUrl);
    await refreshWorkflows();
    return install;
  }

  async function handleUninstallMarketplace(packageId: string) {
    return removePackage(packageId);
  }

  async function handleUninstallSkillPlugin(pluginId: string) {
    return removeSkillPlugin(pluginId);
  }

  async function handleRunBenchmark(payload: { name: string; agent_code: string; iterations: number; cases: BenchmarkCase[] }) {
    return executeBenchmark(payload);
  }

  async function handleOpenBenchmark(runId: string) {
    await openBenchmark(runId);
  }

  async function handleBenchmarkTypeChange(nextType: BenchmarkType) {
    await changeBenchmarkType(nextType);
  }

  function consumeTaskPayload(payload: AgentEvent | Record<string, unknown>) {
    const eventType = String((payload as { type?: unknown }).type ?? '');
    if (eventType === 'task_result') {
      const result = payload as TaskResultPayload;
      setSelectedTaskId(result.task_id);
      setFinalReport(result.final_report ?? '');
      setMermaid(result.mermaid ?? '');
      setSuggestions(result.suggestions ?? []);
      setSuggestionRecords(result.suggestion_records ?? []);
      setRiskLevel(result.risk_level ?? result.governance?.risk_level ?? 'low');
      setReviewRequired(Boolean(result.review_required ?? result.governance?.review_required ?? result.human_review_required));
      setNextActions(result.next_actions ?? result.governance?.next_actions ?? []);
      setToolCalls(result.tool_calls ?? []);
      setAgentOutputs(result.agent_outputs ?? []);
      setWorkflowValidation(result.validation ?? null);
      if (result.planned_workflow) {
        setNodes(normalizeNodes(result.planned_workflow.nodes));
        setEdges(result.planned_workflow.edges ?? []);
        setWorkflowName('Planner Generated Workflow');
        setWorkflowDescription('Generated from task goal by Planner mode.');
      }
    } else if (eventType === 'error') {
      setError(String((payload as { content?: unknown }).content ?? '任务执行失败'));
    } else if (eventType !== 'complete') {
      setEvents((prev) => [...prev, payload as AgentEvent]);
    }
  }

  function resetRunOutput() {
    setRunning(true);
    setError('');
    setEvents([]);
    setFinalReport('');
    setMermaid('');
    setSuggestions([]);
    setSuggestionRecords([]);
    setRiskLevel('low');
    setReviewRequired(false);
    setNextActions([]);
    setToolCalls([]);
    setAgentOutputs([]);
    setSelectedEvent(null);
    setWorkflowValidation(null);
    setResumeSnapshots([]);
  }

  async function runFollowUpTask({
    mode,
    nextGoal,
    nextProjectPath = projectPath,
    nextMaxFiles = maxFiles,
    nextWorkflowName,
    nextNodes = [],
    nextEdges = [],
  }: {
    mode: ExecutionMode;
    nextGoal: string;
    nextProjectPath?: string;
    nextMaxFiles?: number;
    nextWorkflowName: string;
    nextNodes?: WorkflowNode[];
    nextEdges?: WorkflowEdge[];
  }) {
    resetRunOutput();
    setGoal(nextGoal);
    setProjectPath(nextProjectPath);
    setMaxFiles(nextMaxFiles);
    setExecutionMode(mode);
    setWorkflowName(nextWorkflowName);
    if (mode === 'workflow') {
      setNodes(nextNodes);
      setEdges(nextEdges);
      setWorkflowDescription('Generated from human review follow-up action.');
    }
    setActiveView('run');
    try {
      const runner = mode === 'collaboration' ? runCollaborationTaskStream : runTaskStream;
      const useCanvas = mode === 'workflow';
      await runner(
        {
          goal: nextGoal,
          project_path: nextProjectPath,
          max_files: nextMaxFiles,
          require_human_review: requireReview,
          execution_mode: mode,
          workflow_name: nextWorkflowName,
          input_text: nextGoal,
          nodes: useCanvas ? nextNodes : [],
          edges: useCanvas ? nextEdges : [],
        },
        consumeTaskPayload,
      );
      await refreshTasks();
      await refreshLlmTraces();
      await refreshLlmGovernance();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setRunning(false);
    }
  }

  async function handleRunTask(event: FormEvent) {
    event.preventDefault();
    if (executionMode === 'workflow') {
      const approvalsForRun = await loadSkillApprovals();
      const blockedSkills = nodes.filter((node) => {
        if (node.type !== 'skill') return false;
        const skillCode = String(node.config.skill_code ?? '');
        const agentCode = String(node.config.agent_code ?? 'workflow_runner');
        return !approvalsForRun.some((approval) => approval.skill_code === skillCode && approval.agent_code === agentCode && approval.allowed);
      });
      if (blockedSkills.length) {
        setError(`Workflow 存在未审批的 Skill 节点：${blockedSkills.map((node) => `${node.name}(${String(node.config.skill_code ?? '')}/${String(node.config.agent_code ?? 'workflow_runner')})`).join(', ')}。Workflow 只认 skill_code + workflow_runner 的审批记录。`);
        setActiveView('workflow');
        return;
      }
    }
    await runFollowUpTask({
      mode: executionMode,
      nextGoal: goal,
      nextProjectPath: projectPath,
      nextMaxFiles: maxFiles,
      nextWorkflowName: workflowName,
      nextNodes: executionMode === 'workflow' ? nodes : [],
      nextEdges: executionMode === 'workflow' ? edges : [],
    });
  }

  async function openTask(taskId: string) {
    setSelectedTaskId(taskId);
    await restoreTaskContext(taskId);
    setActiveView('history');
  }

  async function loadTaskContext(taskId: string) {
    setSelectedTaskId(taskId);
    await restoreTaskContext(taskId);
  }

  async function restoreTaskContext(taskId: string) {
    setSuggestions([]);
    setSuggestionRecords([]);
    setRiskLevel('low');
    setReviewRequired(false);
    setNextActions([]);
    setToolCalls([]);
    setAgentOutputs([]);
    setSelectedEvent(null);
    setResumeSnapshots([]);
    const [taskEvents, taskDetail] = await Promise.all([getTaskEvents(taskId), getTaskDetail(taskId)]);
    const taskResult = extractTaskResultArtifact(taskDetail.artifacts);
    const resumeRecords = extractResumeSnapshots(taskDetail.artifacts);
    setEvents(taskEvents);
    setFinalReport(taskResult.final_report ?? taskDetail.task.final_report ?? '');
    setMermaid(taskResult.mermaid ?? '');
    setSuggestions(taskResult.suggestions ?? []);
    setSuggestionRecords(taskResult.suggestion_records ?? []);
    setRiskLevel(taskResult.risk_level ?? taskResult.governance?.risk_level ?? 'low');
    setReviewRequired(Boolean(taskResult.review_required ?? taskResult.governance?.review_required ?? taskResult.human_review_required));
    setNextActions(taskResult.next_actions ?? taskResult.governance?.next_actions ?? []);
    setToolCalls(taskResult.tool_calls ?? []);
    setAgentOutputs(taskResult.agent_outputs ?? []);
    setResumeSnapshots(resumeRecords);
  }

  async function handleReview(action: 'approve' | 'reject' | 'revise') {
    if (!latestTaskId) return;
    try {
      await reviewTask(latestTaskId, action, reviewComment);
      await refreshTasks();
      await loadTaskContext(latestTaskId);
      await refreshLlmTraces();
      await refreshLlmGovernance();
      setReviewComment('');
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    }
  }

  function applyGuide(nextMode: ExecutionMode, prompt: string) {
    setExecutionMode(nextMode);
    setGoal(prompt);
  }

  function handleChatModeChange(mode: ChatMode) {
    setChatMode(mode);
    setChatSources([]);
    if (mode === 'coach') refreshLearningPlans().catch(() => undefined);
    if (mode === 'knowledge') handleQueryKnowledge().catch(() => undefined);
  }

  function currentTaskGoal() {
    return tasks.find((task) => task.task_id === latestTaskId)?.goal || goal;
  }

  async function openFocusPicker() {
    setFocusPickerOpen(true);
    setFocusLoading(true);
    setFocusError('');
    try {
      const result = await listProjectFiles(projectPath, Math.min(2000, Math.max(300, maxFiles * 4)));
      setFocusFiles(result.files);
    } catch (exc) {
      setFocusError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setFocusLoading(false);
    }
  }

  async function startDeepAnalysis() {
    const baseGoal = currentTaskGoal();
    const nextGoal = [
      `深入分析：${baseGoal}`,
      `来源任务：${latestTaskId}`,
      reviewComment ? `人工审核意见：${reviewComment}` : '',
      '请通过多 Agent 协作重新分析项目结构、代码风险、知识沉淀点，并给出更具体的治理建议。',
    ].filter(Boolean).join('\n');
    await applyReviewAction(latestTaskId, 'rerun_analysis', reviewComment, { source_task_id: latestTaskId, mode: 'collaboration' });
    await refreshTasks();
    await runFollowUpTask({
      mode: 'collaboration',
      nextGoal,
      nextProjectPath: projectPath,
      nextMaxFiles: maxFiles,
      nextWorkflowName: 'Deep Collaboration Review',
    });
  }

  async function startLearningTask() {
    const baseGoal = currentTaskGoal();
    const result = await applyReviewAction(latestTaskId, 'learning_task', reviewComment, { source_task_id: latestTaskId });
    const plan = await createTaskLearningPlan(latestTaskId, {
      topic: `任务复盘：${baseGoal}`,
      level: 'beginner',
      days: 7,
      goal: baseGoal,
      comment: reviewComment,
    });
    await refreshTasks();
    await refreshLearningPlans();
    await loadTaskContext(latestTaskId);
    setChatMode('coach');
    setActiveView('chat');
    const prompt = [
      `基于当前任务生成学习陪练：${baseGoal}`,
      `任务 ID：${latestTaskId}`,
      reviewComment ? `审核意见：${reviewComment}` : '',
      '请先给我一个学习目标，然后连续追问我对项目结构、风险和 LangGraph 工作流的理解。',
    ].filter(Boolean).join('\n');
    setChatInput('我先回答：');
    setChatMessages((prev) => [...prev, { role: 'user', content: prompt }]);
    const nextTurn = coachTurn + 1;
    setCoachTurn(nextTurn);
    const coach = await chatLearningCoach({
      topic: `任务复盘：${baseGoal}`,
      level: 'beginner',
      question: prompt,
      answer: reviewComment || baseGoal,
      task_id: latestTaskId,
      turn: nextTurn,
    });
    setCoachReply(coach);
    setChatMessages((prev) => [
      ...prev,
      {
        role: 'assistant',
        content: `${result.message}\n\n已生成学习计划：${plan.topic}（${plan.status}）\n\n${coach.reply}\n\n${coach.next_questions.map((item) => `Q: ${item}`).join('\n')}`,
        source: coach.answer_source,
        day: coach.day,
        theme: coach.theme,
      },
    ]);
  }

  async function handleLearningPlanStatus(planId: string, status: LearningPlanRecord['status']) {
    const updated = await setPlanStatus(planId, status);
    await refreshLearningPlans();
    if (updated.task_id === latestTaskId) await loadTaskContext(latestTaskId);
    setChatMode('coach');
    setActiveView('chat');
    setChatMessages((prev) => [
      ...prev,
      { role: 'assistant', content: `学习计划状态已更新：${updated.topic} -> ${updated.status}` },
    ]);
  }

  async function handleFocusTarget(kind: FocusKind, value: string) {
    if (!latestTaskId || !value) return;
    setFocusPickerOpen(false);
    const baseGoal = currentTaskGoal();
    const payload = kind === 'module' ? { module: value } : { file: value };
    await applyReviewAction(latestTaskId, 'focus_module', reviewComment, { ...payload, source_task_id: latestTaskId });
    await refreshTasks();
    if (kind === 'module') {
      const scopedPath = joinProjectPath(projectPath, value);
      await runFollowUpTask({
        mode: 'planner',
        nextGoal: [
          `聚焦模块分析：${value}`,
          `原始任务：${baseGoal}`,
          reviewComment ? `人工审核意见：${reviewComment}` : '',
          '只围绕该模块分析职责边界、关键文件、风险点和重构建议。',
        ].filter(Boolean).join('\n'),
        nextProjectPath: scopedPath,
        nextMaxFiles: maxFiles,
        nextWorkflowName: `Focus Module - ${value}`,
      });
      return;
    }

    const fileNodes = buildFocusedFileWorkflow(value);
    const fileEdges = [
      { source: 'plan_focus', target: 'review_focus_file' },
      { source: 'review_focus_file', target: 'report_focus_file' },
    ];
    await runFollowUpTask({
      mode: 'workflow',
      nextGoal: [
        `聚焦文件分析：${value}`,
        `原始任务：${baseGoal}`,
        reviewComment ? `人工审核意见：${reviewComment}` : '',
        '只读取并分析这个文件，输出职责、风险、依赖线索和后续追问。',
      ].filter(Boolean).join('\n'),
      nextProjectPath: projectPath,
      nextMaxFiles: 1,
      nextWorkflowName: `Focus File - ${value}`,
      nextNodes: fileNodes,
      nextEdges: fileEdges,
    });
  }

  async function handleReviewAction(action: string, payload: Record<string, unknown> = {}) {
    if (!latestTaskId) return;
    if (action === 'rerun_analysis') {
      await startDeepAnalysis();
      setReviewComment('');
      return;
    }
    if (action === 'focus_module') {
      await openFocusPicker();
      return;
    }
    if (action === 'learning_task') {
      await startLearningTask();
      setReviewComment('');
      return;
    }
    const result = await applyReviewAction(latestTaskId, action, reviewComment, payload);
    await refreshTasks();
    await loadTaskContext(latestTaskId);
    if (action === 'save_knowledge') {
      const query = reviewComment || '人工审核';
      const [docs, results] = await Promise.all([
        listKnowledgeDocuments('project-memory'),
        queryKnowledge('project-memory', query, 5),
      ]);
      setKnowledgeDocs(docs);
      setKnowledgeResults(results);
      setKnowledgeQuestion(query);
      setChatMode('knowledge');
      setActiveView('chat');
      setChatMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `${result.message}\n\nproject-memory 当前有 ${docs.length} 条文档记录。` },
      ]);
    }
    setReviewComment('');
  }

  async function handleAskTask() {
    if (!latestTaskId || !askQuestion.trim()) return;
    setAskResult(await askTask(latestTaskId, askQuestion, 'project-memory'));
  }

  async function handleQueryKnowledge() {
    const [docs, results] = await Promise.all([
      listKnowledgeDocuments('project-memory'),
      queryKnowledge('project-memory', knowledgeQuestion || goal, 5),
    ]);
    setKnowledgeDocs(docs);
    setKnowledgeResults(results);
    setChatSources(results);
  }

  async function handleSaveKnowledgeNote() {
    if (!knowledgeNote.trim()) return;
    await addKnowledgeNote('project-memory', `note/${Date.now()}`, knowledgeNote);
    setKnowledgeNote('');
    await handleQueryKnowledge();
    setChatMode('knowledge');
    setActiveView('chat');
  }

  async function handleCoachChat() {
    const nextTurn = coachTurn + 1;
    setCoachTurn(nextTurn);
    setCoachReply(
      await chatLearningCoach({
        topic: 'Jaycode 项目理解',
        level: 'beginner',
        question: '请根据我的回答继续陪练',
        answer: coachAnswer,
        task_id: latestTaskId || undefined,
        turn: nextTurn,
      }),
    );
  }

  async function handleSendChat() {
    const question = chatInput.trim();
    if (!question) return;
    setChatMessages((prev) => [...prev, { role: 'user', content: question }]);
    setChatInput('');
    try {
      await extractMemoryCandidates({ text: question, source_ref: `chat/${chatMode}` });
      await refreshMemories();
      if (chatMode === 'task') {
        if (!latestTaskId) {
          setChatMessages((prev) => [...prev, { role: 'assistant', content: '请先运行或选择一个历史任务，再进行任务追问。' }]);
          return;
        }
        const result = await askTask(latestTaskId, question, 'project-memory');
        setChatSources(result.sources ?? []);
        setChatMessages((prev) => [...prev, { role: 'assistant', content: result.answer, source: result.answer_source }]);
      } else if (chatMode === 'knowledge') {
        const results = await queryKnowledge('project-memory', question, 6);
        setChatSources(results);
        const answer = results.length
          ? `在 project-memory 中找到 ${results.length} 条相关知识：\n\n${results.map((item) => `- ${item.path}: ${firstLine(item.content)}`).join('\n')}`
          : 'project-memory 中暂时没有命中内容。你可以先在报告页保存知识笔记，或运行 RAG Processor。';
        setChatMessages((prev) => [...prev, { role: 'assistant', content: answer }]);
      } else {
        const nextTurn = coachTurn + 1;
        setCoachTurn(nextTurn);
        const result = await chatLearningCoach({
          topic: 'Jaycode 项目理解',
          level: 'beginner',
          question,
          answer: question,
          task_id: latestTaskId || undefined,
          turn: nextTurn,
        });
        setChatMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: `${result.reply}\n\n${result.next_questions.map((item) => `Q: ${item}`).join('\n')}`,
            source: result.answer_source,
            day: result.day,
            theme: result.theme,
          },
        ]);
      }
      await refreshMemories();
    } catch (exc) {
      setChatMessages((prev) => [...prev, { role: 'assistant', content: exc instanceof Error ? exc.message : String(exc) }]);
    }
  }

  async function handleSaveWorkflow() {
    await persistWorkflow();
  }

  async function handleValidateWorkflow() {
    await checkWorkflow();
  }

  function loadWorkflow(workflow: WorkflowRecord) {
    setWorkflowId(workflow.workflow_id);
    setWorkflowName(workflow.name);
    setWorkflowDescription(workflow.description ?? '');
    setNodes(normalizeNodes(workflow.nodes));
    setEdges(workflow.edges ?? []);
    setSelectedNodeId(workflow.nodes[0]?.id ?? '');
    setSelectedEdgeKey('');
    setWorkflowValidation(null);
    setExecutionMode('workflow');
    setActiveView('workflow');
  }

  function handleDrop(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    const raw = event.dataTransfer.getData(dragPayloadMime);
    if (!raw || !canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const item = JSON.parse(raw) as { type: string; name: string; config?: Record<string, unknown> };
    const id = `${item.type}_${Date.now()}`;
    const nextNode: WorkflowNode = {
      id,
      type: item.type,
      name: item.name,
      x: canvasRef.current.scrollLeft + event.clientX - rect.left - 82,
      y: canvasRef.current.scrollTop + event.clientY - rect.top - 28,
      config: item.config ?? {},
    };
    setNodes((prev) => [...prev, nextNode]);
    setSelectedNodeId(id);
    setSelectedEdgeKey('');
  }

  function startMove(event: PointerEvent<HTMLDivElement>, node: WorkflowNode) {
    setSelectedNodeId(node.id);
    setSelectedEdgeKey('');
    const rect = event.currentTarget.getBoundingClientRect();
    dragRef.current = { id: node.id, dx: event.clientX - rect.left, dy: event.clientY - rect.top };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function moveNode(event: PointerEvent<HTMLDivElement>) {
    if (!dragRef.current || !canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const { id, dx, dy } = dragRef.current;
    setNodes((prev) =>
      prev.map((node) =>
        node.id === id
          ? {
              ...node,
              x: Math.max(8, Math.min(canvasSize.width - 180, canvasRef.current!.scrollLeft + event.clientX - rect.left - dx)),
              y: Math.max(8, Math.min(canvasSize.height - 78, canvasRef.current!.scrollTop + event.clientY - rect.top - dy)),
            }
          : node,
      ),
    );
  }

  function startCanvasPan(event: PointerEvent<HTMLDivElement>) {
    const target = event.target as HTMLElement;
    if (target.closest('.flow-node') || target.closest('button')) return;
    panRef.current = {
      x: event.clientX,
      y: event.clientY,
      scrollLeft: event.currentTarget.scrollLeft,
      scrollTop: event.currentTarget.scrollTop,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function panCanvas(event: PointerEvent<HTMLDivElement>) {
    if (!panRef.current || !canvasRef.current) return;
    canvasRef.current.scrollLeft = panRef.current.scrollLeft - (event.clientX - panRef.current.x);
    canvasRef.current.scrollTop = panRef.current.scrollTop - (event.clientY - panRef.current.y);
  }

  function endPointer() {
    dragRef.current = null;
    panRef.current = null;
  }

  function handleCanvasPointerMove(event: PointerEvent<HTMLDivElement>) {
    moveNode(event);
    panCanvas(event);
  }

  function toggleConnect(nodeId: string) {
    if (!connectFrom) {
      setConnectFrom(nodeId);
      return;
    }
    if (connectFrom !== nodeId) {
      setEdges((prev) => {
        const exists = prev.some((edge) => edge.source === connectFrom && edge.target === nodeId);
        return exists ? prev : [...prev, { source: connectFrom, target: nodeId }];
      });
    }
    setConnectFrom(null);
  }

  function updateSelectedNode(patch: Partial<WorkflowNode>) {
    setNodes((prev) => prev.map((node) => (node.id === selectedNodeId ? { ...node, ...patch } : node)));
  }

  function updateSelectedConfig(key: string, value: unknown) {
    setNodes((prev) =>
      prev.map((node) => (node.id === selectedNodeId ? { ...node, config: { ...node.config, [key]: value } } : node)),
    );
  }

  function updateEdge(edgeKey: string, patch: Partial<WorkflowEdge>) {
    setEdges((prev) => prev.map((edge) => (edgeKeyFor(edge) === edgeKey ? { ...edge, ...patch } : edge)));
  }

  function deleteEdge(edgeKey: string) {
    setEdges((prev) => prev.filter((edge) => edgeKeyFor(edge) !== edgeKey));
    if (selectedEdgeKey === edgeKey) setSelectedEdgeKey('');
  }

  function deleteSelectedNode() {
    setNodes((prev) => prev.filter((node) => node.id !== selectedNodeId));
    setEdges((prev) => prev.filter((edge) => edge.source !== selectedNodeId && edge.target !== selectedNodeId));
    setSelectedNodeId('');
    setSelectedEdgeKey('');
  }

  const workflowCanvas = (
    <WorkflowCanvas
      canvasRef={canvasRef}
      canvasSize={canvasSize}
      connectFrom={connectFrom}
      edges={edges}
      nodes={nodes}
      nodeStatus={nodeStatus}
      selectedNodeId={selectedNodeId}
      selectedEdgeKey={selectedEdgeKey}
      onCanvasPointerMove={handleCanvasPointerMove}
      onDrop={handleDrop}
      onEndPointer={endPointer}
      onStartCanvasPan={startCanvasPan}
      onStartMove={startMove}
      onSelectEdge={(edge) => {
        setSelectedEdgeKey(edgeKeyFor(edge));
        setSelectedNodeId('');
      }}
      onToggleConnect={toggleConnect}
    />
  );

  return (
    <div className="app-shell">
      <aside className="side-nav">
        <div className="brand-mark">D</div>
        <nav>
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.view}
                className={activeView === item.view ? 'active' : ''}
                onClick={() => handleNavigate(item.view)}
                title={item.label}
              >
                <Icon size={22} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>

      <main className="app-main">
        <header className="topbar">
          <div>
            <h1>Jaycode</h1>
            <span>可视化 Workflow 任务工作台</span>
          </div>
          <div className="topbar-actions">
            <div className={`status-pill ${latestStatus}`}>{running ? 'running' : latestStatus}</div>
          </div>
        </header>

        <ActivePage>
        {activeView === 'run' ? (
          <section className="page-grid run-page">
            <div className="panel run-panel">
              <PanelTitle icon={<Play size={17} />} title="任务入口" />
              <ModeTabs executionMode={executionMode} onChange={setExecutionMode} />
              <ModeHint executionMode={executionMode} />
              <div className="start-guide">
                <strong>先做这三步</strong>
                <ol>
                  <li>填目标和项目路径</li>
                  <li>选运行模式</li>
                  <li>点击开始执行</li>
                </ol>
              </div>
              <AnalysisGuide onApply={applyGuide} />
              <RunForm
                goal={goal}
                projectPath={projectPath}
                maxFiles={maxFiles}
                requireReview={requireReview}
                running={running}
                submitLabel={modeHelp[executionMode].button}
                onGoalChange={setGoal}
                onProjectPathChange={setProjectPath}
                onMaxFilesChange={setMaxFiles}
                onRequireReviewChange={setRequireReview}
                onSubmit={handleRunTask}
              />
              {error ? <p className="error-text">{error}</p> : null}
            </div>

            <div className="panel timeline-large">
              <PanelTitle icon={<Activity size={17} />} title="执行过程" />
              <Timeline events={events} selectedEventId={selectedEvent?.event_id} onSelect={setSelectedEvent} />
            </div>

            <div className="panel state-panel">
              <PanelTitle icon={<Activity size={17} />} title="结果总览" />
              <StateSummary latestTaskId={latestTaskId} latestStatus={latestStatus} workflowName={workflowName} />
              {taskNeedsReview && latestTaskId ? (
                <ReviewBox
                  comment={reviewComment}
                  onCommentChange={setReviewComment}
                  onReview={handleReview}
                  onReviewAction={handleReviewAction}
                />
              ) : null}
              <ResumePanel snapshots={resumeSnapshots} events={events} />
              <EventDetail event={selectedEvent} />
              <OutputList title="工具调用" empty="暂无工具调用" items={visibleToolCalls.map(formatToolCall)} />
              <OutputList title="Agent 输出" empty="暂无 Agent 输出" items={visibleAgentOutputs.map(formatAgentOutput)} />
            </div>
          </section>
        ) : null}

        {activeView === 'workflow' ? (
          <section className="page-grid workflow-page">
            <div className="panel workflow-sidebar">
              <PanelTitle icon={<Workflow size={17} />} title="Workflow" />
              <div className="workflow-fields">
                <input value={workflowName} onChange={(event) => setWorkflowName(event.target.value)} />
                <FieldHelp>Workflow 名称会写入任务记录和历史模板，用来区分不同编排方案。</FieldHelp>
                <textarea value={workflowDescription} onChange={(event) => setWorkflowDescription(event.target.value)} />
                <FieldHelp>描述当前流程的用途、节点顺序和适用场景，方便后续复用。</FieldHelp>
                <button className="secondary" onClick={handleSaveWorkflow}>
                  <Save size={15} />
                  保存 Workflow
                </button>
                <button className="secondary" onClick={handleValidateWorkflow}>
                  <Check size={15} />
                  校验 Workflow
                </button>
              </div>
              <WorkflowValidationView validation={workflowValidation} />
              <PanelTitle title="节点库" />
              <Palette />
              <PanelTitle title="已保存" />
              <SavedWorkflows workflows={savedWorkflows} onLoad={loadWorkflow} onRefresh={refreshWorkflows} />
            </div>

            <div className="panel canvas-panel">
              <PanelTitle icon={<Workflow size={17} />} title="图形化流程" />
              {workflowCanvas}
            </div>

            <div className="panel config-panel">
              <NodeConfig
                node={selectedNode}
                approvals={skillApprovals}
                onNodeChange={updateSelectedNode}
                onConfigChange={updateSelectedConfig}
                onApproveSkill={async (skillCode, agentCode) => {
                  await handleSkillApproval(skillCode, agentCode, true, 'Approved from Workflow node config.');
                }}
                onDelete={deleteSelectedNode}
              />
              <EdgeConfig
                edge={edges.find((edge) => edgeKeyFor(edge) === selectedEdgeKey)}
                nodes={nodes}
                onChange={(patch) => selectedEdgeKey && updateEdge(selectedEdgeKey, patch)}
                onDelete={() => selectedEdgeKey && deleteEdge(selectedEdgeKey)}
              />
            </div>
          </section>
        ) : null}

        {activeView === 'reports' ? (
          <ReportsWorkspacePage
            finalReport={finalReport}
            mermaid={mermaid}
            nodes={nodes}
            edges={edges}
            riskLevel={riskLevel}
            reviewRequired={reviewRequired}
            nextActions={nextActions}
            suggestions={suggestions}
            suggestionRecords={suggestionRecords}
            knowledgeDocumentCount={knowledgeDocs.length}
            onOpenKnowledge={() => { setChatMode('knowledge'); setActiveView('chat'); handleQueryKnowledge(); }}
          />
        ) : null}
        {activeView === 'chat' ? (
          <ChatConsolePage
            chatInput={chatInput}
            chatMessages={chatMessages}
            chatMode={chatMode}
            chatSources={chatSources}
            knowledgeDocs={knowledgeDocs}
            knowledgeNote={knowledgeNote}
            memories={memories}
            learningPlans={learningPlans}
            latestTaskId={latestTaskId}
            tasks={tasks}
            selectedTaskId={selectedTaskId}
            onChatInputChange={setChatInput}
            onChatModeChange={handleChatModeChange}
            onKnowledgeNoteChange={setKnowledgeNote}
            onMemoryConfirm={handleMemoryConfirm}
            onMemoryDelete={handleMemoryDelete}
            onMemoryReject={handleMemoryReject}
            onLearningPlanStatus={handleLearningPlanStatus}
            onOpenTask={loadTaskContext}
            onRefreshTasks={refreshTasks}
            onSaveKnowledgeNote={handleSaveKnowledgeNote}
            onSend={handleSendChat}
          />
        ) : null}

        {activeView === 'llm' ? (
          <LlmConsolePage
            prompts={llmPrompts}
            usage={llmUsage}
            traces={llmTraces}
            traceAgent={llmTraceAgent}
            agentFilter={llmAgentFilter}
            onAgentFilterChange={changeLlmAgent}
            onTraceAgentChange={changeLlmTraceAgent}
            onActivatePrompt={activateLlmPrompt}
            onSavePrompt={savePrompt}
            onRunAbTest={runPromptAbTest}
            onRefresh={refreshLlm}
          />
        ) : null}

        {activeView === 'mcp' ? (
          <McpConsolePage
            projectPath={projectPath}
            status={mcpStatus}
            servers={mcpServers}
            tools={mcpTools}
            logs={mcpLogs}
            onRefresh={refreshMcp}
            onSaveServer={saveServer}
            onServerEnabled={setServerEnabled}
            onDiscover={discoverServer}
            onToolEnabled={setToolEnabled}
            onApproveTool={setToolApproval}
            onCallTool={invokeTool}
          />
        ) : null}

        {activeView === 'skills' ? (
          <SkillsConsolePage
            plugins={skillPlugins}
            skills={skills}
            approvals={skillApprovals}
            logs={skillLogs}
            selectedSkillCode={selectedSkillCode}
            projectPath={projectPath}
            onSelectSkill={(code) => {
              setSelectedSkillCode(code);
              refreshSkills(code).catch(() => undefined);
            }}
            onRefresh={() => refreshSkills(selectedSkillCode)}
            onSkillEnabled={handleSkillEnabled}
            onSkillApproval={handleSkillApproval}
            onExecuteSkill={handleExecuteSkill}
            onAddToWorkflow={handleAddSkillToWorkflow}
            onUninstallPlugin={handleUninstallSkillPlugin}
          />
        ) : null}

        {activeView === 'marketplace' ? (
          <MarketplacePage
            catalog={marketplaceCatalog}
            installs={marketplaceInstalls}
            preview={marketplacePreview}
            lastInstall={lastMarketplaceInstall}
            onRefresh={() => refreshMarketplace()}
            onPreview={handlePreviewMarketplace}
            onInstall={handleInstallMarketplace}
            onUninstall={handleUninstallMarketplace}
            onOpenSkill={handleOpenMarketplaceSkill}
            onApproveAndTestSkill={handleApproveAndTestMarketplaceSkill}
            onCreateSkillWorkflow={handleCreateMarketplaceSkillWorkflow}
          />
        ) : null}

        {activeView === 'benchmark' ? (
          <BenchmarkConsolePage
            benchmarkType={benchmarkType}
            runs={benchmarkRuns}
            selectedRun={selectedBenchmark}
            running={benchmarkRunning}
            error={benchmarkError}
            onBenchmarkTypeChange={handleBenchmarkTypeChange}
            onRun={handleRunBenchmark}
            onOpen={handleOpenBenchmark}
            onRefresh={() => refreshBenchmarks(benchmarkType)}
          />
        ) : null}

        {activeView === 'history' ? (
          <HistoryWorkspacePage tasks={tasks} selectedTaskId={selectedTaskId} events={events} finalReport={finalReport} onOpen={openTask} onRefresh={refreshTasks} />
        ) : null}

        </ActivePage>

        {focusPickerOpen ? (
          <FocusPicker
            files={focusFiles}
            loading={focusLoading}
            error={focusError}
            modules={focusModules}
            onClose={() => setFocusPickerOpen(false)}
            onSelect={handleFocusTarget}
          />
        ) : null}
      </main>
    </div>
  );
}

function ModeTabs({ executionMode, onChange }: { executionMode: ExecutionMode; onChange: (mode: ExecutionMode) => void }) {
  return <div className="mode-tabs">{modeItems.map((item) => {
    const Icon = item.icon;
    return <button key={item.mode} type="button" className={executionMode === item.mode ? 'active' : ''} onClick={() => onChange(item.mode)}><Icon size={16} />{item.label}</button>;
  })}</div>;
}

function ModeHint({ executionMode }: { executionMode: ExecutionMode }) {
  const hint = modeHelp[executionMode];
  return <div className="mode-hint"><strong>{hint.title}</strong><p>{hint.description}</p></div>;
}

function AnalysisGuide({ onApply }: { onApply: (mode: ExecutionMode, prompt: string) => void }) {
  const items: Array<{ label: string; mode: ExecutionMode; prompt: string }> = [
    { label: '项目全景理解', mode: 'collaboration', prompt: '请从项目结构、技术栈、关键模块、风险和学习路径理解这个项目。' },
    { label: '代码风险审查', mode: 'planner', prompt: '审查这个项目的代码风险、安全问题和技术债，并生成可审核的分析流程。' },
    { label: '项目知识沉淀', mode: 'planner', prompt: '加工这个项目的文档和代码知识，生成项目知识库、FAQ 和阅读建议。' },
    { label: '学习陪练路线', mode: 'agent', prompt: '我是新接手这个项目的用户，请给我项目理解路线和学习陪练建议。' },
  ];
  return (
    <div className="guide-box">
      <strong>分析向导</strong>
      <div>
        {items.map((item) => (
          <button key={item.label} type="button" onClick={() => onApply(item.mode, item.prompt)}>
            {item.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function RunForm({
  goal,
  projectPath,
  maxFiles,
  requireReview,
  running,
  submitLabel,
  onGoalChange,
  onProjectPathChange,
  onMaxFilesChange,
  onRequireReviewChange,
  onSubmit,
}: {
  goal: string;
  projectPath: string;
  maxFiles: number;
  requireReview: boolean;
  running: boolean;
  submitLabel: string;
  onGoalChange: (value: string) => void;
  onProjectPathChange: (value: string) => void;
  onMaxFilesChange: (value: number) => void;
  onRequireReviewChange: (value: boolean) => void;
  onSubmit: (event: FormEvent) => void;
}) {
  return (
    <form className="run-form" onSubmit={onSubmit}>
      <label>
        目标
        <textarea value={goal} onChange={(event) => onGoalChange(event.target.value)} />
        <FieldHelp>写清楚本次任务目标。Planner、Agent 和 Workflow 会把这段话作为核心输入。</FieldHelp>
      </label>
      <label>
        项目路径
        <input value={projectPath} onChange={(event) => onProjectPathChange(event.target.value)} />
        <FieldHelp>本地项目目录，项目分析、代码审查、文件工具和 RAG 加工都会从这里读取文件。</FieldHelp>
      </label>
      <div className="form-row">
        <label>
          文件数
          <input type="number" min={1} max={5000} value={maxFiles} onChange={(event) => onMaxFilesChange(Number(event.target.value))} />
          <FieldHelp>限制最多扫描多少个文件；数值越大越完整，但执行会更慢。</FieldHelp>
        </label>
        <label className="toggle-row">
          <input type="checkbox" checked={requireReview} onChange={(event) => onRequireReviewChange(event.target.checked)} />
          人工审核
        </label>
      </div>
      <button className="primary" disabled={running} type="submit">
        {running ? <RefreshCw className="spin" size={17} /> : <Play size={17} />}
        {running ? '执行中...' : submitLabel}
      </button>
    </form>
  );
}

function Timeline({
  events,
  selectedEventId,
  onSelect,
}: {
  events: AgentEvent[];
  selectedEventId?: string;
  onSelect?: (event: AgentEvent) => void;
}) {
  return (
    <div className="timeline">
      {events.length ? (
        events.map((event, index) => (
          <button
            type="button"
            className={`timeline-row ${selectedEventId === event.event_id ? 'selected' : ''}`}
            key={`${event.event_id ?? index}-${index}`}
            onClick={() => onSelect?.(event)}
          >
            <div className={`dot ${event.status ?? 'running'}`} />
            <div>
              <div className="event-main">
                <strong>{event.data?.node_name ? String(event.data.node_name) : event.node ?? event.type}</strong>
                <span>{event.agent ?? 'runtime'}</span>
                <em>{event.status}</em>
              </div>
              <p>{event.content}</p>
            </div>
          </button>
        ))
      ) : (
        <p className="empty-text">运行任务后，这里会显示完整执行事件。</p>
      )}
    </div>
  );
}

function EventDetail({ event }: { event: AgentEvent | null }) {
  if (!event) {
    return (
      <div className="detail-box">
        <strong>节点详情</strong>
        <p>点击执行时间线中的节点，查看该步骤的输出、状态和后续可追问方向。</p>
      </div>
    );
  }
  const output = event.data?.output;
  return (
    <div className="detail-box">
      <strong>{String(event.data?.node_name ?? event.node ?? event.type)}</strong>
      <p>{event.content}</p>
      <dl>
        <dt>Agent</dt>
        <dd>{event.agent ?? 'runtime'}</dd>
        <dt>Status</dt>
        <dd>{event.status ?? 'unknown'}</dd>
      </dl>
      {output ? <pre>{summarizeValue(output)}</pre> : null}
    </div>
  );
}

function StateSummary({ latestTaskId, latestStatus, workflowName }: { latestTaskId: string; latestStatus: string; workflowName: string }) {
  return (
    <dl className="state-summary">
      <dt>Task</dt>
      <dd>{latestTaskId || '未运行'}</dd>
      <dt>Status</dt>
      <dd>{latestStatus}</dd>
      <dt>Workflow</dt>
      <dd>{workflowName}</dd>
    </dl>
  );
}

function ResumePanel({ snapshots, events }: { snapshots: ResumeSnapshot[]; events: AgentEvent[] }) {
  const records = snapshots.length ? snapshots : deriveResumeSnapshots(events);
  if (!records.length) return null;
  return (
    <div className="resume-panel">
      <PanelTitle icon={<RefreshCw size={16} />} title="Resume 可视化" />
      {records.slice(-3).reverse().map((snapshot, index) => {
        const before = summarizeResumeState(snapshot.before_state);
        const afterEvents = snapshot.after_events ?? [];
        return (
          <div className="resume-card" key={`${snapshot.created_at ?? index}-${snapshot.resumed_from ?? 'resume'}`}>
            <dl>
              <dt>恢复节点</dt>
              <dd>{snapshot.resumed_from || '未知节点'}</dd>
              <dt>审核动作</dt>
              <dd>{snapshot.action || 'approved'}</dd>
              <dt>恢复结果</dt>
              <dd>{snapshot.status || 'completed'}</dd>
            </dl>
            <div className="resume-block">
              <strong>恢复前 state</strong>
              {before.length ? (
                <ul>
                  {before.map((item) => <li key={item}>{item}</li>)}
                </ul>
              ) : (
                <p className="empty-text">暂无 state 快照</p>
              )}
            </div>
            <div className="resume-block">
              <strong>恢复后新增事件</strong>
              {afterEvents.length ? (
                <ol>
                  {afterEvents.slice(0, 8).map((event, eventIndex) => (
                    <li key={`${event.event_id ?? eventIndex}-${eventIndex}`}>
                      <span>{event.node ?? event.type ?? 'event'}</span>
                      <em>{event.status ?? 'unknown'}</em>
                      <p>{event.content}</p>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="empty-text">暂无新增事件快照</p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function FocusPicker({
  error,
  files,
  loading,
  modules,
  onClose,
  onSelect,
}: {
  error: string;
  files: string[];
  loading: boolean;
  modules: string[];
  onClose: () => void;
  onSelect: (kind: FocusKind, value: string) => void;
}) {
  const [kind, setKind] = useState<FocusKind>('module');
  const [keyword, setKeyword] = useState('');
  const normalizedKeyword = keyword.trim().toLowerCase();
  const moduleItems = modules.filter((item) => item.toLowerCase().includes(normalizedKeyword)).slice(0, 80);
  const fileItems = files
    .filter((item) => !normalizedKeyword || item.toLowerCase().includes(normalizedKeyword))
    .slice(0, 160);
  const items = kind === 'module' ? moduleItems : fileItems;

  return (
    <div className="modal-backdrop">
      <div className="focus-modal">
        <div className="modal-title">
          <strong>选择聚焦范围</strong>
          <button className="icon-button" onClick={onClose}><X size={15} /></button>
        </div>
        <div className="focus-tabs">
          <button className={kind === 'module' ? 'active' : ''} onClick={() => setKind('module')}>模块</button>
          <button className={kind === 'file' ? 'active' : ''} onClick={() => setKind('file')}>文件</button>
        </div>
        <input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="搜索模块或文件" />
        <FieldHelp>输入模块名、目录名或文件名关键字，用来缩小聚焦分析范围。</FieldHelp>
        {loading ? <p className="empty-text">正在扫描项目文件...</p> : null}
        {error ? <p className="error-text">{error}</p> : null}
        <div className="focus-list">
          {items.map((item) => (
            <button key={`${kind}-${item}`} onClick={() => onSelect(kind, item)}>
              <span>{item}</span>
              <small>{kind === 'module' ? '只分析该模块目录' : '只读取并分析该文件'}</small>
            </button>
          ))}
          {!loading && !items.length ? <p className="empty-text">没有匹配结果</p> : null}
        </div>
      </div>
    </div>
  );
}

function ReviewBox({
  comment,
  onCommentChange,
  onReview,
  onReviewAction,
}: {
  comment: string;
  onCommentChange: (value: string) => void;
  onReview: (action: 'approve' | 'reject' | 'revise') => void;
  onReviewAction: (action: string, payload?: Record<string, unknown>) => void;
}) {
  return (
    <div className="review-box">
      <PanelTitle icon={<Check size={16} />} title="人工审核" />
      <textarea value={comment} onChange={(event) => onCommentChange(event.target.value)} placeholder="填写审核意见" />
      <FieldHelp>通过会继续暂停的 Workflow；修改/拒绝会保留你的意见到任务事件里。</FieldHelp>
      <FieldHelp>如果暂停节点开启了“执行前确认”并设置 retry_count，拒绝/修改会先消耗重试次数并重新等待确认；次数用完后才结束为拒绝。</FieldHelp>
      <div className="review-actions">
        <button onClick={() => onReview('approve')}><Check size={15} />通过</button>
        <button onClick={() => onReview('revise')}><RefreshCw size={15} />修改</button>
        <button onClick={() => onReview('reject')}><X size={15} />拒绝</button>
      </div>
      <div className="review-extra-actions">
        <button onClick={() => onReviewAction('rerun_analysis')}>深入分析</button>
        <button onClick={() => onReviewAction('focus_module', { module: comment || 'selected module' })}>聚焦模块</button>
        <button onClick={() => onReviewAction('save_knowledge')}>保存知识</button>
        <button onClick={() => onReviewAction('learning_task')}>学习任务</button>
      </div>
    </div>
  );
}

function Palette() {
  return (
    <div className="palette">
      {palette.map((item) => {
        const Icon = item.icon;
        return (
          <button
            key={`${item.type}-${item.name}`}
            draggable
            onDragStart={(event) =>
              event.dataTransfer.setData(dragPayloadMime, JSON.stringify({ type: item.type, name: item.name, config: item.config }))
            }
          >
            <Icon size={16} />
            {item.name}
          </button>
        );
      })}
    </div>
  );
}

function WorkflowCanvas({
  canvasRef,
  canvasSize,
  connectFrom,
  edges,
  nodes,
  nodeStatus,
  selectedEdgeKey,
  selectedNodeId,
  onCanvasPointerMove,
  onDrop,
  onEndPointer,
  onStartCanvasPan,
  onStartMove,
  onSelectEdge,
  onToggleConnect,
}: {
  canvasRef: Ref<HTMLDivElement>;
  canvasSize: { width: number; height: number };
  connectFrom: string | null;
  edges: WorkflowEdge[];
  nodes: WorkflowNode[];
  nodeStatus: Record<string, NodeStatus>;
  selectedEdgeKey: string;
  selectedNodeId: string;
  onCanvasPointerMove: (event: PointerEvent<HTMLDivElement>) => void;
  onDrop: (event: React.DragEvent<HTMLDivElement>) => void;
  onEndPointer: () => void;
  onStartCanvasPan: (event: PointerEvent<HTMLDivElement>) => void;
  onStartMove: (event: PointerEvent<HTMLDivElement>, node: WorkflowNode) => void;
  onSelectEdge: (edge: WorkflowEdge) => void;
  onToggleConnect: (nodeId: string) => void;
}) {
  return (
    <div
      ref={canvasRef}
      className="workflow-canvas"
      onDragOver={(event) => event.preventDefault()}
      onDrop={onDrop}
      onPointerDown={onStartCanvasPan}
      onPointerMove={onCanvasPointerMove}
      onPointerUp={onEndPointer}
      onPointerCancel={onEndPointer}
    >
      <div className="canvas-surface" style={{ width: canvasSize.width, height: canvasSize.height }}>
        <svg className="edges">
          {edges.map((edge) => {
            const source = nodes.find((node) => node.id === edge.source);
            const target = nodes.find((node) => node.id === edge.target);
            if (!source || !target) return null;
            const x1 = source.x + 164;
            const y1 = source.y + 31;
            const x2 = target.x;
            const y2 = target.y + 31;
            const key = edgeKeyFor(edge);
            const label = edge.condition && edge.condition !== 'always' ? edge.condition : '';
            return (
              <g
                key={key}
                className={selectedEdgeKey === key ? 'selected-edge' : ''}
                onPointerDown={(event) => event.stopPropagation()}
                onClick={(event) => {
                  event.stopPropagation();
                  onSelectEdge(edge);
                }}
              >
                <path d={`M ${x1} ${y1} C ${x1 + 58} ${y1}, ${x2 - 58} ${y2}, ${x2} ${y2}`} />
                <circle cx={x2} cy={y2} r="3" />
                {label ? (
                  <text x={(x1 + x2) / 2 - 24} y={(y1 + y2) / 2 - 8}>
                    {label}
                  </text>
                ) : null}
              </g>
            );
          })}
        </svg>

        {nodes.map((node) => (
          <div
            key={node.id}
            className={`flow-node ${connectFrom === node.id ? 'connecting' : ''} ${selectedNodeId === node.id ? 'selected' : ''} ${nodeStatus[node.id]}`}
            style={{ transform: `translate(${node.x}px, ${node.y}px)` }}
            onPointerDown={(event) => onStartMove(event, node)}
          >
            <button
              className="connector"
              onPointerDown={(event) => event.stopPropagation()}
              onClick={(event) => {
                event.stopPropagation();
                onToggleConnect(node.id);
              }}
              title="连接节点"
            >
              <ArrowRight size={14} />
            </button>
            <strong>{node.name}</strong>
            <span>{node.type}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function SavedWorkflows({
  workflows,
  onLoad,
  onRefresh,
}: {
  workflows: WorkflowRecord[];
  onLoad: (workflow: WorkflowRecord) => void;
  onRefresh: () => void;
}) {
  return (
    <>
      <button className="secondary refresh-row" onClick={onRefresh}>
        <RefreshCw size={15} />
        刷新列表
      </button>
      <div className="saved-list">
        {workflows.slice(0, 8).map((workflow) => (
          <button key={workflow.workflow_id} onClick={() => onLoad(workflow)}>
            <span>{workflow.name}</span>
            <small>{workflow.updated_at.slice(0, 10)}</small>
          </button>
        ))}
      </div>
    </>
  );
}

function NodeConfig({
  node,
  approvals,
  onNodeChange,
  onConfigChange,
  onApproveSkill,
  onDelete,
}: {
  node?: WorkflowNode;
  approvals: SkillApproval[];
  onNodeChange: (patch: Partial<WorkflowNode>) => void;
  onConfigChange: (key: string, value: unknown) => void;
  onApproveSkill: (skillCode: string, agentCode: string) => Promise<void>;
  onDelete: () => void;
}) {
  if (!node) {
    return (
      <div className="node-config-empty">
        <PanelTitle title="????" />
        <p className="empty-text">???????????????????</p>
      </div>
    );
  }
  const mcpArgumentsText = String(node.config.arguments_text ?? JSON.stringify(node.config.arguments ?? {}, null, 2));
  function handleMcpArgumentsChange(value: string) {
    onConfigChange('arguments_text', value);
    try {
      onConfigChange('arguments', JSON.parse(value));
    } catch {
      // Keep the raw text while the user is still editing invalid JSON.
    }
  }
  const skillCode = String(node.config.skill_code ?? 'code.review');
  const skillAgentCode = String(node.config.agent_code ?? 'workflow_runner');
  const skillApproval = node.type === 'skill'
    ? approvals.find((approval) => approval.skill_code === skillCode && approval.agent_code === skillAgentCode)
    : undefined;
  return (
    <div className="config-form">
      <PanelTitle title="????" />

      <div className="config-section">
        <strong>????</strong>
        <label>
          ??
          <input value={node.name} onChange={(event) => onNodeChange({ name: event.target.value })} />
          <FieldHelp>?????????????????? Agent ????</FieldHelp>
        </label>
        <label>
          ??
          <select value={node.type} onChange={(event) => onNodeChange({ type: event.target.value })}>
            <option value="planner">planner</option>
            <option value="agent">agent</option>
            <option value="rag">rag</option>
            <option value="mcp_tool">mcp_tool</option>
            <option value="skill">skill</option>
            <option value="supervisor">supervisor</option>
            <option value="human_review">human_review</option>
            <option value="reporter">reporter</option>
          </select>
          <FieldHelp>??????????Agent???????????????????</FieldHelp>
        </label>
      </div>

      <div className="config-section">
        <strong>????</strong>
        <label>
          ????
          <textarea value={String(node.config.focus ?? '')} onChange={(event) => onConfigChange('focus', event.target.value)} />
          <FieldHelp>???????????????????????????????</FieldHelp>
        </label>
        <label>
          ????
          <input value={String(node.config.output_format ?? '')} onChange={(event) => onConfigChange('output_format', event.target.value)} />
          <FieldHelp>????????????????????????</FieldHelp>
        </label>
      </div>

      {node.type === 'agent' ? (
        <div className="config-section">
          <strong>Agent ????</strong>
          <label>
            Agent
            <select value={String(node.config.agent_type ?? 'project_analyzer')} onChange={(event) => onConfigChange('agent_type', event.target.value)}>
              <option value="project_analyzer">project_analyzer</option>
              <option value="code_reviewer">code_reviewer</option>
              <option value="file_reviewer">file_reviewer</option>
              <option value="rag_processor">rag_processor</option>
              <option value="learning_coach">learning_coach</option>
            </select>
            <FieldHelp>??????? Agent ???????????????????RAG ????????</FieldHelp>
          </label>
          <label>
            {node.config.agent_type === 'file_reviewer' ? 'max_chars' : 'max_files'}
            <input
              type="number"
              min={1}
              value={Number(node.config.agent_type === 'file_reviewer' ? node.config.max_chars ?? 20000 : node.config.max_files ?? 100)}
              onChange={(event) => onConfigChange(node.config.agent_type === 'file_reviewer' ? 'max_chars' : 'max_files', Number(event.target.value))}
            />
            <FieldHelp>{node.config.agent_type === 'file_reviewer' ? '??????????????????' : '??? Agent ?????????'}</FieldHelp>
          </label>
          {node.config.agent_type === 'file_reviewer' ? (
            <label>
              file_path
              <input value={String(node.config.file_path ?? '')} onChange={(event) => onConfigChange('file_path', event.target.value)} />
              <FieldHelp>?????????????????? Agent ?????????</FieldHelp>
            </label>
          ) : null}
          {node.config.agent_type === 'rag_processor' ? (
            <>
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={node.config.ingest !== false}
                  onChange={(event) => onConfigChange('ingest', event.target.checked)}
                />
                ????
              </label>
              <label>
                collection
                <input
                  value={String(node.config.collection ?? 'project-memory')}
                  onChange={(event) => onConfigChange('collection', event.target.value)}
                />
                <FieldHelp>?????????????????? project-memory?</FieldHelp>
              </label>
            </>
          ) : null}
        </div>
      ) : null}

      {node.type === 'rag' ? (
        <div className="config-section">
          <strong>RAG ??</strong>
          <label>
            collection
            <input value={String(node.config.collection ?? 'default')} onChange={(event) => onConfigChange('collection', event.target.value)} />
            <FieldHelp>?????????? RAG ????</FieldHelp>
          </label>
          <label>
            top_k
            <input type="number" min={1} max={20} value={Number(node.config.top_k ?? 5)} onChange={(event) => onConfigChange('top_k', Number(event.target.value))} />
            <FieldHelp>?????????????</FieldHelp>
          </label>
        </div>
      ) : null}

      {node.type === 'mcp_tool' ? (
        <div className="config-section">
          <strong>MCP ??</strong>
          <label>
            ????
            <select value={String(node.config.tool_name ?? 'filesystem.list')} onChange={(event) => onConfigChange('tool_name', event.target.value)}>
              <option value="filesystem.list">filesystem.list</option>
              <option value="filesystem.read">filesystem.read</option>
              <option value="git.status">git.status</option>
              <option value="git.log">git.log</option>
              <option value="echo">echo / custom MCP tool</option>
            </select>
            <FieldHelp>local ?????? filesystem/git?mcp ???? tool_name ???? MCP server?</FieldHelp>
          </label>
          <label>
            tool_name
            <input value={String(node.config.tool_name ?? 'filesystem.list')} onChange={(event) => onConfigChange('tool_name', event.target.value)} />
            <FieldHelp>?? MCP Tool ????? filesystem.read_file?github.create_issue ???? server ??????</FieldHelp>
          </label>
          <label>
            server_id
            <input value={String(node.config.server_id ?? '')} onChange={(event) => onConfigChange('server_id', event.target.value)} />
            <FieldHelp>JAYCODE_MCP_PROVIDER=mcp ?????? /api/v1/mcp/servers ???? server_id?</FieldHelp>
          </label>
          <label>
            agent_code
            <input value={String(node.config.agent_code ?? 'workflow_runner')} onChange={(event) => onConfigChange('agent_code', event.target.value)} />
            <FieldHelp>?? MCP ????????? workflow_runner?</FieldHelp>
          </label>
          <label>
            arguments JSON
            <textarea value={mcpArgumentsText} onChange={(event) => handleMcpArgumentsChange(event.target.value)} />
            <FieldHelp>???? MCP Tool ????local ?????? root_path?file_path?max_files?limit ????</FieldHelp>
          </label>
        </div>
      ) : null}

      {node.type === 'skill' ? (
        <div className="config-section">
          <strong>Skill ??</strong>
          <div className={`workflow-skill-approval ${skillApproval?.allowed ? 'approved' : 'pending'}`}>
            <span className={`mcp-approval-state ${skillApproval?.allowed ? 'approved' : 'pending'}`}>
              {skillApproval?.allowed ? '???' : '???'}
            </span>
            <small>{skillCode} / {skillAgentCode}</small>
            <small>??? skill_code + agent_code ?????Workflow ?? Skill ??? workflow_runner????? Skill ? workflow_runner ?????Workflow ?????</small>
            {skillApproval?.reason ? <small>{skillApproval.reason}</small> : null}
            {!skillApproval?.allowed ? (
              <button type="button" className="secondary" onClick={() => onApproveSkill(skillCode, skillAgentCode)}>
                ???? Workflow ??
              </button>
            ) : null}
          </div>
          <label>
            skill_code
            <input value={String(node.config.skill_code ?? 'code.review')} onChange={(event) => onConfigChange('skill_code', event.target.value)} />
            <FieldHelp>???? Skill ????? code.review?rag.chunk?security.scan?</FieldHelp>
          </label>
          <label>
            agent_code
            <input value={String(node.config.agent_code ?? 'workflow_runner')} onChange={(event) => onConfigChange('agent_code', event.target.value)} />
            <FieldHelp>??? Skill ??????skill_console ??? Skills ???????workflow_runner ?? Workflow ?????Workflow ??????? skill_code + workflow_runner?</FieldHelp>
          </label>
          <label>
            input JSON
            <textarea
              value={String(node.config.input_text ?? JSON.stringify(node.config.input ?? {}, null, 2))}
              onChange={(event) => {
                onConfigChange('input_text', event.target.value);
                try {
                  onConfigChange('input', JSON.parse(event.target.value));
                } catch {
                  // Keep raw text until the JSON becomes valid.
                }
              }}
            />
            <FieldHelp>?? Skill ??????????? project_path?goal?max_files ???</FieldHelp>
          </label>
          <label>
            input_mappings JSON
            <textarea
              value={String(node.config.input_mappings_text ?? JSON.stringify(node.config.input_mappings ?? {}, null, 2))}
              onChange={(event) => {
                onConfigChange('input_mappings_text', event.target.value);
                try {
                  onConfigChange('input_mappings', JSON.parse(event.target.value));
                } catch {
                  // Keep raw text until the JSON becomes valid.
                }
              }}
            />
            <FieldHelp>?????????? Skill ??????? <code>{'{"context":{"source":"plan","path":"plan.0"}}'}</code>?source ?? current?goal?input_text????? id ? outputs.xxx?</FieldHelp>
          </label>
        </div>
      ) : null}

      <details className="advanced-config">
        <summary>????</summary>
        <div className="config-section">
          <label className="check-row">
            <input
              type="checkbox"
              checked={Boolean(node.config.confirm_before_run)}
              onChange={(event) => onConfigChange('confirm_before_run', event.target.checked)}
            />
            ?????????
          </label>
          <FieldHelp>???????????????? checkpoint???????????????</FieldHelp>
          <label>
            retry_count
            <input type="number" min={0} max={5} value={Number(node.config.retry_count ?? 0)} onChange={(event) => onConfigChange('retry_count', Number(event.target.value))} />
            <FieldHelp>????????????????? 5 ??</FieldHelp>
          </label>
          <label>
            input_from
            <input value={String(node.config.input_from ?? '')} placeholder="current / goal / ???? id" onChange={(event) => onConfigChange('input_from', event.target.value)} />
            <FieldHelp>?????????????current?goal???????? id?</FieldHelp>
          </label>
          <label>
            input_path
            <input value={String(node.config.input_path ?? '')} placeholder="report_markdown / results.0.content" onChange={(event) => onConfigChange('input_path', event.target.value)} />
            <FieldHelp>?????????????? report_markdown ? results.0.content?</FieldHelp>
          </label>
          <label>
            output_key
            <input value={String(node.config.output_key ?? '')} placeholder={node.id} onChange={(event) => onConfigChange('output_key', event.target.value)} />
            <FieldHelp>????????? state.outputs ? key???????? id?</FieldHelp>
          </label>
          <label>
            fail_strategy
            <select value={String(node.config.fail_strategy ?? 'halt')} onChange={(event) => onConfigChange('fail_strategy', event.target.value)}>
              <option value="halt">halt</option>
              <option value="continue">continue</option>
            </select>
            <FieldHelp>halt ??????????continue ?????????????</FieldHelp>
          </label>
        </div>
      </details>
      <button className="danger" onClick={onDelete}>
        <Trash2 size={15} />
        ????
      </button>
    </div>
  );
}

function LegacyWorkflowCanvas({
  canvasRef,
  canvasSize,
  connectFrom,
  edges,
  nodes,
  nodeStatus,
  selectedEdgeKey,
  selectedNodeId,
  onCanvasPointerMove,
  onDrop,
  onEndPointer,
  onStartCanvasPan,
  onStartMove,
  onSelectEdge,
  onToggleConnect,
}: {
  canvasRef: Ref<HTMLDivElement>;
  canvasSize: { width: number; height: number };
  connectFrom: string | null;
  edges: WorkflowEdge[];
  nodes: WorkflowNode[];
  nodeStatus: Record<string, NodeStatus>;
  selectedEdgeKey: string;
  selectedNodeId: string;
  onCanvasPointerMove: (event: PointerEvent<HTMLDivElement>) => void;
  onDrop: (event: React.DragEvent<HTMLDivElement>) => void;
  onEndPointer: () => void;
  onStartCanvasPan: (event: PointerEvent<HTMLDivElement>) => void;
  onStartMove: (event: PointerEvent<HTMLDivElement>, node: WorkflowNode) => void;
  onSelectEdge: (edge: WorkflowEdge) => void;
  onToggleConnect: (nodeId: string) => void;
}) {
  return (
    <div
      ref={canvasRef}
      className="workflow-canvas"
      onDragOver={(event) => event.preventDefault()}
      onDrop={onDrop}
      onPointerDown={onStartCanvasPan}
      onPointerMove={onCanvasPointerMove}
      onPointerUp={onEndPointer}
      onPointerCancel={onEndPointer}
    >
      <div className="canvas-surface" style={{ width: canvasSize.width, height: canvasSize.height }}>
        <svg className="edges">
          {edges.map((edge) => {
            const source = nodes.find((node) => node.id === edge.source);
            const target = nodes.find((node) => node.id === edge.target);
            if (!source || !target) return null;
            const x1 = source.x + 164;
            const y1 = source.y + 31;
            const x2 = target.x;
            const y2 = target.y + 31;
            const key = edgeKeyFor(edge);
            const label = edge.condition && edge.condition !== 'always' ? edge.condition : '';
            return (
              <g
                key={key}
                className={selectedEdgeKey === key ? 'selected-edge' : ''}
                onPointerDown={(event) => event.stopPropagation()}
                onClick={(event) => {
                  event.stopPropagation();
                  onSelectEdge(edge);
                }}
              >
                <path d={`M ${x1} ${y1} C ${x1 + 58} ${y1}, ${x2 - 58} ${y2}, ${x2} ${y2}`} />
                <circle cx={x2} cy={y2} r="3" />
                {label ? (
                  <text x={(x1 + x2) / 2 - 24} y={(y1 + y2) / 2 - 8}>
                    {label}
                  </text>
                ) : null}
              </g>
            );
          })}
        </svg>

        {nodes.map((node) => (
          <div
            key={node.id}
            className={`flow-node ${connectFrom === node.id ? 'connecting' : ''} ${selectedNodeId === node.id ? 'selected' : ''} ${nodeStatus[node.id]}`}
            style={{ transform: `translate(${node.x}px, ${node.y}px)` }}
            onPointerDown={(event) => onStartMove(event, node)}
          >
            <button
              className="connector"
              onPointerDown={(event) => event.stopPropagation()}
              onClick={(event) => {
                event.stopPropagation();
                onToggleConnect(node.id);
              }}
              title="连接节点"
            >
              <ArrowRight size={14} />
            </button>
            <strong>{node.name}</strong>
            <span>{node.type}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function LegacySavedWorkflows({
  workflows,
  onLoad,
  onRefresh,
}: {
  workflows: WorkflowRecord[];
  onLoad: (workflow: WorkflowRecord) => void;
  onRefresh: () => void;
}) {
  return (
    <>
      <button className="secondary refresh-row" onClick={onRefresh}>
        <RefreshCw size={15} />
        刷新列表
      </button>
      <div className="saved-list">
        {workflows.slice(0, 8).map((workflow) => (
          <button key={workflow.workflow_id} onClick={() => onLoad(workflow)}>
            <span>{workflow.name}</span>
            <small>{workflow.updated_at.slice(0, 10)}</small>
          </button>
        ))}
      </div>
    </>
  );
}

function LegacyNodeConfig({
  node,
  approvals,
  onNodeChange,
  onConfigChange,
  onApproveSkill,
  onDelete,
}: {
  node?: WorkflowNode;
  approvals: SkillApproval[];
  onNodeChange: (patch: Partial<WorkflowNode>) => void;
  onConfigChange: (key: string, value: unknown) => void;
  onApproveSkill: (skillCode: string, agentCode: string) => Promise<void>;
  onDelete: () => void;
}) {
  if (!node) {
    return (
      <div className="node-config-empty">
        <PanelTitle title="节点配置" />
        <p className="empty-text">选择一个流程节点后配置参数。</p>
      </div>
    );
  }
  const mcpArgumentsText = String(node.config.arguments_text ?? JSON.stringify(node.config.arguments ?? {}, null, 2));
  function handleMcpArgumentsChange(value: string) {
    onConfigChange('arguments_text', value);
    try {
      onConfigChange('arguments', JSON.parse(value));
    } catch {
      // Keep the raw text while the user is still editing invalid JSON.
    }
  }
  const skillCode = String(node.config.skill_code ?? 'code.review');
  const skillAgentCode = String(node.config.agent_code ?? 'workflow_runner');
  const skillApproval = node.type === 'skill'
    ? approvals.find((approval) => approval.skill_code === skillCode && approval.agent_code === skillAgentCode)
    : undefined;
  return (
    <div className="config-form">
      <PanelTitle title="节点配置" />
      <label>
        名称
        <input value={node.name} onChange={(event) => onNodeChange({ name: event.target.value })} />
        <FieldHelp>节点显示名称，会出现在画布、时间线和 Agent 输出里。</FieldHelp>
      </label>
      <label>
        类型
        <select value={node.type} onChange={(event) => onNodeChange({ type: event.target.value })}>
          <option value="planner">planner</option>
          <option value="agent">agent</option>
          <option value="rag">rag</option>
          <option value="mcp_tool">mcp_tool</option>
          <option value="skill">skill</option>
          <option value="supervisor">supervisor</option>
          <option value="human_review">human_review</option>
          <option value="reporter">reporter</option>
        </select>
        <FieldHelp>节点类型决定运行器：Agent、工具、知识检索、人工审核或报告生成。</FieldHelp>
      </label>
      <label>
        分析重点
        <textarea value={String(node.config.focus ?? '')} onChange={(event) => onConfigChange('focus', event.target.value)} />
        <FieldHelp>告诉当前节点更关注什么，例如结构、风险、测试、依赖或学习路径。</FieldHelp>
      </label>
      <label>
        输出要求
        <input value={String(node.config.output_format ?? '')} onChange={(event) => onConfigChange('output_format', event.target.value)} />
        <FieldHelp>约束输出格式，例如“列出风险等级和下一步动作”。</FieldHelp>
      </label>
      {node.type === 'agent' ? (
        <>
          <label>
            Agent
            <select value={String(node.config.agent_type ?? 'project_analyzer')} onChange={(event) => onConfigChange('agent_type', event.target.value)}>
              <option value="project_analyzer">project_analyzer</option>
              <option value="code_reviewer">code_reviewer</option>
              <option value="file_reviewer">file_reviewer</option>
              <option value="rag_processor">rag_processor</option>
              <option value="learning_coach">learning_coach</option>
            </select>
            <FieldHelp>选择真实调用的 Agent 子能力：项目分析、代码审查、文件审查、RAG 加工或学习陪练。</FieldHelp>
          </label>
          <label>
            {node.config.agent_type === 'file_reviewer' ? 'max_chars' : 'max_files'}
            <input
              type="number"
              min={1}
              value={Number(node.config.agent_type === 'file_reviewer' ? node.config.max_chars ?? 20000 : node.config.max_files ?? 100)}
              onChange={(event) => onConfigChange(node.config.agent_type === 'file_reviewer' ? 'max_chars' : 'max_files', Number(event.target.value))}
            />
            <FieldHelp>{node.config.agent_type === 'file_reviewer' ? '限制单文件读取字符数，防止报告过长。' : '限制该 Agent 最多扫描的文件数。'}</FieldHelp>
          </label>
          {node.config.agent_type === 'file_reviewer' ? (
            <label>
              file_path
              <input value={String(node.config.file_path ?? '')} onChange={(event) => onConfigChange('file_path', event.target.value)} />
              <FieldHelp>相对项目根目录的文件路径，文件级审查 Agent 会只分析这个文件。</FieldHelp>
            </label>
          ) : null}
          {node.config.agent_type === 'rag_processor' ? (
            <>
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={node.config.ingest !== false}
                  onChange={(event) => onConfigChange('ingest', event.target.checked)}
                />
                自动入库
              </label>
              <label>
                collection
                <input
                  value={String(node.config.collection ?? 'project-memory')}
                  onChange={(event) => onConfigChange('collection', event.target.value)}
                />
                <FieldHelp>自动入库时写入的知识集合名，默认推荐 project-memory。</FieldHelp>
              </label>
            </>
          ) : null}
        </>
      ) : null}
      {node.type === 'rag' ? (
        <>
          <label>
            collection
            <input value={String(node.config.collection ?? 'default')} onChange={(event) => onConfigChange('collection', event.target.value)} />
            <FieldHelp>知识检索节点要查询的 RAG 集合名。</FieldHelp>
          </label>
          <label>
            top_k
            <input type="number" min={1} max={20} value={Number(node.config.top_k ?? 5)} onChange={(event) => onConfigChange('top_k', Number(event.target.value))} />
            <FieldHelp>返回最相关的知识片段数量。</FieldHelp>
          </label>
        </>
      ) : null}
      {node.type === 'mcp_tool' ? (
        <>
          <label>
            常用工具
            <select value={String(node.config.tool_name ?? 'filesystem.list')} onChange={(event) => onConfigChange('tool_name', event.target.value)}>
              <option value="filesystem.list">filesystem.list</option>
              <option value="filesystem.read">filesystem.read</option>
              <option value="git.status">git.status</option>
              <option value="git.log">git.log</option>
              <option value="echo">echo / custom MCP tool</option>
            </select>
            <FieldHelp>local 模式可选内置 filesystem/git；mcp 模式会把 tool_name 发给真实 MCP server。</FieldHelp>
          </label>
          <label>
            tool_name
            <input value={String(node.config.tool_name ?? 'filesystem.list')} onChange={(event) => onConfigChange('tool_name', event.target.value)} />
            <FieldHelp>真实 MCP Tool 名称，例如 filesystem.read_file、github.create_issue 或自定义 server 暴露的工具。</FieldHelp>
          </label>
          <label>
            server_id
            <input value={String(node.config.server_id ?? '')} onChange={(event) => onConfigChange('server_id', event.target.value)} />
            <FieldHelp>JAYCODE_MCP_PROVIDER=mcp 时必填，对应 /api/v1/mcp/servers 中保存的 server_id。</FieldHelp>
          </label>
          <label>
            agent_code
            <input value={String(node.config.agent_code ?? 'workflow_runner')} onChange={(event) => onConfigChange('agent_code', event.target.value)} />
            <FieldHelp>用于 MCP 工具权限审批，默认 workflow_runner。</FieldHelp>
          </label>
          <label>
            arguments JSON
            <textarea value={mcpArgumentsText} onChange={(event) => handleMcpArgumentsChange(event.target.value)} />
            <FieldHelp>传给真实 MCP Tool 的参数。local 模式也会读取 root_path、file_path、max_files、limit 等字段。</FieldHelp>
          </label>
        </>
      ) : null}
      {node.type === 'skill' ? (
        <>
          <div className={`workflow-skill-approval ${skillApproval?.allowed ? 'approved' : 'pending'}`}>
            <span className={`mcp-approval-state ${skillApproval?.allowed ? 'approved' : 'pending'}`}>
              {skillApproval?.allowed ? '已审批' : '待审批'}
            </span>
            <small>{skillCode} / {skillAgentCode}</small>
            <small>权限按 skill_code + agent_code 精确匹配。Workflow 运行 Skill 时使用 workflow_runner；只有当前 Skill 的 workflow_runner 审批通过，Workflow 才能执行。</small>
            {skillApproval?.reason ? <small>{skillApproval.reason}</small> : null}
            {!skillApproval?.allowed ? (
              <button type="button" className="secondary" onClick={() => onApproveSkill(skillCode, skillAgentCode)}>
                审批当前 Workflow 节点
              </button>
            ) : null}
          </div>
          <label>
            skill_code
            <input value={String(node.config.skill_code ?? 'code.review')} onChange={(event) => onConfigChange('skill_code', event.target.value)} />
            <FieldHelp>要执行的 Skill 编号，例如 code.review、rag.chunk、security.scan。</FieldHelp>
          </label>
          <label>
            agent_code
            <input value={String(node.config.agent_code ?? 'workflow_runner')} onChange={(event) => onConfigChange('agent_code', event.target.value)} />
            <FieldHelp>这里是 Skill 的调用身份。skill_console 只表示 Skills 页面手动测试；workflow_runner 表示 Workflow 自动执行。Workflow 运行时必须审批 skill_code + workflow_runner。</FieldHelp>
          </label>
          <label>
            input JSON
            <textarea
              value={String(node.config.input_text ?? JSON.stringify(node.config.input ?? {}, null, 2))}
              onChange={(event) => {
                onConfigChange('input_text', event.target.value);
                try {
                  onConfigChange('input', JSON.parse(event.target.value));
                } catch {
                  // Keep raw text until the JSON becomes valid.
                }
              }}
            />
            <FieldHelp>传给 Skill 的额外输入，会和任务的 project_path、goal、max_files 合并。</FieldHelp>
          </label>
          <label>
            input_mappings JSON
            <textarea
              value={String(node.config.input_mappings_text ?? JSON.stringify(node.config.input_mappings ?? {}, null, 2))}
              onChange={(event) => {
                onConfigChange('input_mappings_text', event.target.value);
                try {
                  onConfigChange('input_mappings', JSON.parse(event.target.value));
                } catch {
                  // Keep raw text until the JSON becomes valid.
                }
              }}
            />
            <FieldHelp>把上游节点输出映射到 Skill 输入字段，例如 <code>{'{"context":{"source":"plan","path":"plan.0"}}'}</code>。source 可用 current、goal、input_text、上游节点 id 或 outputs.xxx。</FieldHelp>
          </label>
        </>
      ) : null}
      <div className="config-divider">Production</div>
      <label className="check-row">
        <input
          type="checkbox"
          checked={Boolean(node.config.confirm_before_run)}
          onChange={(event) => onConfigChange('confirm_before_run', event.target.checked)}
        />
        节点执行前人工确认
      </label>
      <FieldHelp>开启后，运行到该节点会暂停并保存 checkpoint；点通过后会从该节点继续执行。</FieldHelp>
      <label>
        retry_count
        <input type="number" min={0} max={5} value={Number(node.config.retry_count ?? 0)} onChange={(event) => onConfigChange('retry_count', Number(event.target.value))} />
        <FieldHelp>节点失败后的自动重试次数，最多建议 5 次。</FieldHelp>
      </label>
      <label>
        input_from
        <input value={String(node.config.input_from ?? '')} placeholder="current / goal / 上游节点 id" onChange={(event) => onConfigChange('input_from', event.target.value)} />
        <FieldHelp>指定当前节点读取哪个输入：current、goal，或某个上游节点 id。</FieldHelp>
      </label>
      <label>
        input_path
        <input value={String(node.config.input_path ?? '')} placeholder="report_markdown / results.0.content" onChange={(event) => onConfigChange('input_path', event.target.value)} />
        <FieldHelp>从输入对象中取某个字段，例如 report_markdown 或 results.0.content。</FieldHelp>
      </label>
      <label>
        output_key
        <input value={String(node.config.output_key ?? '')} placeholder={node.id} onChange={(event) => onConfigChange('output_key', event.target.value)} />
        <FieldHelp>当前节点输出保存到 state.outputs 的 key；为空时使用节点 id。</FieldHelp>
      </label>
      <label>
        fail_strategy
        <select value={String(node.config.fail_strategy ?? 'halt')} onChange={(event) => onConfigChange('fail_strategy', event.target.value)}>
          <option value="halt">halt</option>
          <option value="continue">continue</option>
        </select>
        <FieldHelp>halt 表示失败后停止流程；continue 表示记录失败但继续走下游。</FieldHelp>
      </label>
      <button className="danger" onClick={onDelete}>
        <Trash2 size={15} />
        删除节点
      </button>
    </div>
  );
}

function EdgeConfig({
  edge,
  nodes,
  onChange,
  onDelete,
}: {
  edge?: WorkflowEdge;
  nodes: WorkflowNode[];
  onChange: (patch: Partial<WorkflowEdge>) => void;
  onDelete: () => void;
}) {
  if (!edge) {
    return (
      <div className="edge-config-empty">
        <PanelTitle title="边配置" />
        <p className="empty-text">点击画布连线后配置条件分支。</p>
      </div>
    );
  }
  return (
    <div className="config-form edge-config">
      <PanelTitle title="边配置" />
      <label>
        source
        <select value={edge.source} onChange={(event) => onChange({ source: event.target.value })}>
          {nodes.map((node) => <option key={node.id} value={node.id}>{node.id}</option>)}
        </select>
        <FieldHelp>分支起点节点，条件会基于这个节点的输出或状态判断。</FieldHelp>
      </label>
      <label>
        target
        <select value={edge.target} onChange={(event) => onChange({ target: event.target.value })}>
          {nodes.map((node) => <option key={node.id} value={node.id}>{node.id}</option>)}
        </select>
        <FieldHelp>条件命中后要执行的下游节点。</FieldHelp>
      </label>
      <label>
        condition
        <select value={edge.condition ?? 'always'} onChange={(event) => onChange({ condition: event.target.value })}>
          <option value="always">always</option>
          <option value="contains">contains</option>
          <option value="on_status">on_status</option>
          <option value="truthy_output">truthy_output</option>
        </select>
        <FieldHelp>always 总是执行；contains 检查输出文本；on_status 检查节点状态；truthy_output 检查字段是否有值。</FieldHelp>
      </label>
      <label>
        value
        <input value={edge.value ?? ''} onChange={(event) => onChange({ value: event.target.value })} />
        <FieldHelp>条件匹配值，例如 contains 要包含的关键词，或 on_status 的 completed/failed。</FieldHelp>
      </label>
      <label>
        source_path
        <input value={edge.source_path ?? ''} placeholder="report_markdown / status / results.0.content" onChange={(event) => onChange({ source_path: event.target.value })} />
        <FieldHelp>可选，从源节点输出中取指定字段再判断；为空时判断整个输出。</FieldHelp>
      </label>
      <button className="danger" onClick={onDelete}>
        <Trash2 size={15} />
        删除连线
      </button>
    </div>
  );
}

function WorkflowValidationView({ validation }: { validation: WorkflowValidation | null }) {
  if (!validation) return null;
  return (
    <div className={`workflow-validation ${validation.valid ? 'valid' : 'invalid'}`}>
      <strong>{validation.valid ? 'Workflow 校验通过' : 'Workflow 校验失败'}</strong>
      <p>{validation.node_count} nodes / {validation.edge_count} edges</p>
      {validation.parallel_sources.length ? <p>并行源节点：{validation.parallel_sources.join(', ')}</p> : null}
      {validation.errors.map((item) => <p className="error-text" key={item}>{item}</p>)}
      {validation.warnings.map((item) => <p className="warning-text" key={item}>{item}</p>)}
    </div>
  );
}

function OutputList({ title, empty, items }: { title: string; empty: string; items: string[] }) {
  return (
    <div className="output-list">
      <PanelTitle title={title} />
      {items.length ? items.map((item) => <p key={item}>{item}</p>) : <p className="empty-text">{empty}</p>}
    </div>
  );
}

function parseJsonValue<T>(text: string, fallback: T): T {
  try {
    return JSON.parse(text) as T;
  } catch {
    return fallback;
  }
}

function splitLines(text: string): string[] {
  return text
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function defaultMcpToolName(serverId: string) {
  return serverId === 'real_memory' ? 'search_nodes' : 'read_text_file';
}

function defaultMcpCallArguments(toolName: string, serverId: string) {
  const projectPath = defaultProjectPath.replace(/\\/g, '/');
  const name = toolName || defaultMcpToolName(serverId);
  const samples: Record<string, Record<string, unknown>> = {
    read_file: { path: `${projectPath}/README.md`, head: 5 },
    read_text_file: { path: `${projectPath}/README.md`, head: 5 },
    read_multiple_files: { paths: [`${projectPath}/README.md`, `${projectPath}/pyproject.toml`] },
    read_media_file: { path: `${projectPath}/README.md` },
    list_directory: { path: projectPath },
    list_directory_with_sizes: { path: projectPath, sortBy: 'name' },
    directory_tree: { path: projectPath, excludePatterns: ['**/.venv/**', '**/node_modules/**', '**/web/dist/**'] },
    search_files: { path: projectPath, pattern: '**/*mcp*.py', excludePatterns: ['**/.venv/**', '**/node_modules/**', '**/__pycache__/**'] },
    get_file_info: { path: `${projectPath}/README.md` },
    list_allowed_directories: {},
    create_entities: {
      entities: [
        {
          name: 'MCP 管理页面',
          entityType: 'feature',
          observations: ['支持真实 MCP Server 保存、Discover、审批和测试调用'],
        },
      ],
    },
    search_nodes: { query: 'Jaycode' },
    open_nodes: { names: ['Jaycode'] },
    read_graph: {},
    add_observations: { observations: [{ entityName: 'Jaycode', contents: ['MCP 页面测试调用使用真实工具参数模板'] }] },
    create_relations: { relations: [{ from: 'Jaycode', to: 'MCP 管理页面', relationType: 'contains feature' }] },
  };
  return JSON.stringify(samples[name] ?? {}, null, 2);
}

function defaultBenchmarkCases(type: BenchmarkType = 'mcp'): BenchmarkCase[] {
  const projectPath = defaultProjectPath.replace(/\\/g, '/');
  if (type === 'llm') {
    return [
      {
        case_id: 'planner_v1_project_plan',
        tool_name: 'planner.v1',
        arguments: {
          agent: 'planner',
          prompt_version: 'planner.v1',
          system_prompt: 'You are a concise software project planning agent.',
          user_prompt: 'Plan how to analyze Jaycode from architecture, risks, knowledge, and workflow.',
          fallback: 'Analyze architecture, risks, knowledge assets, workflow runtime, and next actions.',
          expected_keywords: ['architecture', 'risk', 'workflow'],
        },
        enabled: true,
      },
      {
        case_id: 'reporter_v1_governance_report',
        tool_name: 'reporter.v1',
        arguments: {
          agent: 'reporter',
          prompt_version: 'reporter.v1',
          system_prompt: 'You are a software governance report writer.',
          user_prompt: 'Write a concise governance summary for a multi-agent project analysis workbench.',
          fallback: 'The report should cover quality, risk, review, traceability, and next actions.',
          expected_keywords: ['quality', 'risk', 'traceability'],
        },
        enabled: true,
      },
    ];
  }
  if (type === 'rag') {
    return [
      {
        case_id: 'project_memory_workflow',
        tool_name: 'rag.query',
        arguments: {
          collection: 'project-memory',
          question: 'workflow runtime human review resume',
          expected_keywords: ['workflow', 'review', 'resume'],
          limit: 5,
        },
        enabled: true,
      },
      {
        case_id: 'default_project_structure',
        tool_name: 'rag.query',
        arguments: {
          collection: 'default',
          question: 'project structure FastAPI LangGraph agents',
          expected_keywords: ['FastAPI', 'LangGraph', 'Agent'],
          limit: 5,
        },
        enabled: true,
      },
    ];
  }
  if (type === 'workflow') {
    return [
      {
        case_id: 'planner_reporter_smoke',
        tool_name: 'workflow.run',
        arguments: {
          workflow_name: 'benchmark_planner_reporter',
          input_text: 'Create a short governance summary for Jaycode.',
          nodes: [
            { id: 'plan', type: 'planner', name: 'Planner', config: {} },
            { id: 'report', type: 'reporter', name: 'Reporter', config: {} },
          ],
          edges: [{ source: 'plan', target: 'report' }],
          expected_nodes: ['plan', 'report'],
        },
        enabled: true,
      },
    ];
  }
  if (type === 'collaboration') {
    return [
      {
        case_id: 'collab_project_governance',
        tool_name: 'collaboration.run',
        arguments: {
          goal: 'Analyze Jaycode and produce project structure, code risk, knowledge, and governance suggestions.',
          project_path: projectPath,
          max_files: 80,
          require_human_review: true,
          expected_sections: ['Project', 'Code', 'RAG', 'Supervisor'],
          expected_risk_keywords: ['risk', 'review', 'governance', 'quality'],
        },
        enabled: true,
      },
    ];
  }
  return [
    {
      case_id: 'fs_read_readme',
      server_id: 'real_filesystem',
      tool_name: 'read_text_file',
      arguments: { path: `${projectPath}/README.md`, head: 5 },
      enabled: true,
    },
    {
      case_id: 'fs_list_project',
      server_id: 'real_filesystem',
      tool_name: 'list_directory',
      arguments: { path: projectPath },
      enabled: true,
    },
    {
      case_id: 'fs_search_mcp',
      server_id: 'real_filesystem',
      tool_name: 'search_files',
      arguments: {
        path: projectPath,
        pattern: '**/*mcp*.py',
        excludePatterns: ['**/.venv/**', '**/node_modules/**', '**/__pycache__/**'],
      },
      enabled: true,
    },
    {
      case_id: 'memory_search_project',
      server_id: 'real_memory',
      tool_name: 'search_nodes',
      arguments: { query: 'Jaycode' },
      enabled: true,
    },
    {
      case_id: 'memory_read_graph',
      server_id: 'real_memory',
      tool_name: 'read_graph',
      arguments: {},
      enabled: true,
    },
  ];
}

function benchmarkTypeLabel(type: BenchmarkType) {
  const labels: Record<BenchmarkType, string> = {
    mcp: 'MCP',
    llm: 'LLM',
    rag: 'RAG',
    workflow: 'Workflow',
    collaboration: 'Collab',
  };
  return labels[type];
}

function benchmarkName(type: BenchmarkType) {
  const names: Record<BenchmarkType, string> = {
    mcp: 'MCP Tool Benchmark',
    llm: 'LLM Prompt/Model Benchmark',
    rag: 'RAG Retrieval Benchmark',
    workflow: 'Workflow Runtime Benchmark',
    collaboration: 'Multi-Agent Collaboration Benchmark',
  };
  return names[type];
}

function benchmarkMetricItems(type: BenchmarkType, summary: Record<string, unknown>) {
  const pct = (value: unknown) => `${Math.round(Number(value ?? 0) * 100)}%`;
  const base = [
    { label: 'success', value: pct(summary.success_rate) },
    { label: 'avg latency', value: `${summary.avg_latency_ms ?? 0}ms` },
    { label: 'p95 latency', value: `${summary.p95_latency_ms ?? 0}ms` },
    { label: 'failures', value: String(summary.failed ?? 0) },
  ];
  if (type === 'llm') {
    return [
      { label: 'quality', value: String(summary.avg_quality_score ?? 0) },
      { label: 'fallback', value: pct(summary.fallback_rate) },
      { label: 'tokens', value: String(summary.total_tokens ?? 0) },
      { label: 'cost', value: `$${Number(summary.estimated_cost_usd ?? 0).toFixed(6)}` },
    ];
  }
  if (type === 'rag') {
    return [
      { label: 'hit rate', value: pct(summary.hit_rate) },
      { label: 'source quality', value: String(summary.avg_source_quality ?? 0) },
      { label: 'avg results', value: String(summary.avg_result_count ?? 0) },
      { label: 'failures', value: String(summary.failed ?? 0) },
    ];
  }
  if (type === 'workflow') {
    return [
      { label: 'workflow ok', value: pct(summary.workflow_success_rate) },
      { label: 'failed nodes', value: String(summary.failed_node_count ?? 0) },
      { label: 'avg nodes', value: String(summary.avg_completed_nodes ?? 0) },
      { label: 'p95 latency', value: `${summary.p95_latency_ms ?? 0}ms` },
    ];
  }
  if (type === 'collaboration') {
    return [
      { label: 'completeness', value: String(summary.avg_completeness_score ?? 0) },
      { label: 'risk score', value: pct(summary.avg_risk_detection_score) },
      { label: 'review trigger', value: pct(summary.human_review_trigger_rate) },
      { label: 'p95 latency', value: `${summary.p95_latency_ms ?? 0}ms` },
    ];
  }
  return base;
}

function summarizeMcpLogInput(log: McpToolCallLog) {
  return summarizeValue(log.input) || '无参数';
}

function summarizeMcpLogOutput(log: McpToolCallLog) {
  if (log.error_message) return firstLine(log.error_message);
  const result = log.output?.result;
  if (result && typeof result === 'object') {
    const data = result as Record<string, unknown>;
    const content = data.content;
    if (Array.isArray(content)) {
      const text = content
        .map((item) => (item && typeof item === 'object' ? String((item as Record<string, unknown>).text ?? '') : ''))
        .filter(Boolean)
        .join('\n');
      if (text) return firstLine(text);
    }
    if (data.structuredContent) return summarizeValue(data.structuredContent);
  }
  return summarizeValue(log.output) || '无输出';
}

function ChatPage({
  chatInput,
  chatMessages,
  chatMode,
  chatSources,
  knowledgeDocs,
  knowledgeNote,
  memories,
  learningPlans,
  latestTaskId,
  tasks,
  selectedTaskId,
  onChatInputChange,
  onChatModeChange,
  onKnowledgeNoteChange,
  onMemoryConfirm,
  onMemoryDelete,
  onMemoryReject,
  onLearningPlanStatus,
  onOpenTask,
  onRefreshTasks,
  onSaveKnowledgeNote,
  onSend,
}: {
  chatInput: string;
  chatMessages: ChatMessage[];
  chatMode: ChatMode;
  chatSources: RagResult[];
  knowledgeDocs: RagDocument[];
  knowledgeNote: string;
  memories: MemoryRecord[];
  learningPlans: LearningPlanRecord[];
  latestTaskId: string;
  tasks: TaskSummary[];
  selectedTaskId: string;
  onChatInputChange: (value: string) => void;
  onChatModeChange: (mode: ChatMode) => void;
  onKnowledgeNoteChange: (value: string) => void;
  onMemoryConfirm: (memoryId: string) => void;
  onMemoryDelete: (memoryId: string) => void;
  onMemoryReject: (memoryId: string) => void;
  onLearningPlanStatus: (planId: string, status: LearningPlanRecord['status']) => void;
  onOpenTask: (taskId: string) => void;
  onRefreshTasks: () => void;
  onSaveKnowledgeNote: () => void;
  onSend: () => void;
}) {
  const modeLabels: Array<{ mode: ChatMode; label: string }> = [
    { mode: 'task', label: '任务追问' },
    { mode: 'knowledge', label: '知识库' },
    { mode: 'coach', label: '学习陪练' },
  ];
  return (
    <section className="page-grid chat-page">
      <div className="panel chat-sidebar">
        <PanelTitle icon={<MessageSquare size={17} />} title="追问上下文" action={<button className="icon-button" onClick={onRefreshTasks}><RefreshCw size={15} /></button>} />
        <div className="chat-mode-list">
          {modeLabels.map((item) => (
            <button key={item.mode} className={chatMode === item.mode ? 'active' : ''} onClick={() => onChatModeChange(item.mode)}>
              {item.label}
            </button>
          ))}
        </div>
        <div className="chat-current">
          <strong>当前任务</strong>
          <p>{latestTaskId || '未选择任务'}</p>
        </div>
        <MemoryPanel memories={memories} onConfirm={onMemoryConfirm} onReject={onMemoryReject} onDelete={onMemoryDelete} />
        <TaskList tasks={tasks.slice(0, 10)} selectedTaskId={selectedTaskId} onOpen={onOpenTask} />
      </div>

      <div className="panel chat-main">
        <PanelTitle icon={<MessageSquare size={17} />} title="项目交互追问" />
        <div className="chat-messages">
          {chatMessages.length ? (
            chatMessages.map((message, index) => (
              <div className={`chat-bubble ${message.role}`} key={`${message.role}-${index}`}>
                {message.role === 'assistant' && message.source ? (
                  <div className="answer-meta">
                    <span>{message.source === 'llm' ? 'LLM 回答' : 'fallback 回答'}</span>
                    {message.day || message.theme ? <span>Day {message.day ?? '-'} · {message.theme ?? '未命名主题'}</span> : null}
                  </div>
                ) : null}
                <MarkdownView text={message.content} />
              </div>
            ))
          ) : (
            <div className="chat-empty">
              <strong>开始追问项目</strong>
              <p>选择左侧的任务和追问类型，然后询问项目结构、风险来源、知识库内容或学习路线。</p>
            </div>
          )}
        </div>
        <div className="chat-composer">
          <textarea value={chatInput} onChange={(event) => onChatInputChange(event.target.value)} />
          <FieldHelp>输入你想追问的问题；任务追问结合当前任务，知识库模式检索 project-memory，陪练模式会继续追问。</FieldHelp>
          <button className="primary" onClick={onSend}>发送追问</button>
        </div>
      </div>

      <div className="panel chat-sources">
        <PanelTitle
          icon={chatMode === 'coach' ? <BookOpen size={17} /> : <Database size={17} />}
          title={chatMode === 'task' ? '任务上下文' : chatMode === 'knowledge' ? '知识库内容' : '学习陪练计划'}
        />
        <div className="source-list">
          {chatMode === 'task' ? (
            <div className="context-box">
              <strong>当前任务</strong>
              <p>{latestTaskId || '未选择任务'}</p>
            </div>
          ) : null}
          {chatMode === 'knowledge' ? (
            <div className="knowledge-save-box">
              <strong>project-memory</strong>
              <p>{knowledgeDocs.length} documents saved</p>
              <textarea
                value={knowledgeNote}
                onChange={(event) => onKnowledgeNoteChange(event.target.value)}
                placeholder="保存人工判断、模块说明或复盘结论"
              />
              <button className="secondary" onClick={onSaveKnowledgeNote}>保存知识笔记</button>
            </div>
          ) : null}
          {chatMode === 'coach' ? <LearningPlanList plans={learningPlans} latestTaskId={latestTaskId} onStatus={onLearningPlanStatus} /> : null}
          {chatMode !== 'coach' && chatSources.length ? (
            chatSources.map((source) => (
              <div className="source-item" key={`${source.chunk_id}-${source.path}`}>
                <strong>{source.path ?? 'source'}</strong>
                <small>{source.chunk_id}</small>
                <p>{firstLine(source.content)}</p>
              </div>
            ))
          ) : chatMode !== 'coach' ? (
            <p className="empty-text">{chatMode === 'task' ? '任务追问后，这里会显示引用到的任务报告和知识线索。' : '知识库检索后，这里会显示 project-memory 命中的内容。'}</p>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function MemoryPanel({
  memories,
  onConfirm,
  onReject,
  onDelete,
}: {
  memories: MemoryRecord[];
  onConfirm: (memoryId: string) => void;
  onReject: (memoryId: string) => void;
  onDelete: (memoryId: string) => void;
}) {
  const candidates = memories.filter((item) => item.status === 'candidate').slice(0, 4);
  const confirmed = memories.filter((item) => item.status === 'confirmed').slice(0, 3);
  const conflictContent = (memory: MemoryRecord) => memories.find((item) => item.memory_id === memory.conflict_with)?.content;
  return (
    <div className="memory-panel">
      <strong>Long-term memory</strong>
      <p>{candidates.length} candidates / {confirmed.length} confirmed</p>
      {candidates.map((memory) => (
        <article className="memory-candidate" key={memory.memory_id}>
          <span>{memory.memory_type} · quality {Math.round(memory.quality_score ?? 0)} · {memory.extraction_source === 'llm' ? 'LLM' : 'rule'}</span>
          <p>{memory.content}</p>
          <small>{memory.retention_policy === 'stable' ? 'Stable memory' : `Review by ${memory.expires_at ?? 'later'}`}</small>
          {memory.conflict_with ? <small className="memory-conflict">Will replace: {conflictContent(memory) ?? 'an existing preference'}</small> : null}
          <div>
            <button className="secondary" onClick={() => onConfirm(memory.memory_id)}>Confirm</button>
            <button className="icon-button" title="Reject memory" onClick={() => onReject(memory.memory_id)}><X size={14} /></button>
          </div>
        </article>
      ))}
      {confirmed.map((memory) => (
        <div className="memory-confirmed" key={memory.memory_id}>
          <div>
            <span>{memory.content}</span>
            {memory.conflict_with ? <small className="memory-conflict">Replaced: {conflictContent(memory) ?? 'an existing preference'}</small> : null}
          </div>
          <button className="icon-button" title="Delete memory" onClick={() => onDelete(memory.memory_id)}><Trash2 size={13} /></button>
        </div>
      ))}
      {!candidates.length && !confirmed.length ? <small>Explicit preferences from conversation appear here for confirmation.</small> : null}
    </div>
  );
}

function LearningPlanList({
  latestTaskId,
  plans,
  onStatus,
}: {
  latestTaskId: string;
  plans: LearningPlanRecord[];
  onStatus: (planId: string, status: LearningPlanRecord['status']) => void;
}) {
  const [expandedId, setExpandedId] = useState('');
  const ordered = [...plans]
    .sort((a, b) => Number(b.task_id === latestTaskId) - Number(a.task_id === latestTaskId))
    .slice(0, 8);
  return (
    <div className="learning-plan-box">
      <strong>学习计划</strong>
      <p>{plans.length} plans saved</p>
      <div className="learning-plan-list">
        {ordered.map((plan) => (
          <div className="learning-plan-item" key={plan.plan_id}>
            <div>
              <span>{plan.topic}</span>
              <small>{plan.status} · {plan.level} · {plan.plan.length} days</small>
            </div>
            <div className="learning-plan-actions">
              {plan.status !== 'completed' ? (
                <button onClick={() => onStatus(plan.plan_id, 'completed')}>完成</button>
              ) : (
                <button onClick={() => onStatus(plan.plan_id, 'active')}>继续</button>
              )}
              <button onClick={() => onStatus(plan.plan_id, 'paused')}>暂停</button>
              <button onClick={() => setExpandedId(expandedId === plan.plan_id ? '' : plan.plan_id)}>
                {expandedId === plan.plan_id ? '收起' : '详情'}
              </button>
            </div>
            {expandedId === plan.plan_id ? (
              <div className="learning-plan-detail">
                <MarkdownView text={plan.report_markdown} />
              </div>
            ) : null}
          </div>
        ))}
        {!ordered.length ? <p className="empty-text">点击人工审核里的“学习任务”后，这里会保存学习计划。</p> : null}
      </div>
    </div>
  );
}

function InteractionPanel({
  askQuestion,
  askResult,
  coachAnswer,
  coachReply,
  knowledgeDocs,
  knowledgeNote,
  knowledgeQuestion,
  knowledgeResults,
  suggestions,
  onAsk,
  onAskQuestionChange,
  onCoachAnswerChange,
  onCoachChat,
  onKnowledgeNoteChange,
  onKnowledgeQuestionChange,
  onQueryKnowledge,
  onSaveKnowledgeNote,
}: {
  askQuestion: string;
  askResult: AskResponse | null;
  coachAnswer: string;
  coachReply: LearningChatResponse | null;
  knowledgeDocs: RagDocument[];
  knowledgeNote: string;
  knowledgeQuestion: string;
  knowledgeResults: RagResult[];
  suggestions: string[];
  onAsk: () => void;
  onAskQuestionChange: (value: string) => void;
  onCoachAnswerChange: (value: string) => void;
  onCoachChat: () => void;
  onKnowledgeNoteChange: (value: string) => void;
  onKnowledgeQuestionChange: (value: string) => void;
  onQueryKnowledge: () => void;
  onSaveKnowledgeNote: () => void;
}) {
  const fallbackSuggestions = ['保存高频 Workflow 为模板', '给关键节点增加人工审核', '把项目理解结论沉淀到 project-memory'];
  return (
    <div className="interaction-panel">
      <section>
        <h3>优化建议</h3>
        <ul>
          {(suggestions.length ? suggestions : fallbackSuggestions).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>

      <section>
        <h3>追问项目</h3>
        <textarea value={askQuestion} onChange={(event) => onAskQuestionChange(event.target.value)} />
        <button className="secondary" onClick={onAsk}>基于报告追问</button>
        {askResult ? (
          <>
            <div className="answer-meta">
              <span>{askResult.answer_source === 'llm' ? 'LLM 回答' : 'fallback 回答'}</span>
            </div>
            <MarkdownView text={askResult.answer} />
          </>
        ) : null}
      </section>

      <section>
        <h3>项目知识库</h3>
        <input value={knowledgeQuestion} onChange={(event) => onKnowledgeQuestionChange(event.target.value)} />
        <button className="secondary" onClick={onQueryKnowledge}>检索 project-memory</button>
        <textarea value={knowledgeNote} onChange={(event) => onKnowledgeNoteChange(event.target.value)} placeholder="把人工判断、模块说明或学习结论保存为知识" />
        <button className="secondary" onClick={onSaveKnowledgeNote}>保存知识笔记</button>
        <p>{knowledgeDocs.length} documents in project-memory</p>
        {knowledgeResults.map((item) => (
          <p key={`${item.chunk_id}-${item.path}`}><strong>{item.path}</strong>: {firstLine(item.content)}</p>
        ))}
      </section>

      <section>
        <h3>学习陪练</h3>
        <textarea value={coachAnswer} onChange={(event) => onCoachAnswerChange(event.target.value)} placeholder="写下你对项目结构的理解，学习陪练会继续追问" />
        <button className="secondary" onClick={onCoachChat}>提交陪练回答</button>
        {coachReply ? (
          <>
            <p>{coachReply.reply}</p>
            {coachReply.next_questions.map((item) => <p key={item}>Q: {item}</p>)}
          </>
        ) : null}
      </section>
    </div>
  );
}

function TaskList({ tasks, selectedTaskId, onOpen }: { tasks: TaskSummary[]; selectedTaskId: string; onOpen: (taskId: string) => void }) {
  return (
    <div className="task-list">
      {tasks.map((task) => (
        <button key={task.task_id} className={task.task_id === selectedTaskId ? 'active' : ''} onClick={() => onOpen(task.task_id)}>
          <span>{task.goal}</span>
          <small>{task.status}</small>
        </button>
      ))}
    </div>
  );
}

function ReportTabs({ active, onChange }: { active: ReportTab; onChange: (value: ReportTab) => void }) {
  const tabs: Array<{ value: ReportTab; label: string }> = [
    { value: 'final', label: '最终报告' },
    { value: 'mentor', label: '架构导师视角' },
    { value: 'mermaid', label: 'Mermaid 图' },
    { value: 'governance', label: '治理建议' },
  ];
  return (
    <div className="report-tabs">
      {tabs.map((tab) => (
        <button key={tab.value} className={active === tab.value ? 'active' : ''} onClick={() => onChange(tab.value)}>
          {tab.label}
        </button>
      ))}
    </div>
  );
}

function GovernanceView({
  compact = false,
  riskLevel,
  reviewRequired,
  nextActions,
  suggestions,
  suggestionRecords,
}: {
  compact?: boolean;
  riskLevel: string;
  reviewRequired: boolean;
  nextActions: string[];
  suggestions: string[];
  suggestionRecords: SuggestionRecord[];
}) {
  const fallbackSuggestions = ['保存高频 Workflow 为模板', '给关键节点增加人工审核', '把项目理解结论沉淀到 project-memory'];
  return (
    <div className={`governance-view ${compact ? 'compact' : ''}`}>
      <div className="governance-summary-row">
        <span className={`risk-badge ${riskLevel}`}>risk_level: {riskLevel}</span>
        <span className={`review-badge ${reviewRequired ? 'required' : ''}`}>
          review_required: {reviewRequired ? 'true' : 'false'}
        </span>
      </div>
      <section>
        <h3>next_actions</h3>
        <ul className="suggestion-list">
          {(nextActions.length ? nextActions : suggestions.length ? suggestions : fallbackSuggestions).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>
      {!compact ? (
        <section>
          <h3>finding 绑定建议与测试用例</h3>
          <div className="finding-suggestion-list">
            {suggestionRecords.length ? (
              suggestionRecords.map((record) => <FindingSuggestionCard key={record.id ?? record.action} record={record} />)
            ) : (
              <p className="empty-text">本次任务还没有结构化 finding 绑定建议；运行 Code Review 或 Collab 后会展示。</p>
            )}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function FindingSuggestionCard({ record }: { record: SuggestionRecord }) {
  const finding = record.finding ?? {};
  const path = typeof finding.path === 'string' ? finding.path : 'project';
  const line = typeof finding.line === 'number' || typeof finding.line === 'string' ? finding.line : '';
  const message = typeof finding.message === 'string' ? finding.message : 'general governance item';
  return (
    <article className="finding-suggestion-card">
      <header>
        <span>{record.risk_level ?? 'low'}</span>
        <strong>{path}{line ? `:${line}` : ''}</strong>
      </header>
      <p>{message}</p>
      <dl>
        <dt>action</dt>
        <dd>{record.action ?? '补充治理动作。'}</dd>
        <dt>test_case</dt>
        <dd>{record.test_case ?? '补充回归测试。'}</dd>
      </dl>
    </article>
  );
}

function extractMentorView(report: string) {
  const mentor = extractMarkdownSection(report, 'LLM 架构理解') || extractMarkdownSection(report, '架构');
  if (mentor) return mentor;
  return [
    '# 架构导师视角',
    '',
    '当前报告里还没有单独的架构导师段落。',
    '',
    '- 运行 Project Analyzer 或 Collab 模式后，如果 LLM 可用，会在这里提取 `LLM 架构理解`。',
    '- 如果暂时走 fallback，也可以先从最终报告里的 Agent Outputs 和 Detailed Agent Reports 理解结构。',
  ].join('\n');
}

function extractMarkdownSection(report: string, title: string) {
  if (!report) return '';
  const lines = report.split('\n');
  const start = lines.findIndex((line) => line.toLowerCase().includes(title.toLowerCase()));
  if (start < 0) return '';
  const section = [lines[start]];
  for (const line of lines.slice(start + 1)) {
    if (line.startsWith('## ') && section.length > 1) break;
    section.push(line);
  }
  return section.join('\n').trim();
}

function MarkdownView({ text }: { text: string }) {
  const blocks = parseMarkdown(text);
  return (
    <div className="markdown-view">
      {blocks.map((block, index) => {
        if (block.type === 'h1') return <h1 key={index}>{block.text}</h1>;
        if (block.type === 'h2') return <h2 key={index}>{block.text}</h2>;
        if (block.type === 'h3') return <h3 key={index}>{block.text}</h3>;
        if (block.type === 'list') {
          return (
            <ul key={index}>
              {block.items?.map((item) => <li key={item}>{renderInline(item)}</li>)}
            </ul>
          );
        }
        return <p key={index}>{renderInline(block.text)}</p>;
      })}
    </div>
  );
}

function MermaidDiagram({ source }: { source: string }) {
  const graph = parseMermaid(source);
  return (
    <div className="mermaid-visual">
      <svg viewBox={`0 0 ${graph.width} ${graph.height}`} role="img">
        <defs>
          <marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto" markerUnits="strokeWidth">
            <path d="M0,0 L0,6 L9,3 z" fill="#52748a" />
          </marker>
        </defs>
        {graph.edges.map((edge) => {
          const sourceNode = graph.nodes.find((node) => node.id === edge.source);
          const targetNode = graph.nodes.find((node) => node.id === edge.target);
          if (!sourceNode || !targetNode) return null;
          const x1 = sourceNode.x + sourceNode.width;
          const y1 = sourceNode.y + sourceNode.height / 2;
          const x2 = targetNode.x;
          const y2 = targetNode.y + targetNode.height / 2;
          return <path key={`${edge.source}-${edge.target}`} d={`M${x1} ${y1} C ${x1 + 48} ${y1}, ${x2 - 48} ${y2}, ${x2} ${y2}`} className="mermaid-edge" />;
        })}
        {graph.nodes.map((node) => (
          <g key={node.id}>
            <rect x={node.x} y={node.y} width={node.width} height={node.height} rx="8" className="mermaid-node" />
            <text x={node.x + node.width / 2} y={node.y + node.height / 2 + 5} textAnchor="middle">
              {node.label}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

function deriveModules(files: string[]) {
  const modules = new Set<string>();
  for (const file of files) {
    const parts = file.split('/').filter(Boolean);
    if (parts.length > 1) modules.add(parts[0]);
  }
  return [...modules].sort((a, b) => a.localeCompare(b));
}

function joinProjectPath(root: string, child: string) {
  const normalizedRoot = root.replace(/[\\/]+$/, '');
  return `${normalizedRoot}/${child}`;
}

function buildFocusedFileWorkflow(filePath: string): WorkflowNode[] {
  return [
    { id: 'plan_focus', type: 'planner', name: 'Focus Planner', x: 64, y: 92, config: {} },
    {
      id: 'review_focus_file',
      type: 'agent',
      name: 'File Review Agent',
      x: 292,
      y: 92,
      config: { agent_type: 'file_reviewer', file_path: filePath, max_chars: 20000 },
    },
    { id: 'report_focus_file', type: 'reporter', name: 'Focus Reporter', x: 520, y: 92, config: {} },
  ];
}

function normalizeNodes(nodes: WorkflowNode[]): WorkflowNode[] {
  return (nodes ?? []).map((node, index) => ({
    ...node,
    x: Number.isFinite(node.x) ? node.x : 64 + index * 228,
    y: Number.isFinite(node.y) ? node.y : 92,
    config: node.config ?? {},
  }));
}

function edgeKeyFor(edge: WorkflowEdge) {
  return `${edge.source}->${edge.target}:${edge.condition ?? 'always'}:${edge.value ?? ''}:${edge.source_path ?? ''}`;
}

function buildLocalMermaid(nodes: WorkflowNode[], edges: WorkflowEdge[]) {
  const lines = ['flowchart LR', ...nodes.map((node) => `  ${node.id}[${node.name}]`)];
  for (const edge of edges) {
    const label = edge.condition && edge.condition !== 'always' ? `|${edge.condition}${edge.value ? `: ${edge.value}` : ''}|` : '';
    lines.push(`  ${edge.source} -->${label} ${edge.target}`);
  }
  return lines.join('\n');
}

function firstLine(value?: string) {
  return (value ?? '').split('\n')[0].slice(0, 140);
}

function deriveToolCalls(events: AgentEvent[]): ToolCall[] {
  return events
    .filter((event) => event.status === 'completed' && event.data?.node_type === 'mcp_tool')
    .map((event) => ({
      node_id: String(event.data?.node_id ?? event.node ?? ''),
      tool_name: String(event.data?.node_name ?? event.agent ?? 'tool'),
      status: event.status,
      result: event.data?.output,
    }));
}

function deriveAgentOutputs(events: AgentEvent[]): AgentOutput[] {
  return events
    .filter((event) => event.status === 'completed' && event.data?.node_type !== 'mcp_tool')
    .filter((event) => Boolean(event.content))
    .map((event) => ({
      node_id: String(event.data?.node_id ?? event.node ?? ''),
      node_name: String(event.data?.node_name ?? event.node ?? event.type ?? 'node'),
      agent: String(event.agent ?? event.data?.node_type ?? 'agent'),
      content: event.content,
    }));
}

function formatToolCall(item: ToolCall) {
  const detail = summarizeValue(item.result);
  return `${item.tool_name ?? 'tool'}: ${item.status ?? 'done'}${detail ? ` - ${detail}` : ''}`;
}

function formatAgentOutput(item: AgentOutput) {
  return `${item.node_name ?? item.agent ?? 'Agent'}: ${firstLine(item.content)}`;
}

function extractTaskResultArtifact(artifacts: Array<{ artifact_type: string; name: string; content?: unknown }>): Partial<TaskResultPayload> {
  const graphResult = [...artifacts]
    .reverse()
    .find((artifact) => artifact.artifact_type === 'graph_result' && artifact.name === 'result');
  if (graphResult?.content && typeof graphResult.content === 'object') {
    return graphResult.content as Partial<TaskResultPayload>;
  }
  const governance = [...artifacts].reverse().find((artifact) => artifact.artifact_type === 'governance');
  if (governance?.content && typeof governance.content === 'object') {
    const content = governance.content as Partial<TaskResultPayload>;
    return {
      governance: content.governance,
      risk_level: content.risk_level ?? content.governance?.risk_level,
      review_required: content.review_required ?? content.governance?.review_required,
      next_actions: content.next_actions ?? content.governance?.next_actions,
      suggestion_records: content.suggestion_records,
      suggestions: content.suggestions,
    };
  }
  return {};
}

function extractResumeSnapshots(artifacts: Array<{ artifact_type: string; name: string; content?: unknown }>): ResumeSnapshot[] {
  return artifacts
    .filter((artifact) => artifact.artifact_type === 'workflow_resume' && artifact.content && typeof artifact.content === 'object')
    .map((artifact) => artifact.content as ResumeSnapshot);
}

function deriveResumeSnapshots(events: AgentEvent[]): ResumeSnapshot[] {
  const records: ResumeSnapshot[] = [];
  for (let index = 0; index < events.length; index += 1) {
    const event = events[index];
    if (event.node !== 'workflow_resume' || event.status !== 'running') continue;
    const endIndex = events.findIndex((item, offset) => offset > index && item.node === 'workflow_resume' && item.status !== 'running');
    const afterEvents = events.slice(index + 1, endIndex > -1 ? endIndex : undefined);
    records.push({
      task_id: event.task_id,
      resumed_from: String(event.data?.paused_node_id ?? ''),
      action: 'approved',
      status: endIndex > -1 ? events[endIndex].status : 'running',
      before_state: {},
      after_events: afterEvents,
      created_at: event.timestamp,
    });
  }
  return records;
}

function summarizeResumeState(state?: Record<string, unknown>): string[] {
  if (!state) return [];
  const outputs = state.outputs && typeof state.outputs === 'object' ? Object.keys(state.outputs as Record<string, unknown>) : [];
  const suggestions = Array.isArray(state.suggestions) ? state.suggestions.length : 0;
  const toolCalls = Array.isArray(state.tool_calls) ? state.tool_calls.length : 0;
  const agentOutputs = Array.isArray(state.agent_outputs) ? state.agent_outputs.length : 0;
  return [
    state.workflow_name ? `workflow: ${String(state.workflow_name)}` : '',
    state.goal ? `goal: ${String(state.goal).slice(0, 90)}` : '',
    state.current ? `current: ${summarizeValue(state.current)}` : '',
    outputs.length ? `outputs: ${outputs.join(', ')}` : 'outputs: empty',
    `tool_calls: ${toolCalls}`,
    `agent_outputs: ${agentOutputs}`,
    `suggestions: ${suggestions}`,
    state.review_retries && typeof state.review_retries === 'object'
      ? `review_retries: ${JSON.stringify(state.review_retries).slice(0, 90)}`
      : '',
  ].filter(Boolean);
}

function summarizeValue(value: unknown) {
  if (!value || typeof value !== 'object') return value ? String(value).slice(0, 120) : '';
  const data = value as Record<string, unknown>;
  if (Array.isArray(data.files)) return `${data.files.length} files`;
  if (Array.isArray(data.commits)) return `${data.commits.length} commits`;
  if (Array.isArray(data.results)) return `${data.results.length} results`;
  if (typeof data.content === 'string') return firstLine(data.content);
  if (typeof data.root === 'string') return data.root;
  return JSON.stringify(data).slice(0, 120);
}

function parseMarkdown(text: string): Array<{ type: 'h1' | 'h2' | 'h3' | 'p' | 'list'; text: string; items?: string[] }> {
  const blocks: Array<{ type: 'h1' | 'h2' | 'h3' | 'p' | 'list'; text: string; items?: string[] }> = [];
  let listItems: string[] = [];
  const flushList = () => {
    if (listItems.length) {
      blocks.push({ type: 'list', text: '', items: listItems });
      listItems = [];
    }
  };

  for (const rawLine of text.split('\n')) {
    const line = rawLine.trim();
    if (!line) {
      flushList();
      continue;
    }
    if (line.startsWith('- ')) {
      listItems.push(line.slice(2));
      continue;
    }
    flushList();
    if (line.startsWith('### ')) blocks.push({ type: 'h3', text: line.slice(4) });
    else if (line.startsWith('## ')) blocks.push({ type: 'h2', text: line.slice(3) });
    else if (line.startsWith('# ')) blocks.push({ type: 'h1', text: line.slice(2) });
    else blocks.push({ type: 'p', text: line });
  }
  flushList();
  return blocks;
}

function renderInline(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, index) =>
    part.startsWith('**') && part.endsWith('**') ? <strong key={index}>{part.slice(2, -2)}</strong> : <span key={index}>{part}</span>,
  );
}

function parseMermaid(source: string) {
  const labels = new Map<string, string>();
  const edgeList: Array<{ source: string; target: string }> = [];
  for (const line of source.split('\n')) {
    const trimmed = line.trim();
    const nodeMatch = trimmed.match(/^([A-Za-z0-9_-]+)\[(.+)]$/);
    if (nodeMatch) labels.set(nodeMatch[1], nodeMatch[2]);
    const edgeMatch = trimmed.match(/^([A-Za-z0-9_-]+)\s*-->\s*([A-Za-z0-9_-]+)/);
    if (edgeMatch) edgeList.push({ source: edgeMatch[1], target: edgeMatch[2] });
  }
  for (const edge of edgeList) {
    if (!labels.has(edge.source)) labels.set(edge.source, edge.source);
    if (!labels.has(edge.target)) labels.set(edge.target, edge.target);
  }
  const nodes = Array.from(labels.entries()).map(([id, label], index) => ({
    id,
    label,
    x: 48 + index * 190,
    y: 78,
    width: 132,
    height: 52,
  }));
  return {
    nodes,
    edges: edgeList,
    width: Math.max(420, 96 + nodes.length * 190),
    height: 220,
  };
}
