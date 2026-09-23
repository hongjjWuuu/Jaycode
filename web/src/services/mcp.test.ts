import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from './http';
import {
  listMcpRegisteredTools,
  listProjectFiles,
  setMcpToolApproval,
} from './mcp';

afterEach(() => vi.restoreAllMocks());

describe('MCP service', () => {
  it('encodes registered-tool query parameters and returns the tool list', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ tools: [{ server_id: 'filesystem', tool_name: 'list' }] }), {
        status: 200,
      }),
    );

    await expect(listMcpRegisteredTools('filesystem', 'workflow runner')).resolves.toEqual([
      { server_id: 'filesystem', tool_name: 'list' },
    ]);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/mcp/registered-tools?server_id=filesystem&agent_code=workflow+runner',
      {},
    );
  });

  it('normalizes a filesystem-list response while retaining the request payload', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ files: ['README.md'] }), { status: 200 }),
    );

    await expect(listProjectFiles('D:/JayAgent/Jaycode', 12)).resolves.toEqual({
      root: 'D:/JayAgent/Jaycode',
      files: ['README.md'],
    });
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/mcp/filesystem/list', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ root_path: 'D:/JayAgent/Jaycode', max_files: 12 }),
    });
  });

  it('preserves error-envelope details for a failed approval update', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          error_code: 'MCP_APPROVAL_DENIED',
          message: 'Approval update was rejected.',
          request_id: 'req-mcp-1',
        }),
        { status: 403 },
      ),
    );

    await expect(
      setMcpToolApproval({
        agent_code: 'workflow_runner',
        server_id: 'filesystem',
        tool_name: 'list',
        allowed: true,
      }),
    ).rejects.toEqual(new ApiError('MCP_APPROVAL_DENIED', 'req-mcp-1', 'Approval update was rejected.'));
  });
});
