import type { SkillRecord, WorkflowNode } from '../types';

const projectAgents = new Set(['project_analyzer', 'code_reviewer', 'file_reviewer', 'rag_processor']);
const projectInputs = new Set(['project_path', 'root_path', 'repo_path']);
const projectTools = new Set(['read_file', 'write_file', 'list_directory', 'directory_tree', 'search_files', 'git_status', 'git_log']);

export type WorkflowRequirements = {
  requiresProject: boolean;
  reasons: string[];
  knowledgeScopeMissing: boolean;
};

export function inspectWorkflowRequirements(nodes: WorkflowNode[], skills: SkillRecord[] = []): WorkflowRequirements {
  const reasons: string[] = [];
  let knowledgeScopeMissing = false;
  for (const node of nodes) {
    const agentType = String(node.config.agent_type ?? node.config.agent ?? '');
    const isKnowledge = node.type === 'rag' || (node.type === 'agent' && agentType === 'rag_processor');
    if (isKnowledge) {
      const scope = String(node.config.knowledge_scope ?? '');
      if (!scope || (scope === 'custom' && !String(node.config.collection ?? '').trim())) knowledgeScopeMissing = true;
      if (scope === 'project') reasons.push(`${node.name} 使用当前项目知识`);
    }
    if (node.type === 'agent' && projectAgents.has(agentType)) reasons.push(`${node.name} 需要读取项目`);
    if (node.type === 'mcp_tool') {
      const tool = String(node.config.tool_name ?? '');
      if (tool.startsWith('filesystem.') || tool.startsWith('git.') || projectTools.has(tool.toLowerCase())) reasons.push(`${node.name} 需要访问文件或 Git`);
    }
    if (node.type === 'skill') {
      const skill = skills.find((item) => item.code === String(node.config.skill_code ?? ''));
      const input = typeof node.config.input === 'object' && node.config.input ? node.config.input as Record<string, unknown> : {};
      if ([...projectInputs].some((key) => key in (skill?.input_schema ?? {}) || key in input)) reasons.push(`${node.name} 需要项目路径`);
    }
  }
  const uniqueReasons = [...new Set(reasons)];
  return { requiresProject: uniqueReasons.length > 0, reasons: uniqueReasons, knowledgeScopeMissing };
}
