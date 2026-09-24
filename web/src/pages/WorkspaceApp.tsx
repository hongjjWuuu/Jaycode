import {
  Activity,
  BarChart3,
  FileText,
  History,
  LayoutDashboard,
  MessageSquare,
  Puzzle,
  Workflow,
  Wrench,
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
import { FocusPicker, type FocusKind } from '../components/run/FocusPicker';
import { PageBoundary } from '../components/PageBoundary';
import { BenchmarkPage as BenchmarkConsolePage } from './BenchmarkPage';
import { ChatWorkspacePage as ChatConsolePage } from './ChatPage';
import { HistoryPage as HistoryWorkspacePage } from './HistoryPage';
import { LlmPage as LlmConsolePage } from './LlmPage';
import { MarketplacePage } from './MarketplacePage';
import { McpPage as McpConsolePage } from './McpPage';
import { ReportsPage as ReportsWorkspacePage } from './ReportsPage';
import { RunPage as RunWorkspacePage } from './RunPage';
import { SkillsPage as SkillsConsolePage } from './SkillsPage';
import { WorkflowPage as WorkflowWorkspacePage } from './WorkflowPage';

const defaultProjectPath = '.';
const dragPayloadMime = 'application/jaycode-node';

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
const RunFrame = ({ children }: { children: ReactNode }) => <PageBoundary name="run">{children}</PageBoundary>;
const WorkflowFrame = ({ children }: { children: ReactNode }) => <PageBoundary name="workflow">{children}</PageBoundary>;

const pageFrames: Record<ViewKey, ComponentType<{ children: ReactNode }>> = {
  run: RunFrame,
  workflow: WorkflowFrame,
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

  const workflowCanvas = {
    canvasRef,
    canvasSize,
    connectFrom,
    edges,
    nodes,
    nodeStatus,
    selectedNodeId,
    selectedEdgeKey,
    onCanvasPointerMove: handleCanvasPointerMove,
    onDrop: handleDrop,
    onEndPointer: endPointer,
    onStartCanvasPan: startCanvasPan,
    onStartMove: startMove,
    onSelectEdge: (edge: WorkflowEdge) => {
      setSelectedEdgeKey(edgeKeyFor(edge));
      setSelectedNodeId('');
    },
    onToggleConnect: toggleConnect,
  };

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
          <RunWorkspacePage
            goal={goal} projectPath={projectPath} maxFiles={maxFiles} requireReview={requireReview} running={running}
            submitLabel={modeHelp[executionMode].button} error={error} events={events} latestTaskId={latestTaskId}
            latestStatus={latestStatus} workflowName={workflowName} taskNeedsReview={taskNeedsReview}
            reviewComment={reviewComment} resumeSnapshots={resumeSnapshots} selectedEvent={selectedEvent}
            toolCalls={visibleToolCalls.map(formatToolCall)} agentOutputs={visibleAgentOutputs.map(formatAgentOutput)}
            onReviewCommentChange={setReviewComment} onReview={handleReview} onReviewAction={handleReviewAction}
            onGoalChange={setGoal} onProjectPathChange={setProjectPath} onMaxFilesChange={setMaxFiles} onRequireReviewChange={setRequireReview} onSubmit={handleRunTask}
          />
        ) : null}
        {activeView === 'workflow' ? (
          <WorkflowWorkspacePage
            name={workflowName} description={workflowDescription} validation={workflowValidation} workflows={savedWorkflows}
            canvas={workflowCanvas}
            nodeConfig={{ node: selectedNode, approvals: skillApprovals, onNodeChange: updateSelectedNode, onConfigChange: updateSelectedConfig, onApproveSkill: async (skillCode, agentCode) => handleSkillApproval(skillCode, agentCode, true, 'Approved from Workflow node config.'), onDelete: deleteSelectedNode }}
            edgeConfig={{ edge: edges.find((edge) => edgeKeyFor(edge) === selectedEdgeKey), nodes, onChange: (patch) => selectedEdgeKey && updateEdge(selectedEdgeKey, patch), onDelete: () => selectedEdgeKey && deleteEdge(selectedEdgeKey) }}
            onNameChange={setWorkflowName} onDescriptionChange={setWorkflowDescription} onSave={handleSaveWorkflow}
            onValidate={handleValidateWorkflow} onLoad={loadWorkflow} onRefresh={refreshWorkflows}
          />
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
            onOpenKnowledge={async () => { setChatMode('knowledge'); setActiveView('chat'); await handleQueryKnowledge(); }}
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
