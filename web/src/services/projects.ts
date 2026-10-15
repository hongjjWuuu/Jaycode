import type { ProjectBrowserResult, ProjectBrowserRoot, ProjectLibraryItem, ResolvedProject } from '../types';
import { requestJson } from './http';

export function resolveProject(projectPath: string, maxFiles = 200): Promise<ResolvedProject> {
  return requestJson('/api/v1/projects/resolve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_path: projectPath, max_files: maxFiles }),
  }, '项目路径验证失败');
}

export async function listProjectLibrary(): Promise<ProjectLibraryItem[]> {
  return (await requestJson<{ projects: ProjectLibraryItem[] }>('/api/v1/projects/library', {}, '读取项目库失败')).projects;
}

export async function saveProjectToLibrary(projectPath: string, name?: string): Promise<ProjectLibraryItem> {
  return (await requestJson<{ project: ProjectLibraryItem }>('/api/v1/projects/library', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project_path: projectPath, name }) }, '保存项目失败')).project;
}

export async function listProjectBrowserRoots(): Promise<ProjectBrowserRoot[]> {
  return (await requestJson<{ roots: ProjectBrowserRoot[] }>('/api/v1/projects/browser/roots', {}, '读取可浏览目录失败')).roots;
}

export function browseProjectDirectories(rootId: string, relativePath = ''): Promise<ProjectBrowserResult> {
  return requestJson('/api/v1/projects/browser/directories', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ root_id: rootId, relative_path: relativePath }) }, '浏览目录失败');
}
