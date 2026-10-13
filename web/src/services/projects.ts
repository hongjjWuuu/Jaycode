import type { ResolvedProject } from '../types';
import { requestJson } from './http';

export function resolveProject(projectPath: string, maxFiles = 200): Promise<ResolvedProject> {
  return requestJson('/api/v1/projects/resolve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_path: projectPath, max_files: maxFiles }),
  }, '项目路径验证失败');
}
