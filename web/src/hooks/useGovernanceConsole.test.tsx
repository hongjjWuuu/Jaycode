import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  listBenchmarks: vi.fn(), getBenchmark: vi.fn(), runBenchmark: vi.fn(),
  listLlmTraces: vi.fn(), listLlmPrompts: vi.fn(), getLlmUsage: vi.fn(), saveLlmPrompt: vi.fn(), setActiveLlmPrompt: vi.fn(), runLlmPromptAbTest: vi.fn(),
  getMcpStatus: vi.fn(), listMcpServers: vi.fn(), listMcpRegisteredTools: vi.fn(), listMcpToolCallLogs: vi.fn(), saveMcpServer: vi.fn(), setMcpServerEnabled: vi.fn(), discoverMcpServer: vi.fn(), setMcpRegisteredToolEnabled: vi.fn(), setMcpToolApproval: vi.fn(), callMcpTool: vi.fn(),
  listMarketplaceCatalog: vi.fn(), listMarketplaceInstalls: vi.fn(), installMarketplacePackage: vi.fn(), previewMarketplacePackage: vi.fn(), uninstallMarketplacePackage: vi.fn(),
  listSkillApprovals: vi.fn(), listSkillExecutionLogs: vi.fn(), listSkillPlugins: vi.fn(), listSkills: vi.fn(), executeSkill: vi.fn(), setSkillApproval: vi.fn(), setSkillEnabled: vi.fn(), uninstallSkillPlugin: vi.fn(),
}));
vi.mock('../services/benchmarks', () => mocks);
vi.mock('../services/llm', () => mocks);
vi.mock('../services/mcp', () => mocks);
vi.mock('../services/marketplace', () => mocks);
vi.mock('../services/skills', () => mocks);

import { useGovernanceConsole } from './useGovernanceConsole';

beforeEach(() => {
  vi.resetAllMocks();
  Object.values(mocks).forEach((mock) => mock.mockResolvedValue([]));
  mocks.getBenchmark.mockResolvedValue({ run_id: 'run-1', benchmark_type: 'mcp', summary: {}, results: [] });
  mocks.runBenchmark.mockResolvedValue({ run_id: 'run-1', benchmark_type: 'mcp', summary: {}, results: [] });
  mocks.getMcpStatus.mockResolvedValue({}); mocks.listMcpServers.mockResolvedValue([]); mocks.listMcpRegisteredTools.mockResolvedValue([]); mocks.listMcpToolCallLogs.mockResolvedValue([]);
});

describe('useGovernanceConsole', () => {
  it('runs a benchmark, refreshes its data, and resets loading', async () => {
    const { result } = renderHook(() => useGovernanceConsole());
    await act(async () => { await result.current.executeBenchmark({ name: 'run', agent_code: 'runner', iterations: 1, cases: [] }); });
    expect(mocks.runBenchmark).toHaveBeenCalledWith('mcp', expect.objectContaining({ name: 'run' }));
    expect(result.current.benchmarkRunning).toBe(false);
  });

  it('retains the error and resets loading when a benchmark fails', async () => {
    mocks.runBenchmark.mockRejectedValueOnce(new Error('run failed'));
    const { result } = renderHook(() => useGovernanceConsole());
    await act(async () => { try { await result.current.executeBenchmark({ name: 'run', agent_code: 'runner', iterations: 1, cases: [] }); } catch { /* asserted from Hook state below */ } });
    expect(result.current.benchmarkRunning).toBe(false);
    expect(result.current.benchmarkError).toBe('run failed');
  });
});
