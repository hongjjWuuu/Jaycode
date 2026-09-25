import { useCallback, useState } from 'react';
import {
  applyReviewAction, askTask, getTaskDetail, getTaskEvents, listTasks, reviewTask,
  runCollaborationTaskStream, runTaskStream,
  type TaskRunPayload,
} from '../services/tasks';
import { listProjectFiles } from '../services/projectFiles';
import type {
  AgentEvent, AgentOutput, ResumeSnapshot, SuggestionRecord, TaskResultPayload,
  TaskSummary, ToolCall,
} from '../types';
import { extractResumeSnapshots, extractTaskResultArtifact } from '../utils/taskRuntime';

type TaskPresentation = {
  finalReport: string;
  mermaid: string;
  suggestions: string[];
  suggestionRecords: SuggestionRecord[];
  riskLevel: string;
  reviewRequired: boolean;
  nextActions: string[];
  toolCalls: ToolCall[];
  agentOutputs: AgentOutput[];
  resumeSnapshots: ResumeSnapshot[];
};

const emptyPresentation = (): TaskPresentation => ({
  finalReport: '', mermaid: '', suggestions: [], suggestionRecords: [], riskLevel: 'low',
  reviewRequired: false, nextActions: [], toolCalls: [], agentOutputs: [], resumeSnapshots: [],
});

/** Shared task lifecycle for Run, Reports, Chat, and History without a global store. */
export function useTaskWorkspace() {
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState('');
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [presentation, setPresentation] = useState<TaskPresentation>(emptyPresentation);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<unknown>('');

  const refreshTasks = useCallback(async () => {
    setTasks(await listTasks());
  }, []);

  const applyResult = useCallback((result: Partial<TaskResultPayload>, snapshots: ResumeSnapshot[] = []) => {
    setPresentation({
      finalReport: result.final_report ?? '', mermaid: result.mermaid ?? '',
      suggestions: result.suggestions ?? [], suggestionRecords: result.suggestion_records ?? [],
      riskLevel: result.risk_level ?? result.governance?.risk_level ?? 'low',
      reviewRequired: Boolean(result.review_required ?? result.governance?.review_required ?? result.human_review_required),
      nextActions: result.next_actions ?? result.governance?.next_actions ?? [],
      toolCalls: result.tool_calls ?? [], agentOutputs: result.agent_outputs ?? [], resumeSnapshots: snapshots,
    });
  }, []);

  const resetRunState = useCallback(() => {
    setRunning(true);
    setRunError('');
    setEvents([]);
    setPresentation(emptyPresentation());
  }, []);

  const consumeTaskPayload = useCallback((payload: AgentEvent | Record<string, unknown>): TaskResultPayload | null => {
    const eventType = String((payload as { type?: unknown }).type ?? '');
    if (eventType === 'task_result') {
      const result = payload as TaskResultPayload;
      setSelectedTaskId(result.task_id);
      applyResult(result);
      return result;
    }
    if (eventType === 'error') setRunError(String((payload as { content?: unknown }).content ?? '任务执行失败'));
    else if (eventType !== 'complete') setEvents((previous) => [...previous, payload as AgentEvent]);
    return null;
  }, [applyResult]);

  const runTask = useCallback(async (payload: TaskRunPayload): Promise<TaskResultPayload | null> => {
    resetRunState();
    let taskResult: TaskResultPayload | null = null;
    try {
      const runner = payload.execution_mode === 'collaboration' ? runCollaborationTaskStream : runTaskStream;
      await runner(payload, (event) => { taskResult = consumeTaskPayload(event) ?? taskResult; });
      await refreshTasks();
      return taskResult as TaskResultPayload | null;
    } catch (error) {
      setRunError(error instanceof Error ? error.message : String(error));
      throw error;
    } finally {
      setRunning(false);
    }
  }, [consumeTaskPayload, refreshTasks, resetRunState]);

  const restoreTaskContext = useCallback(async (taskId: string) => {
    setSelectedTaskId(taskId);
    setRunError('');
    setPresentation(emptyPresentation());
    const [taskEvents, taskDetail] = await Promise.all([getTaskEvents(taskId), getTaskDetail(taskId)]);
    const result = extractTaskResultArtifact(taskDetail.artifacts);
    const snapshots = extractResumeSnapshots(taskDetail.artifacts);
    setEvents(taskEvents);
    applyResult({ ...result, final_report: result.final_report ?? taskDetail.task.final_report ?? '' }, snapshots);
    return result;
  }, [applyResult]);

  const submitReview = useCallback(async (taskId: string, action: 'approve' | 'reject' | 'revise', comment: string) => {
    try {
      await reviewTask(taskId, action, comment);
      await refreshTasks();
      return await restoreTaskContext(taskId);
    } catch (error) {
      setRunError(error instanceof Error ? error.message : String(error));
      throw error;
    }
  }, [refreshTasks, restoreTaskContext]);

  return {
    tasks, setTasks, selectedTaskId, setSelectedTaskId, events, setEvents,
    ...presentation, running, runError, setRunError, refreshTasks, resetRunState,
    runTask, consumeTaskPayload, restoreTaskContext, submitReview,
    getTaskDetail, getTaskEvents, reviewTask, applyReviewAction, askTask, listProjectFiles,
  };
}
