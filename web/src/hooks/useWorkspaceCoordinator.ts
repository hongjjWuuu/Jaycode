import type { WorkflowEdge, WorkflowNode } from '../types';
import { useGovernanceConsole } from './useGovernanceConsole';
import { useKnowledgeChat } from './useKnowledgeChat';
import { useTaskWorkspace } from './useTaskWorkspace';
import { useWorkflowEditor } from './useWorkflowEditor';

/**
 * Composition boundary for the four feature hooks. It owns no independent
 * state and deliberately performs no HTTP request itself.
 */
export function useWorkspaceCoordinator(initialNodes: WorkflowNode[], initialEdges: WorkflowEdge[]) {
  const taskWorkspace = useTaskWorkspace();
  return {
    taskWorkspace,
    workflowEditor: useWorkflowEditor(initialNodes, initialEdges, taskWorkspace.events),
    knowledgeChat: useKnowledgeChat(),
    governance: useGovernanceConsole(),
  };
}
