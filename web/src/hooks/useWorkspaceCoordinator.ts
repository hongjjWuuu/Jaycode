import { useCallback, useEffect, useRef } from 'react';
import type { FormEvent } from 'react';
import type { FocusKind } from '../components/run/FocusPicker';
import type { ExecutionMode, SkillRecord, WorkflowEdge, WorkflowNode, WorkflowRecord } from '../types';
import { buildFocusedFileWorkflow, joinProjectPath } from '../utils/taskRuntime';
import { useGovernanceConsole } from './useGovernanceConsole';
import { useKnowledgeChat } from './useKnowledgeChat';
import { useTaskWorkspace } from './useTaskWorkspace';
import type { ViewKey } from './useViewNavigation';
import { useWorkflowEditor } from './useWorkflowEditor';

const modeHelp: Record<ExecutionMode, string> = {
  agent: '运行 Agent 模式', workflow: '运行当前画布', planner: '生成并运行 Workflow',
  collaboration: '运行多 Agent 协作', tool: '运行 Tool 模式', knowledge: '运行 Knowledge 模式',
};

type Options = { activeView: ViewKey; setActiveView: (view: ViewKey) => void; initialNodes: WorkflowNode[]; initialEdges: WorkflowEdge[] };

/** Cross-domain wiring only: feature hooks retain their own data and service boundaries. */
export function useWorkspaceCoordinator({ activeView, setActiveView, initialNodes, initialEdges }: Options) {
  const task = useTaskWorkspace();
  const workflow = useWorkflowEditor(initialNodes, initialEdges, task.events);
  const knowledge = useKnowledgeChat({ taskId: task.latestTaskId, fallbackGoal: task.goal, askTask: task.askCurrentTask, onNavigate: setActiveView });
  const governance = useGovernanceConsole();

  const initialized = useRef(false);
  useEffect(() => {
    // Hook return objects are intentionally recreated as their feature state changes.
    // Guard the initial fan-out so those renders cannot restart every request.
    if (initialized.current) return;
    initialized.current = true;
    Promise.all([
      task.refreshTasks(), workflow.refreshWorkflows(), knowledge.refreshLearningPlans(), knowledge.refreshMemories(),
      governance.refreshLlmTraces(), governance.refreshLlmGovernance(), governance.refreshMcp('real_filesystem'),
      governance.refreshSkills(), governance.refreshMarketplace(), governance.refreshBenchmarks('mcp'),
    ]).catch(() => undefined);
  }, [
    governance.refreshBenchmarks, governance.refreshLlmGovernance, governance.refreshLlmTraces,
    governance.refreshMarketplace, governance.refreshMcp, governance.refreshSkills,
    knowledge.refreshLearningPlans, knowledge.refreshMemories, task.refreshTasks, workflow.refreshWorkflows,
  ]);
  useEffect(() => {
    if (!['reports', 'chat', 'history'].includes(activeView) || task.selectedTaskId || !task.tasks.length) return;
    task.restoreTaskContext(task.tasks[0].task_id).then((result) => workflow.setWorkflowValidation(result.validation ?? null)).catch(() => undefined);
  }, [activeView, task.restoreTaskContext, task.selectedTaskId, task.tasks, workflow.setWorkflowValidation]);

  const navigate = useCallback((view: ViewKey) => {
    setActiveView(view);
    if (view === 'workflow' || view === 'skills' || view === 'marketplace') governance.refreshSkills(governance.selectedSkillCode).catch(() => undefined);
    if (view === 'marketplace') governance.refreshMarketplace().catch(() => undefined);
  }, [governance, setActiveView]);
  const runFollowUpTask = useCallback(async ({ mode, nextGoal, nextProjectPath = task.projectPath, nextMaxFiles = task.maxFiles, nextWorkflowName, nextNodes = [], nextEdges = [] }: { mode: ExecutionMode; nextGoal: string; nextProjectPath?: string; nextMaxFiles?: number; nextWorkflowName: string; nextNodes?: WorkflowNode[]; nextEdges?: WorkflowEdge[] }) => {
    task.setSelectedEvent(null); workflow.setWorkflowValidation(null); task.setGoal(nextGoal); task.setProjectPath(nextProjectPath); task.setMaxFiles(nextMaxFiles); task.setExecutionMode(mode); workflow.setWorkflowName(nextWorkflowName);
    if (mode === 'workflow') { workflow.setNodes(nextNodes); workflow.setEdges(nextEdges); workflow.setWorkflowDescription('Generated from human review follow-up action.'); }
    setActiveView('run');
    try {
      const result = await task.runTask({ goal: nextGoal, project_path: nextProjectPath, max_files: nextMaxFiles, require_human_review: task.requireReview, execution_mode: mode, workflow_name: nextWorkflowName, input_text: nextGoal, nodes: mode === 'workflow' ? nextNodes : [], edges: mode === 'workflow' ? nextEdges : [] });
      workflow.setWorkflowValidation(result?.validation ?? null);
      if (result?.planned_workflow) workflow.applyPlannedWorkflow(result.planned_workflow);
      await Promise.all([governance.refreshLlmTraces(), governance.refreshLlmGovernance()]);
    } catch { /* The task hook retains the compatible error state. */ }
  }, [governance, setActiveView, task, workflow]);
  const runCurrentTask = useCallback(async (event: FormEvent) => {
    event.preventDefault();
    if (task.executionMode === 'workflow') {
      const approvals = await governance.loadSkillApprovals();
      const blocked = workflow.nodes.filter((node) => node.type === 'skill' && !approvals.some((item) => item.skill_code === String(node.config.skill_code ?? '') && item.agent_code === String(node.config.agent_code ?? 'workflow_runner') && item.allowed));
      if (blocked.length) {
        task.setRunError(`Workflow 存在未审批的 Skill 节点：${blocked.map((node) => `${node.name}(${String(node.config.skill_code ?? '')}/${String(node.config.agent_code ?? 'workflow_runner')})`).join(', ')}。Workflow 只认 skill_code + workflow_runner 的审批记录。`);
        setActiveView('workflow'); return;
      }
    }
    await runFollowUpTask({ mode: task.executionMode, nextGoal: task.goal, nextProjectPath: task.projectPath, nextMaxFiles: task.maxFiles, nextWorkflowName: workflow.workflowName, nextNodes: task.executionMode === 'workflow' ? workflow.nodes : [], nextEdges: task.executionMode === 'workflow' ? workflow.edges : [] });
  }, [governance, runFollowUpTask, setActiveView, task, workflow]);
  const openTask = useCallback(async (taskId: string, view: ViewKey = 'history') => {
    const result = await task.restoreTaskContext(taskId); workflow.setWorkflowValidation(result.validation ?? null); setActiveView(view);
  }, [setActiveView, task, workflow]);
  const review = useCallback(async (action: 'approve' | 'reject' | 'revise') => {
    const result = await task.submitReview(action); workflow.setWorkflowValidation(result?.validation ?? null);
    await Promise.all([governance.refreshLlmTraces(), governance.refreshLlmGovernance()]);
  }, [governance, task, workflow]);
  const currentGoal = useCallback(() => task.tasks.find((item) => item.task_id === task.latestTaskId)?.goal || task.goal, [task.goal, task.latestTaskId, task.tasks]);
  const startDeepAnalysis = useCallback(async () => {
    const baseGoal = currentGoal();
    await task.recordReviewAction('rerun_analysis', { source_task_id: task.latestTaskId, mode: 'collaboration' });
    await runFollowUpTask({ mode: 'collaboration', nextGoal: [`深入分析：${baseGoal}`, `来源任务：${task.latestTaskId}`, task.reviewComment ? `人工审核意见：${task.reviewComment}` : '', '请通过多 Agent 协作重新分析项目结构、代码风险、知识沉淀点，并给出更具体的治理建议。'].filter(Boolean).join('\n'), nextWorkflowName: 'Deep Collaboration Review' });
    task.setReviewComment('');
  }, [currentGoal, runFollowUpTask, task]);
  const startLearningTask = useCallback(async () => {
    await task.recordReviewAction('learning_task', { source_task_id: task.latestTaskId });
    await knowledge.startLearning(task.reviewComment); await task.refreshTasks(); task.setReviewComment('');
  }, [knowledge, task]);
  const focusTarget = useCallback(async (kind: FocusKind, value: string) => {
    if (!task.latestTaskId || !value) return; task.closeFocusPicker(); const baseGoal = currentGoal();
    await task.recordReviewAction('focus_module', { ...(kind === 'module' ? { module: value } : { file: value }), source_task_id: task.latestTaskId });
    if (kind === 'module') {
      await runFollowUpTask({ mode: 'planner', nextGoal: [`聚焦模块分析：${value}`, `原始任务：${baseGoal}`, task.reviewComment ? `人工审核意见：${task.reviewComment}` : '', '只围绕该模块分析职责边界、关键文件、风险点和重构建议。'].filter(Boolean).join('\n'), nextProjectPath: joinProjectPath(task.projectPath, value), nextWorkflowName: `Focus Module - ${value}` }); return;
    }
    await runFollowUpTask({ mode: 'workflow', nextGoal: [`聚焦文件分析：${value}`, `原始任务：${baseGoal}`, task.reviewComment ? `人工审核意见：${task.reviewComment}` : '', '只读取并分析这个文件，输出职责、风险、依赖线索和后续追问。'].filter(Boolean).join('\n'), nextMaxFiles: 1, nextWorkflowName: `Focus File - ${value}`, nextNodes: buildFocusedFileWorkflow(value), nextEdges: [{ source: 'plan_focus', target: 'review_focus_file' }, { source: 'review_focus_file', target: 'report_focus_file' }] });
  }, [currentGoal, runFollowUpTask, task]);
  const reviewAction = useCallback(async (action: string, payload: Record<string, unknown> = {}) => {
    if (action === 'rerun_analysis') return startDeepAnalysis();
    if (action === 'focus_module') return task.openFocusPicker();
    if (action === 'learning_task') return startLearningTask();
    const result = await task.recordReviewAction(action, payload);
    if (action === 'save_knowledge') await knowledge.saveReviewKnowledge(result?.message ?? '', task.reviewComment || '人工审核');
    task.setReviewComment('');
  }, [knowledge, startDeepAnalysis, startLearningTask, task]);
  const addSkillToWorkflow = useCallback((skill: SkillRecord) => {
    const id = `skill_${Date.now()}`; const previous = workflow.nodes[workflow.nodes.length - 1];
    const node: WorkflowNode = { id, type: 'skill', name: skill.name, x: previous ? previous.x + 220 : 80, y: previous ? previous.y : 120, config: { skill_code: skill.code, agent_code: 'skill_console', input: skill.default_input ?? {} } };
    workflow.setNodes((items) => [...items, node]); if (previous) workflow.setEdges((items) => [...items, { source: previous.id, target: id }]); workflow.setSelectedNodeId(id); setActiveView('workflow');
  }, [setActiveView, workflow]);
  const openMarketplaceSkill = useCallback((code: string) => { governance.setSelectedSkillCode(code); governance.refreshSkills(code).catch(() => undefined); setActiveView('skills'); }, [governance, setActiveView]);
  const approveMarketplaceSkill = useCallback(async (code: string) => {
    const skill = governance.skills.find((item) => item.code === code); if (!skill) throw new Error(`Skill not found: ${code}`);
    await governance.updateSkillApproval(code, 'skill_console', true, 'Approved from Marketplace install result.');
    await governance.runSkill({ skill_code: code, agent_code: 'skill_console', input: skill.default_input ?? {}, task_id: task.latestTaskId || undefined }); openMarketplaceSkill(code);
  }, [governance, openMarketplaceSkill, task.latestTaskId]);
  const createMarketplaceWorkflow = useCallback(async (code: string) => {
    const skill = governance.skills.find((item) => item.code === code); if (!skill) throw new Error(`Skill not found: ${code}`);
    workflow.setNodes([{ id: `skill_${Date.now()}`, type: 'skill', name: skill.name, x: 120, y: 140, config: { skill_code: code, agent_code: 'workflow_runner', input: skill.default_input ?? {} } }]); workflow.setEdges([]); workflow.setSelectedNodeId(''); setActiveView('workflow'); await governance.refreshSkills(code);
  }, [governance, setActiveView, workflow]);

  return {
    activeStatus: task.running ? 'running' : task.latestStatus, navigate,
    focusPicker: { ...task.focusPicker, onClose: task.closeFocusPicker, onSelect: focusTarget },
    runPage: { goal: task.goal, projectPath: task.projectPath, maxFiles: task.maxFiles, requireReview: task.requireReview, running: task.running, submitLabel: modeHelp[task.executionMode], error: task.runError, events: task.events, latestTaskId: task.latestTaskId, latestStatus: task.latestStatus, workflowName: workflow.workflowName, workflowId: workflow.workflowId, workflows: workflow.savedWorkflows, taskNeedsReview: task.taskNeedsReview, reviewComment: task.reviewComment, resumeSnapshots: task.resumeSnapshots, selectedEvent: task.selectedEvent, toolCalls: task.visibleToolCalls, agentOutputs: task.visibleAgentOutputs, onReviewCommentChange: task.setReviewComment, onReview: review, onReviewAction: reviewAction, onGoalChange: task.setGoal, onProjectPathChange: task.setProjectPath, onMaxFilesChange: task.setMaxFiles, onRequireReviewChange: task.setRequireReview, onWorkflowSelect: (workflowId: string) => { const selected = workflow.savedWorkflows.find((item) => item.workflow_id === workflowId); if (selected) { workflow.loadWorkflow(selected); task.setExecutionMode('workflow'); } }, onWorkflowsRefresh: workflow.refreshWorkflows, onSubmit: runCurrentTask },
    workflowPage: { name: workflow.workflowName, description: workflow.workflowDescription, validation: workflow.workflowValidation, workflows: workflow.savedWorkflows, canvas: workflow.workflowCanvas, nodeConfig: { node: workflow.selectedNode, approvals: governance.skillApprovals, onNodeChange: workflow.updateSelectedNode, onConfigChange: workflow.updateSelectedConfig, onApproveSkill: async (code: string, agent: string) => governance.updateSkillApproval(code, agent, true, 'Approved from Workflow node config.'), onDelete: workflow.deleteSelectedNode }, edgeConfig: { edge: workflow.selectedEdge, nodes: workflow.nodes, onChange: workflow.updateSelectedEdge, onDelete: workflow.deleteSelectedEdge }, onNameChange: workflow.setWorkflowName, onDescriptionChange: workflow.setWorkflowDescription, onNew: workflow.createWorkflow, onAddNode: workflow.addNode, onSave: workflow.persistWorkflow, onValidate: workflow.checkWorkflow, onLoad: (item: WorkflowRecord) => { workflow.loadWorkflow(item); task.setExecutionMode('workflow'); setActiveView('workflow'); }, onDelete: workflow.deleteWorkflow, onRefresh: workflow.refreshWorkflows },
    reportsPage: { finalReport: task.finalReport, mermaid: task.mermaid, nodes: workflow.nodes, edges: workflow.edges, riskLevel: task.riskLevel, reviewRequired: task.reviewRequired, nextActions: task.nextActions, suggestions: task.suggestions, suggestionRecords: task.suggestionRecords, knowledgeDocumentCount: knowledge.knowledgeDocs.length, onOpenKnowledge: async () => { await knowledge.changeMode('knowledge'); setActiveView('chat'); } },
    chatPage: { chatInput: knowledge.chatInput, chatMessages: knowledge.chatMessages, chatMode: knowledge.chatMode, chatSources: knowledge.chatSources, knowledgeDocs: knowledge.knowledgeDocs, knowledgeNote: knowledge.knowledgeNote, memories: knowledge.memories, learningPlans: knowledge.learningPlans, latestTaskId: task.latestTaskId, tasks: task.tasks, selectedTaskId: task.selectedTaskId, onChatInputChange: knowledge.setChatInput, onChatModeChange: knowledge.changeMode, onKnowledgeNoteChange: knowledge.setKnowledgeNote, onMemoryConfirm: knowledge.confirm, onMemoryDelete: knowledge.remove, onMemoryReject: knowledge.reject, onLearningPlanStatus: async (id: string, status: Parameters<typeof knowledge.setPlanStatus>[1]) => { await knowledge.setPlanStatus(id, status); }, onOpenTask: (id: string) => openTask(id, 'chat'), onRefreshTasks: task.refreshTasks, onSaveKnowledgeNote: knowledge.saveKnowledgeNote, onSend: knowledge.send },
    historyPage: { tasks: task.tasks, selectedTaskId: task.selectedTaskId, events: task.events, finalReport: task.finalReport, onOpen: openTask, onRefresh: task.refreshTasks },
    operationsPage: { onOpenTask: (id: string) => openTask(id, 'history') },
    llmPage: { prompts: governance.llmPrompts, usage: governance.llmUsage, traces: governance.llmTraces, traceAgent: governance.llmTraceAgent, agentFilter: governance.llmAgentFilter, onAgentFilterChange: governance.changeLlmAgent, onTraceAgentChange: governance.changeLlmTraceAgent, onActivatePrompt: governance.activateLlmPrompt, onSavePrompt: governance.savePrompt, onRunAbTest: governance.runPromptAbTest, onRefresh: governance.refreshLlm },
    mcpPage: { projectPath: task.projectPath, status: governance.mcpStatus, servers: governance.mcpServers, tools: governance.mcpTools, logs: governance.mcpLogs, onRefresh: governance.refreshMcp, onSaveServer: governance.saveServer, onServerEnabled: governance.setServerEnabled, onDiscover: governance.discoverServer, onToolEnabled: governance.setToolEnabled, onApproveTool: governance.setToolApproval, onCallTool: governance.invokeTool },
    skillsPage: { plugins: governance.skillPlugins, skills: governance.skills, approvals: governance.skillApprovals, logs: governance.skillLogs, selectedSkillCode: governance.selectedSkillCode, projectPath: task.projectPath, onSelectSkill: openMarketplaceSkill, onRefresh: () => governance.refreshSkills(governance.selectedSkillCode), onSkillEnabled: governance.setSkillStatus, onSkillApproval: governance.updateSkillApproval, onExecuteSkill: (code: string, agent: string, input: Record<string, unknown>) => governance.runSkill({ skill_code: code, agent_code: agent, input, task_id: task.latestTaskId || undefined }), onAddToWorkflow: addSkillToWorkflow, onUninstallPlugin: governance.removeSkillPlugin },
    marketplacePage: { catalog: governance.marketplaceCatalog, installs: governance.marketplaceInstalls, preview: governance.marketplacePreview, lastInstall: governance.lastMarketplaceInstall, onRefresh: governance.refreshMarketplace, onPreview: governance.previewPackage, onInstall: async (url: string) => { const result = await governance.installPackage(url); await workflow.refreshWorkflows(); return result; }, onUninstall: governance.removePackage, onOpenSkill: openMarketplaceSkill, onApproveAndTestSkill: approveMarketplaceSkill, onCreateSkillWorkflow: createMarketplaceWorkflow },
    benchmarkPage: { benchmarkType: governance.benchmarkType, runs: governance.benchmarkRuns, selectedRun: governance.selectedBenchmark, running: governance.benchmarkRunning, error: governance.benchmarkError, onBenchmarkTypeChange: governance.changeBenchmarkType, onRun: governance.executeBenchmark, onOpen: governance.openBenchmark, onRefresh: () => governance.refreshBenchmarks(governance.benchmarkType) },
  };
}
