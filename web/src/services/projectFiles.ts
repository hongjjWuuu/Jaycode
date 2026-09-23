import { requestJson } from './http';

/** Project file picker API; kept separate from the MCP governance console. */
export async function listProjectFiles(rootPath: string, maxFiles = 800): Promise<{ root: string; files: string[] }> {
  const data = await requestJson<{ root?: string; files?: string[] }>(
    '/api/v1/mcp/filesystem/list',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ root_path: rootPath, max_files: maxFiles }) },
    'File list failed',
  );
  return { root: data.root ?? rootPath, files: data.files ?? [] };
}
