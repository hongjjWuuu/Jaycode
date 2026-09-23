import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from './http';
import { getBenchmark, listBenchmarks, runBenchmark } from './benchmarks';

afterEach(() => vi.restoreAllMocks());

describe('Benchmark service', () => {
  it('encodes type filters and unwraps benchmark runs', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ runs: [{ run_id: 'run-1', benchmark_type: 'rag' }] }), { status: 200 }),
    );

    await expect(listBenchmarks(12, 'rag')).resolves.toEqual([{ run_id: 'run-1', benchmark_type: 'rag' }]);
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/benchmarks?limit=12&benchmark_type=rag', {});
  });

  it('sends an unchanged Benchmark run payload and unwraps its result', async () => {
    const payload = { name: 'RAG regression', agent_code: 'benchmark_runner', iterations: 3, cases: [] };
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ run: { run_id: 'run-2', status: 'completed' } }), { status: 200 }),
    );

    await expect(runBenchmark('rag', payload)).resolves.toMatchObject({ run_id: 'run-2' });
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/benchmarks/rag/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  });

  it('preserves the compatible error envelope for detail failures', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ error_code: 'NOT_FOUND', message: 'Benchmark run not found.', request_id: 'req-benchmark-1' }), { status: 404 }),
    );

    await expect(getBenchmark('missing/run'))
      .rejects.toEqual(new ApiError('NOT_FOUND', 'req-benchmark-1', 'Benchmark run not found.'));
  });
});
