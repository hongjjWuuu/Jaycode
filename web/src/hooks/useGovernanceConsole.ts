import { useCallback, useState } from 'react';
import { getBenchmark, listBenchmarks, runBenchmark } from '../services/benchmarks';
import { getLlmUsage, listLlmPrompts, listLlmTraces, runLlmPromptAbTest, saveLlmPrompt, setActiveLlmPrompt } from '../services/llm';
import { callMcpTool, discoverMcpServer, getMcpStatus, listMcpRegisteredTools, listMcpServers, listMcpToolCallLogs, saveMcpServer, setMcpRegisteredToolEnabled, setMcpServerEnabled, setMcpToolApproval } from '../services/mcp';
import { installMarketplacePackage, listMarketplaceCatalog, listMarketplaceInstalls, previewMarketplacePackage, uninstallMarketplacePackage } from '../services/marketplace';
import { executeSkill, listSkillApprovals, listSkillExecutionLogs, listSkillPlugins, listSkills, setSkillApproval, setSkillEnabled, uninstallSkillPlugin } from '../services/skills';
import type {
  BenchmarkCase, BenchmarkRun, BenchmarkType, LlmPromptVersion, LlmTrace, LlmUsageDashboard, MarketplaceCatalogItem,
  MarketplaceInstall, MarketplacePreview, McpRegisteredTool, McpServerConfig, McpStatus, McpToolCallLog,
  LlmPromptAbTestResult, LlmPromptPayload, SkillApproval, SkillExecutionLog, SkillPlugin, SkillRecord,
} from '../types';

/** State and refresh boundary for the five governance consoles. Cross-page navigation remains explicit. */
export function useGovernanceConsole() {
  const [llmTraces, setLlmTraces] = useState<LlmTrace[]>([]);
  const [llmTraceAgent, setLlmTraceAgent] = useState('');
  const [llmPrompts, setLlmPrompts] = useState<LlmPromptVersion[]>([]);
  const [llmUsage, setLlmUsage] = useState<LlmUsageDashboard | null>(null);
  const [llmAgentFilter, setLlmAgentFilter] = useState('');
  const [mcpStatus, setMcpStatus] = useState<McpStatus | null>(null);
  const [mcpServers, setMcpServers] = useState<McpServerConfig[]>([]);
  const [mcpTools, setMcpTools] = useState<McpRegisteredTool[]>([]);
  const [mcpLogs, setMcpLogs] = useState<McpToolCallLog[]>([]);
  const [skillPlugins, setSkillPlugins] = useState<SkillPlugin[]>([]);
  const [skills, setSkills] = useState<SkillRecord[]>([]);
  const [skillApprovals, setSkillApprovals] = useState<SkillApproval[]>([]);
  const [skillLogs, setSkillLogs] = useState<SkillExecutionLog[]>([]);
  const [selectedSkillCode, setSelectedSkillCode] = useState('code.review');
  const [marketplaceCatalog, setMarketplaceCatalog] = useState<MarketplaceCatalogItem[]>([]);
  const [marketplaceInstalls, setMarketplaceInstalls] = useState<MarketplaceInstall[]>([]);
  const [marketplacePreview, setMarketplacePreview] = useState<MarketplacePreview | null>(null);
  const [lastMarketplaceInstall, setLastMarketplaceInstall] = useState<MarketplaceInstall | null>(null);
  const [benchmarkRuns, setBenchmarkRuns] = useState<BenchmarkRun[]>([]);
  const [selectedBenchmark, setSelectedBenchmark] = useState<BenchmarkRun | null>(null);
  const [benchmarkType, setBenchmarkType] = useState<BenchmarkType>('mcp');
  const [benchmarkRunning, setBenchmarkRunning] = useState(false);
  const [benchmarkError, setBenchmarkError] = useState('');

  const refreshLlmTraces = useCallback(async (agent = '') => setLlmTraces(await listLlmTraces(50, agent)), []);
  const refreshLlmGovernance = useCallback(async (agent = '') => {
    const [prompts, usage] = await Promise.all([listLlmPrompts(agent), getLlmUsage(500, agent)]);
    setLlmPrompts(prompts); setLlmUsage(usage);
  }, []);
  const refreshMcp = useCallback(async (serverId = '', agentCode = 'workflow_runner') => {
    const [status, servers, tools, logs] = await Promise.all([getMcpStatus(), listMcpServers(), listMcpRegisteredTools(serverId, agentCode), listMcpToolCallLogs(100, serverId)]);
    setMcpStatus(status); setMcpServers(servers); setMcpTools(tools); setMcpLogs(logs);
  }, []);
  const refreshSkills = useCallback(async (skillCode = '') => {
    const [plugins, nextSkills, approvals, logs] = await Promise.all([listSkillPlugins(), listSkills(), listSkillApprovals(), listSkillExecutionLogs(80, skillCode)]);
    setSkillPlugins(plugins); setSkills(nextSkills); setSkillApprovals(approvals); setSkillLogs(logs);
    if (!skillCode && nextSkills[0]) setSelectedSkillCode((current) => current || nextSkills[0].code);
  }, []);
  const refreshMarketplace = useCallback(async (packageType = '') => {
    const [catalog, installs] = await Promise.all([listMarketplaceCatalog(), listMarketplaceInstalls(80, packageType)]);
    setMarketplaceCatalog(catalog); setMarketplaceInstalls(installs);
  }, []);
  const refreshBenchmarks = useCallback(async (nextType: BenchmarkType) => {
    const runs = await listBenchmarks(50, nextType);
    setBenchmarkRuns(runs);
    setSelectedBenchmark((current) => current?.benchmark_type === nextType ? current : null);
    if (runs[0]) setSelectedBenchmark(await getBenchmark(runs[0].run_id));
  }, []);

  const executeBenchmark = useCallback(async (payload: {
    name: string;
    agent_code: string;
    iterations: number;
    cases: BenchmarkCase[];
  }) => {
    setBenchmarkRunning(true);
    setBenchmarkError('');
    try {
      const run = await runBenchmark(benchmarkType, payload);
      setSelectedBenchmark(run);
      await refreshBenchmarks(benchmarkType);
      await refreshMcp();
      return run;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Benchmark failed';
      setBenchmarkError(message);
      throw error;
    } finally {
      setBenchmarkRunning(false);
    }
  }, [benchmarkType, refreshBenchmarks, refreshMcp]);

  const openBenchmark = useCallback(async (runId: string) => {
    setBenchmarkError('');
    setSelectedBenchmark(await getBenchmark(runId));
  }, []);

  const changeBenchmarkType = useCallback(async (nextType: BenchmarkType) => {
    setBenchmarkType(nextType);
    setBenchmarkError('');
    setSelectedBenchmark(null);
    await refreshBenchmarks(nextType);
  }, [refreshBenchmarks]);

  const changeLlmAgent = useCallback(async (agent: string) => {
    setLlmAgentFilter(agent);
    await refreshLlmGovernance(agent);
  }, [refreshLlmGovernance]);

  const changeLlmTraceAgent = useCallback(async (agent: string) => {
    setLlmTraceAgent(agent);
    await refreshLlmTraces(agent);
  }, [refreshLlmTraces]);

  const refreshLlm = useCallback(async () => {
    await Promise.all([refreshLlmGovernance(llmAgentFilter), refreshLlmTraces(llmTraceAgent)]);
  }, [llmAgentFilter, llmTraceAgent, refreshLlmGovernance, refreshLlmTraces]);

  const activateLlmPrompt = useCallback(async (prompt: LlmPromptVersion) => {
    await setActiveLlmPrompt(prompt.agent, prompt.prompt_version);
    await refreshLlm();
  }, [refreshLlm]);

  const savePrompt = useCallback(async (payload: LlmPromptPayload) => {
    await saveLlmPrompt(payload);
    await refreshLlm();
  }, [refreshLlm]);

  const runPromptAbTest = useCallback(async (payload: { agent: string; prompt_a: string; prompt_b: string; system_prompt: string; user_prompt: string; fallback: string }): Promise<LlmPromptAbTestResult> => {
    const result = await runLlmPromptAbTest(payload);
    await refreshLlm();
    return result;
  }, [refreshLlm]);

  const saveServer = useCallback(async (payload: { server_id: string; name: string; transport: string; command?: string; args: string[]; env: Record<string, string>; url?: string; enabled: boolean }) => {
    await saveMcpServer(payload); await refreshMcp(payload.server_id);
  }, [refreshMcp]);
  const setServerEnabled = useCallback(async (serverId: string, enabled: boolean) => {
    await setMcpServerEnabled(serverId, enabled); await refreshMcp(serverId);
  }, [refreshMcp]);
  const discoverServer = useCallback(async (serverId: string) => {
    await discoverMcpServer(serverId); await refreshMcp(serverId);
  }, [refreshMcp]);
  const setToolEnabled = useCallback(async (serverId: string, toolName: string, enabled: boolean) => {
    await setMcpRegisteredToolEnabled(serverId, toolName, enabled); await refreshMcp(serverId);
  }, [refreshMcp]);
  const setToolApproval = useCallback(async (agentCode: string, serverId: string, toolName: string, allowed: boolean, reason: string) => {
    await setMcpToolApproval({ agent_code: agentCode, server_id: serverId, tool_name: toolName, allowed, reason }); await refreshMcp(serverId, agentCode);
  }, [refreshMcp]);
  const invokeTool = useCallback(async (payload: { server_id?: string; tool_name: string; agent_code: string; arguments: Record<string, unknown> }) => {
    const result = await callMcpTool(payload); await refreshMcp(payload.server_id ?? '', payload.agent_code); return result;
  }, [refreshMcp]);

  const setSkillStatus = useCallback(async (skillCode: string, enabled: boolean) => {
    await setSkillEnabled(skillCode, enabled); await refreshSkills(skillCode);
  }, [refreshSkills]);
  const loadSkillApprovals = useCallback(async () => {
    const approvals = await listSkillApprovals(); setSkillApprovals(approvals); return approvals;
  }, []);
  const updateSkillApproval = useCallback(async (skillCode: string, agentCode: string, allowed: boolean, reason: string) => {
    await setSkillApproval({ skill_code: skillCode, agent_code: agentCode, allowed, reason }); await refreshSkills(skillCode);
  }, [refreshSkills]);
  const runSkill = useCallback(async (payload: { skill_code: string; agent_code: string; input: Record<string, unknown>; task_id?: string }) => {
    const result = await executeSkill(payload); await refreshSkills(payload.skill_code); return result;
  }, [refreshSkills]);
  const removeSkillPlugin = useCallback(async (pluginId: string) => {
    const result = await uninstallSkillPlugin(pluginId); await Promise.all([refreshSkills(), refreshMarketplace()]); return result;
  }, [refreshMarketplace, refreshSkills]);
  const previewPackage = useCallback(async (sourceUrl: string) => {
    const preview = await previewMarketplacePackage(sourceUrl); setMarketplacePreview(preview); return preview;
  }, []);
  const installPackage = useCallback(async (sourceUrl: string) => {
    const result = await installMarketplacePackage(sourceUrl); setLastMarketplaceInstall(result); await Promise.all([refreshMarketplace(), refreshSkills(), refreshMcp(), refreshLlm()]); return result;
  }, [refreshLlm, refreshMarketplace, refreshMcp, refreshSkills]);
  const removePackage = useCallback(async (packageId: string) => {
    const result = await uninstallMarketplacePackage(packageId); setLastMarketplaceInstall(result); await Promise.all([refreshMarketplace(), refreshSkills()]); return result;
  }, [refreshMarketplace, refreshSkills]);

  return { llmTraces, setLlmTraces, llmTraceAgent, setLlmTraceAgent, llmPrompts, setLlmPrompts, llmUsage, setLlmUsage, llmAgentFilter, setLlmAgentFilter,
    mcpStatus, setMcpStatus, mcpServers, setMcpServers, mcpTools, setMcpTools, mcpLogs, setMcpLogs, skillPlugins, setSkillPlugins, skills, setSkills,
    skillApprovals, setSkillApprovals, skillLogs, setSkillLogs, selectedSkillCode, setSelectedSkillCode, marketplaceCatalog, setMarketplaceCatalog,
    marketplaceInstalls, setMarketplaceInstalls, marketplacePreview, setMarketplacePreview, lastMarketplaceInstall, setLastMarketplaceInstall,
    benchmarkRuns, setBenchmarkRuns, selectedBenchmark, setSelectedBenchmark, benchmarkType, setBenchmarkType, benchmarkRunning, setBenchmarkRunning,
    benchmarkError, setBenchmarkError, refreshLlmTraces, refreshLlmGovernance, refreshMcp, refreshSkills, refreshMarketplace, refreshBenchmarks,
    executeBenchmark, openBenchmark, changeBenchmarkType,
    changeLlmAgent, changeLlmTraceAgent, refreshLlm, activateLlmPrompt, savePrompt, runPromptAbTest,
    saveServer, setServerEnabled, discoverServer, setToolEnabled, setToolApproval, invokeTool,
    setSkillStatus, loadSkillApprovals, updateSkillApproval, runSkill, removeSkillPlugin, previewPackage, installPackage, removePackage };
}
