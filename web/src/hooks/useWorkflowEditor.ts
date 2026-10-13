import { useCallback, useMemo, useRef, useState } from 'react';
import type { DragEvent, PointerEvent } from 'react';
import { deleteWorkflow as deleteSavedWorkflow, listWorkflows, saveWorkflow, updateWorkflow, validateWorkflow } from '../services/workflows';
import type { AgentEvent, NodeStatus, WorkflowEdge, WorkflowNode, WorkflowRecord, WorkflowValidation } from '../types';
import type { WorkflowCanvasProps } from '../components/workflow/WorkflowCanvas';
import { workflowNodeLabel } from '../utils/workflowNodes';

const dragPayloadMime = 'application/jaycode-node';
const edgeKey = (edge: WorkflowEdge) => `${edge.source}:${edge.target}:${edge.condition ?? 'always'}:${edge.value ?? ''}:${edge.source_path ?? ''}`;
const nodeTemplates: Record<string, Pick<WorkflowNode, 'type' | 'name' | 'config'>> = {
  planner: { type: 'planner', name: workflowNodeLabel('planner'), config: {} },
  agent: { type: 'agent', name: workflowNodeLabel('agent'), config: { agent_type: 'project_analyzer', max_files: 100 } },
  human_review: { type: 'human_review', name: workflowNodeLabel('human_review'), config: { require_comment: false } },
  reporter: { type: 'reporter', name: workflowNodeLabel('reporter'), config: {} },
  rag: { type: 'rag', name: workflowNodeLabel('rag'), config: { knowledge_scope: 'project', top_k: 5 } },
  mcp_tool: { type: 'mcp_tool', name: workflowNodeLabel('mcp_tool'), config: { tool_name: 'filesystem.list', agent_code: 'workflow_runner' } },
  skill: { type: 'skill', name: workflowNodeLabel('skill'), config: { skill_code: 'code.review', agent_code: 'workflow_runner', input: {} } },
  supervisor: { type: 'supervisor', name: workflowNodeLabel('supervisor'), config: {} },
};

export function useWorkflowEditor(initialNodes: WorkflowNode[], initialEdges: WorkflowEdge[], events: AgentEvent[] = []) {
  const [workflowId, setWorkflowId] = useState('');
  const [workflowName, setWorkflowName] = useState('项目分析审核流');
  const [workflowDescription, setWorkflowDescription] = useState('规划 -> 分析 Agent -> 人工审核 -> 报告');
  const [savedWorkflows, setSavedWorkflows] = useState<WorkflowRecord[]>([]);
  const [nodes, setNodes] = useState<WorkflowNode[]>(initialNodes);
  const [edges, setEdges] = useState<WorkflowEdge[]>(initialEdges);
  const [selectedNodeId, setSelectedNodeId] = useState('analyze');
  const [selectedEdgeKey, setSelectedEdgeKey] = useState('');
  const [connectFrom, setConnectFrom] = useState<string | null>(null);
  const [isPanning, setIsPanning] = useState(false);
  const [workflowValidation, setWorkflowValidation] = useState<WorkflowValidation | null>(null);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<{ id: string; dx: number; dy: number } | null>(null);
  const panRef = useRef<{ x: number; y: number; scrollLeft: number; scrollTop: number } | null>(null);

  const selectedNode = nodes.find((node) => node.id === selectedNodeId);
  const nodeStatus = useMemo(() => {
    const status: Record<string, NodeStatus> = {};
    for (const node of nodes) status[node.id] = 'idle';
    for (const event of events) {
      const nodeId = String(event.data?.node_id ?? event.node ?? '');
      if (nodeId && status[nodeId] !== undefined && event.status) status[nodeId] = event.status as NodeStatus;
    }
    return status;
  }, [events, nodes]);
  const canvasSize = useMemo(() => ({ width: Math.max(960, ...nodes.map((node) => node.x + 260)), height: Math.max(460, ...nodes.map((node) => node.y + 150)) }), [nodes]);

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
  const loadWorkflow = useCallback((workflow: WorkflowRecord) => {
    setWorkflowId(workflow.workflow_id);
    setWorkflowName(workflow.name);
    setWorkflowDescription(workflow.description ?? '');
    setNodes(workflow.nodes.map((node, index) => ({ ...node, x: Number.isFinite(node.x) ? node.x : 64 + index * 228, y: Number.isFinite(node.y) ? node.y : 92, config: node.config ?? {} })));
    setEdges(workflow.edges ?? []);
    setSelectedNodeId(workflow.nodes[0]?.id ?? '');
    setSelectedEdgeKey('');
    setWorkflowValidation(null);
  }, []);
  const applyPlannedWorkflow = useCallback((workflow: { nodes: WorkflowNode[]; edges: WorkflowEdge[] }) => {
    setNodes(workflow.nodes.map((node, index) => ({ ...node, x: Number.isFinite(node.x) ? node.x : 64 + index * 228, y: Number.isFinite(node.y) ? node.y : 92, config: node.config ?? {} })));
    setEdges(workflow.edges ?? []);
    setWorkflowName('Planner Generated Workflow');
    setWorkflowDescription('Generated from task goal by Planner mode.');
  }, []);
  const createWorkflow = useCallback(() => {
    setWorkflowId('');
    setWorkflowName('未命名 Workflow');
    setWorkflowDescription('');
    setNodes([]);
    setEdges([]);
    setSelectedNodeId('');
    setSelectedEdgeKey('');
    setConnectFrom(null);
    setWorkflowValidation(null);
  }, []);
  const addNode = useCallback((type: string) => {
    const template = nodeTemplates[type];
    if (!template) return;
    const id = `${type}_${Date.now()}`;
    setNodes((previous) => {
      const index = previous.length;
      const node = { ...template, id, x: 64 + (index % 4) * 228, y: 92 + Math.floor(index / 4) * 138 };
      if (previous.length) setEdges((current) => [...current, { source: previous[previous.length - 1].id, target: id }]);
      return [...previous, node];
    });
    setSelectedNodeId(id);
    setSelectedEdgeKey('');
  }, []);
  const deleteWorkflow = useCallback(async (id: string) => {
    const result = await deleteSavedWorkflow(id);
    if (workflowId === id) createWorkflow();
    await refreshWorkflows();
    return result;
  }, [createWorkflow, refreshWorkflows, workflowId]);

  const handleDrop = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const raw = event.dataTransfer.getData(dragPayloadMime);
    if (!raw || !canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const item = JSON.parse(raw) as { type: string; name: string; config?: Record<string, unknown> };
    const id = `${item.type}_${Date.now()}`;
    setNodes((previous) => [...previous, { id, type: item.type, name: item.name, x: canvasRef.current!.scrollLeft + event.clientX - rect.left - 82, y: canvasRef.current!.scrollTop + event.clientY - rect.top - 28, config: item.config ?? {} }]);
    setSelectedNodeId(id); setSelectedEdgeKey('');
  }, []);
  const startMove = useCallback((event: PointerEvent<HTMLDivElement>, node: WorkflowNode) => {
    setSelectedNodeId(node.id); setSelectedEdgeKey('');
    const rect = event.currentTarget.getBoundingClientRect();
    dragRef.current = { id: node.id, dx: event.clientX - rect.left, dy: event.clientY - rect.top };
    event.currentTarget.setPointerCapture(event.pointerId);
  }, []);
  const startCanvasPan = useCallback((event: PointerEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement;
    if (event.button !== 0 || target.closest('.flow-node') || target.closest('button')) return;
    event.preventDefault();
    panRef.current = { x: event.clientX, y: event.clientY, scrollLeft: event.currentTarget.scrollLeft, scrollTop: event.currentTarget.scrollTop };
    setIsPanning(true);
    event.currentTarget.setPointerCapture(event.pointerId);
  }, []);
  const onCanvasPointerMove = useCallback((event: PointerEvent<HTMLDivElement>) => {
    if (dragRef.current && canvasRef.current) {
      const canvas = canvasRef.current;
      const rect = canvas.getBoundingClientRect(); const { id, dx, dy } = dragRef.current;
      const edge = 64;
      const horizontal = event.clientX < rect.left + edge ? event.clientX - (rect.left + edge) : event.clientX > rect.right - edge ? event.clientX - (rect.right - edge) : 0;
      const vertical = event.clientY < rect.top + edge ? event.clientY - (rect.top + edge) : event.clientY > rect.bottom - edge ? event.clientY - (rect.bottom - edge) : 0;
      if (horizontal || vertical) {
        canvas.scrollLeft = Math.max(0, Math.min(canvas.scrollWidth - canvas.clientWidth, canvas.scrollLeft + horizontal * 0.22));
        canvas.scrollTop = Math.max(0, Math.min(canvas.scrollHeight - canvas.clientHeight, canvas.scrollTop + vertical * 0.22));
      }
      setNodes((previous) => previous.map((node) => node.id === id ? { ...node, x: Math.max(8, canvas.scrollLeft + event.clientX - rect.left - dx), y: Math.max(8, canvas.scrollTop + event.clientY - rect.top - dy) } : node));
    }
    if (panRef.current && canvasRef.current) { canvasRef.current.scrollLeft = panRef.current.scrollLeft - (event.clientX - panRef.current.x); canvasRef.current.scrollTop = panRef.current.scrollTop - (event.clientY - panRef.current.y); }
  }, [canvasSize]);
  const onEndPointer = useCallback(() => { dragRef.current = null; panRef.current = null; setIsPanning(false); }, []);
  const onToggleConnect = useCallback((nodeId: string) => {
    if (!connectFrom) { setConnectFrom(nodeId); return; }
    if (connectFrom !== nodeId) setEdges((previous) => previous.some((edge) => edge.source === connectFrom && edge.target === nodeId) ? previous : [...previous, { source: connectFrom, target: nodeId }]);
    setConnectFrom(null);
  }, [connectFrom]);
  const updateSelectedNode = useCallback((patch: Partial<WorkflowNode>) => setNodes((previous) => previous.map((node) => node.id === selectedNodeId ? { ...node, ...patch } : node)), [selectedNodeId]);
  const updateSelectedConfig = useCallback((key: string, value: unknown) => setNodes((previous) => previous.map((node) => node.id === selectedNodeId ? { ...node, config: { ...node.config, [key]: value } } : node)), [selectedNodeId]);
  const updateSelectedEdge = useCallback((patch: Partial<WorkflowEdge>) => setEdges((previous) => previous.map((edge) => edgeKey(edge) === selectedEdgeKey ? { ...edge, ...patch } : edge)), [selectedEdgeKey]);
  const deleteSelectedEdge = useCallback(() => { setEdges((previous) => previous.filter((edge) => edgeKey(edge) !== selectedEdgeKey)); setSelectedEdgeKey(''); }, [selectedEdgeKey]);
  const deleteSelectedNode = useCallback(() => { setNodes((previous) => previous.filter((node) => node.id !== selectedNodeId)); setEdges((previous) => previous.filter((edge) => edge.source !== selectedNodeId && edge.target !== selectedNodeId)); setSelectedNodeId(''); setSelectedEdgeKey(''); }, [selectedNodeId]);
  const workflowCanvas: WorkflowCanvasProps = { canvasRef, canvasSize, connectFrom, edges, nodes, nodeStatus, selectedNodeId, selectedEdgeKey, isPanning, onCanvasPointerMove, onDrop: handleDrop, onEndPointer, onStartCanvasPan: startCanvasPan, onStartMove: startMove, onSelectEdge: (edge) => { setSelectedEdgeKey(edgeKey(edge)); setSelectedNodeId(''); }, onToggleConnect };

  return { workflowId, setWorkflowId, workflowName, setWorkflowName, workflowDescription, setWorkflowDescription,
    savedWorkflows, setSavedWorkflows, nodes, setNodes, edges, setEdges, selectedNodeId, setSelectedNodeId,
    selectedEdgeKey, setSelectedEdgeKey, connectFrom, setConnectFrom, workflowValidation, setWorkflowValidation,
    refreshWorkflows, persistWorkflow, checkWorkflow, loadWorkflow, applyPlannedWorkflow, createWorkflow, addNode, deleteWorkflow, selectedNode, selectedEdge: edges.find((edge) => edgeKey(edge) === selectedEdgeKey),
    workflowCanvas, updateSelectedNode, updateSelectedConfig, updateSelectedEdge, deleteSelectedEdge, deleteSelectedNode };
}
