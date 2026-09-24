import { useCallback, useMemo, useRef, useState } from 'react';
import type { DragEvent, PointerEvent } from 'react';
import { listWorkflows, saveWorkflow, updateWorkflow, validateWorkflow } from '../services/workflows';
import type { AgentEvent, NodeStatus, WorkflowEdge, WorkflowNode, WorkflowRecord, WorkflowValidation } from '../types';
import type { WorkflowCanvasProps } from '../components/workflow/WorkflowCanvas';

const dragPayloadMime = 'application/jaycode-node';
const edgeKey = (edge: WorkflowEdge) => `${edge.source}:${edge.target}:${edge.condition ?? 'always'}:${edge.value ?? ''}:${edge.source_path ?? ''}`;

export function useWorkflowEditor(initialNodes: WorkflowNode[], initialEdges: WorkflowEdge[], events: AgentEvent[] = []) {
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
    if (target.closest('.flow-node') || target.closest('button')) return;
    panRef.current = { x: event.clientX, y: event.clientY, scrollLeft: event.currentTarget.scrollLeft, scrollTop: event.currentTarget.scrollTop };
    event.currentTarget.setPointerCapture(event.pointerId);
  }, []);
  const onCanvasPointerMove = useCallback((event: PointerEvent<HTMLDivElement>) => {
    if (dragRef.current && canvasRef.current) {
      const rect = canvasRef.current.getBoundingClientRect(); const { id, dx, dy } = dragRef.current;
      setNodes((previous) => previous.map((node) => node.id === id ? { ...node, x: Math.max(8, Math.min(canvasSize.width - 180, canvasRef.current!.scrollLeft + event.clientX - rect.left - dx)), y: Math.max(8, Math.min(canvasSize.height - 78, canvasRef.current!.scrollTop + event.clientY - rect.top - dy)) } : node));
    }
    if (panRef.current && canvasRef.current) { canvasRef.current.scrollLeft = panRef.current.scrollLeft - (event.clientX - panRef.current.x); canvasRef.current.scrollTop = panRef.current.scrollTop - (event.clientY - panRef.current.y); }
  }, [canvasSize]);
  const onEndPointer = useCallback(() => { dragRef.current = null; panRef.current = null; }, []);
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
  const workflowCanvas: WorkflowCanvasProps = { canvasRef, canvasSize, connectFrom, edges, nodes, nodeStatus, selectedNodeId, selectedEdgeKey, onCanvasPointerMove, onDrop: handleDrop, onEndPointer, onStartCanvasPan: startCanvasPan, onStartMove: startMove, onSelectEdge: (edge) => { setSelectedEdgeKey(edgeKey(edge)); setSelectedNodeId(''); }, onToggleConnect };

  return { workflowId, setWorkflowId, workflowName, setWorkflowName, workflowDescription, setWorkflowDescription,
    savedWorkflows, setSavedWorkflows, nodes, setNodes, edges, setEdges, selectedNodeId, setSelectedNodeId,
    selectedEdgeKey, setSelectedEdgeKey, connectFrom, setConnectFrom, workflowValidation, setWorkflowValidation,
    refreshWorkflows, persistWorkflow, checkWorkflow, selectedNode, selectedEdge: edges.find((edge) => edgeKey(edge) === selectedEdgeKey),
    workflowCanvas, updateSelectedNode, updateSelectedConfig, updateSelectedEdge, deleteSelectedEdge, deleteSelectedNode };
}
