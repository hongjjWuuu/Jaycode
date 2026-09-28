import { useCallback, useMemo, useState } from 'react';
import {
  applyReviewAction, askTask, getTaskDetail, getTaskEvents, listTasks, reviewTask,
  runCollaborationTaskStream, runTaskStream, type TaskRunPayload,
} from '../services/tasks';
import { listProjectFiles } from '../services/projectFiles';
import type {
  AgentEvent, AgentOutput, ExecutionMode, ResumeSnapshot, SuggestionRecord, TaskResultPayload,
  TaskSummary, ToolCall,
} from '../types';
import {
  deriveAgentOutputs, deriveModules, deriveToolCalls, extractResumeSnapshots,
  extractTaskResultArtifact, formatAgentOutput, formatToolCall,
} from '../utils/taskRuntime';

type TaskPresentation = {
  finalReport: string; mermaid: string; suggestions: string[]; suggestionRecords: SuggestionRecord[];
  riskLevel: string; reviewRequired: boolean; nextActions: string[]; toolCalls: ToolCall[];
  agentOutputs: AgentOutput[]; resumeSnapshots: ResumeSnapshot[];
};

const emptyPresentation = (): TaskPresentation => ({
  finalReport: '', mermaid: '', suggestions: [], suggestionRecords: [], riskLevel: 'low',
  reviewRequired: false, nextActions: [], toolCalls: [], agentOutputs: [], resumeSnapshots: [],
});
const defaultProjectPath = '.';

/** Owns task lifecycle and the Run/History presentation state. */
export function useTaskWorkspace() {
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState('');
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [presentation, setPresentation] = useState<TaskPresentation>(emptyPresentation);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<unknown>('');
  const [executionMode, setExecutionMode] = useState<ExecutionMode>('workflow');
  const [goal, setGoal] = useState('分析这个项目并给出重构建议');
  const [projectPath, setProjectPath] = useState(defaultProjectPath);
  const [maxFiles, setMaxFiles] = useState(100);
  const [requireReview, setRequireReview] = useState(true);
  const [reviewComment, setReviewComment] = useState('');
  const [selectedEvent, setSelectedEvent] = useState<AgentEvent | null>(null);
  const [focusPickerOpen, setFocusPickerOpen] = useState(false);
  const [focusFiles, setFocusFiles] = useState<string[]>([]);
  const [focusLoading, setFocusLoading] = useState(false);
  const [focusError, setFocusError] = useState('');

  const latestTaskId = useMemo(() => [...events].reverse().find((event) => event.task_id)?.task_id ?? selectedTaskId, [events, selectedTaskId]);
  const latestStatus = useMemo(() => [...events].reverse().find((event) => event.status)?.status ?? 'idle', [events]);
  const visibleToolCalls = useMemo(() => (presentation.toolCalls.length ? presentation.toolCalls : deriveToolCalls(events)).map(formatToolCall), [events, presentation.toolCalls]);
  const visibleAgentOutputs = useMemo(() => (presentation.agentOutputs.length ? presentation.agentOutputs : deriveAgentOutputs(events)).map(formatAgentOutput), [events, presentation.agentOutputs]);
  const taskNeedsReview = latestStatus === 'waiting_review' || tasks.find((task) => task.task_id === latestTaskId)?.status === 'waiting_review';
  const focusModules = useMemo(() => deriveModules(focusFiles), [focusFiles]);

  const refreshTasks = useCallback(async () => setTasks(await listTasks()), []);
  const applyResult = useCallback((result: Partial<TaskResultPayload>, snapshots: ResumeSnapshot[] = []) => {
    setPresentation({
      finalReport: result.final_report ?? '', mermaid: result.mermaid ?? '', suggestions: result.suggestions ?? [],
      suggestionRecords: result.suggestion_records ?? [], riskLevel: result.risk_level ?? result.governance?.risk_level ?? 'low',
      reviewRequired: Boolean(result.review_required ?? result.governance?.review_required ?? result.human_review_required),
      nextActions: result.next_actions ?? result.governance?.next_actions ?? [], toolCalls: result.tool_calls ?? [],
      agentOutputs: result.agent_outputs ?? [], resumeSnapshots: snapshots,
    });
  }, []);
  const resetRunState = useCallback(() => { setRunning(true); setRunError(''); setEvents([]); setPresentation(emptyPresentation()); }, []);
  const consumeTaskPayload = useCallback((payload: AgentEvent | Record<string, unknown>): TaskResultPayload | null => {
    const type = String((payload as { type?: unknown }).type ?? '');
    if (type === 'task_result') { const result = payload as TaskResultPayload; setSelectedTaskId(result.task_id); applyResult(result); return result; }
    if (type === 'error') setRunError(String((payload as { content?: unknown }).content ?? '任务执行失败'));
    else if (type !== 'complete') setEvents((previous) => [...previous, payload as AgentEvent]);
    return null;
  }, [applyResult]);
  const runTask = useCallback(async (payload: TaskRunPayload): Promise<TaskResultPayload | null> => {
    resetRunState(); let result: TaskResultPayload | null = null;
    try {
      const stream = payload.execution_mode === 'collaboration' ? runCollaborationTaskStream : runTaskStream;
      await stream(payload, (event) => { result = consumeTaskPayload(event) ?? result; });
      await refreshTasks(); return result;
    } catch (error) { setRunError(error instanceof Error ? error.message : String(error)); throw error; }
    finally { setRunning(false); }
  }, [consumeTaskPayload, refreshTasks, resetRunState]);
  const restoreTaskContext = useCallback(async (taskId: string) => {
    setSelectedTaskId(taskId); setRunError(''); setPresentation(emptyPresentation()); setSelectedEvent(null);
    const [taskEvents, detail] = await Promise.all([getTaskEvents(taskId), getTaskDetail(taskId)]);
    const result = extractTaskResultArtifact(detail.artifacts); const snapshots = extractResumeSnapshots(detail.artifacts);
    setEvents(taskEvents); applyResult({ ...result, final_report: result.final_report ?? detail.task.final_report ?? '' }, snapshots);
    return result;
  }, [applyResult]);
  const submitReview = useCallback(async (action: 'approve' | 'reject' | 'revise') => {
    if (!latestTaskId) return null;
    try { await reviewTask(latestTaskId, action, reviewComment); await refreshTasks(); const result = await restoreTaskContext(latestTaskId); setReviewComment(''); return result; }
    catch (error) { setRunError(error instanceof Error ? error.message : String(error)); throw error; }
  }, [latestTaskId, refreshTasks, restoreTaskContext, reviewComment]);
  const recordReviewAction = useCallback(async (action: string, payload: Record<string, unknown> = {}) => {
    if (!latestTaskId) return null;
    const result = await applyReviewAction(latestTaskId, action, reviewComment, payload);
    await refreshTasks(); await restoreTaskContext(latestTaskId); return result;
  }, [latestTaskId, refreshTasks, restoreTaskContext, reviewComment]);
  const askCurrentTask = useCallback((question: string) => latestTaskId ? askTask(latestTaskId, question, 'project-memory') : Promise.reject(new Error('请先运行或选择一个历史任务，再进行任务追问。')), [latestTaskId]);
  const openFocusPicker = useCallback(async () => {
    setFocusPickerOpen(true); setFocusLoading(true); setFocusError('');
    try { setFocusFiles((await listProjectFiles(projectPath, Math.min(2000, Math.max(300, maxFiles * 4)))).files); }
    catch (error) { setFocusError(error instanceof Error ? error.message : String(error)); }
    finally { setFocusLoading(false); }
  }, [maxFiles, projectPath]);

  return {
    tasks, selectedTaskId, events, ...presentation, running, runError, executionMode, goal, projectPath, maxFiles,
    requireReview, reviewComment, selectedEvent, latestTaskId, latestStatus, taskNeedsReview, visibleToolCalls,
    visibleAgentOutputs, focusPicker: { open: focusPickerOpen, files: focusFiles, modules: focusModules, loading: focusLoading, error: focusError },
    refreshTasks, runTask, restoreTaskContext, submitReview, recordReviewAction, askCurrentTask, openFocusPicker,
    closeFocusPicker: () => setFocusPickerOpen(false), setRunError, setExecutionMode, setGoal, setProjectPath,
    setMaxFiles, setRequireReview, setReviewComment, setSelectedEvent,
  };
}
