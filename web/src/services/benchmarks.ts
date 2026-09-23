import type { BenchmarkCase, BenchmarkRun, BenchmarkType } from '../types';
import { requestJson } from './http';

const API_BASE = '';
const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

export type BenchmarkRunPayload = {
  name: string;
  agent_code: string;
  iterations: number;
  cases: BenchmarkCase[];
};

export async function runMcpBenchmark(payload: BenchmarkRunPayload): Promise<BenchmarkRun> {
  const data = await requestJson<{ run: BenchmarkRun }>(
    `${API_BASE}/api/v1/benchmarks/mcp/run`, json(payload), 'MCP benchmark failed',
  );
  return data.run;
}

export async function runBenchmark(
  benchmarkType: BenchmarkType,
  payload: BenchmarkRunPayload,
): Promise<BenchmarkRun> {
  const data = await requestJson<{ run: BenchmarkRun }>(
    `${API_BASE}/api/v1/benchmarks/${benchmarkType}/run`, json(payload), `${benchmarkType} benchmark failed`,
  );
  return data.run;
}

export async function listBenchmarks(limit = 50, benchmarkType = ''): Promise<BenchmarkRun[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (benchmarkType) params.set('benchmark_type', benchmarkType);
  const data = await requestJson<{ runs?: BenchmarkRun[] }>(
    `${API_BASE}/api/v1/benchmarks?${params}`, {}, 'Benchmark list failed',
  );
  return data.runs ?? [];
}

export async function getBenchmark(runId: string): Promise<BenchmarkRun> {
  const data = await requestJson<{ run: BenchmarkRun }>(
    `${API_BASE}/api/v1/benchmarks/${encodeURIComponent(runId)}`, {}, 'Benchmark detail failed',
  );
  return data.run;
}
