import { useCallback, useState } from 'react';
import {
  applyReviewAction, askTask, getTaskDetail, getTaskEvents, listTasks, reviewTask,
  runCollaborationTaskStream, runTaskStream,
} from '../services/tasks';
import { listProjectFiles } from '../services/projectFiles';
import type { AgentEvent, TaskSummary } from '../types';

/** Shared task context for Run, Reports, Chat, and History without a global store. */
export function useTaskWorkspace() {
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState('');
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [finalReport, setFinalReport] = useState('');

  const refreshTasks = useCallback(async () => {
    setTasks(await listTasks());
  }, []);

  return {
    tasks, setTasks, selectedTaskId, setSelectedTaskId, events, setEvents,
    finalReport, setFinalReport, refreshTasks,
    runTaskStream, runCollaborationTaskStream, getTaskDetail, getTaskEvents,
    reviewTask, applyReviewAction, askTask, listProjectFiles,
  };
}
