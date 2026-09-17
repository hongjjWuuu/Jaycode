import { useCallback, useState } from 'react';
import { listWorkflows, saveWorkflow, updateWorkflow, validateWorkflow } from '../services/workflows';
import type { WorkflowEdge, WorkflowNode, WorkflowRecord, WorkflowValidation } from '../types';

export function useWorkflowEditor(initialNodes: WorkflowNode[], initialEdges: WorkflowEdge[]) {
  const [workflowId, setWorkflowId] = useState('');
  const [workflowName, setWorkflowName] = useState('项目分析审核流');
  const [workflowDescription, setWorkflowDescription] = useState('Planner -> Agent -> Human Review -> Reporter');
  const [savedWorkflows, setSavedWorkflows] = useState<WorkflowRecord[]>([]);
  const [nodes, setNodes] = useState<WorkflowNode[]>(initialNodes);
  const [edges, setEdges] = useState<WorkflowEdge[]>(initialEdges);
  const [selectedNodeId, setSelectedNodeId] = useState('analyze');
  const [selectedEdgeKey, setSelectedEdgeKey] = useState('');
  const [connectFrom, setConnectFrom] = useState<string | null>(null);
  const [workflowValidation, setWorkflowValidation] = useState<WorkflowValidation | null>(null);

  const refreshWorkflows = useCallback(async () => setSavedWorkflows(await listWorkflows()), []);
  const persistWorkflow = useCallback(async () => {
    const payload = { name: workflowName, description: workflowDescription, nodes, edges };
    const saved = workflowId ? await updateWorkflow(workflowId, payload) : await saveWorkflow(payload);
    setWorkflowId(saved.workflow_id);
    await refreshWorkflows();
  }, [edges, nodes, refreshWorkflows, workflowDescription, workflowId, workflowName]);
  const checkWorkflow = useCallback(async () => {
    try { setWorkflowValidation(await validateWorkflow({ nodes, edges })); }
    catch (exc) {
      setWorkflowValidation({ valid: false, errors: [exc instanceof Error ? exc.message : String(exc)], warnings: [], node_count: nodes.length, edge_count: edges.length, parallel_sources: [] });
    }
  }, [edges, nodes]);

  return { workflowId, setWorkflowId, workflowName, setWorkflowName, workflowDescription, setWorkflowDescription,
    savedWorkflows, setSavedWorkflows, nodes, setNodes, edges, setEdges, selectedNodeId, setSelectedNodeId,
    selectedEdgeKey, setSelectedEdgeKey, connectFrom, setConnectFrom, workflowValidation, setWorkflowValidation,
    refreshWorkflows, persistWorkflow, checkWorkflow };
}
