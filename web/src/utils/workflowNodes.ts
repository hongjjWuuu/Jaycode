export const workflowNodeLabels: Record<string, string> = {
  planner: '规划',
  agent: '分析 Agent',
  human_review: '人工审核',
  reporter: '报告',
  rag: '知识检索',
  mcp_tool: 'MCP 工具',
  skill: 'Skill',
  supervisor: '监督',
};

export const workflowNodeDescriptions: Record<string, string> = {
  planner: '拆解目标并规划后续执行步骤。',
  agent: '按所选 Agent 能力执行项目分析或代码审查。',
  human_review: '暂停流程，等待人工确认、修改或拒绝。',
  reporter: '汇总节点输出并生成最终报告。',
  rag: '从知识库中检索与任务相关的资料。',
  mcp_tool: '调用已配置并获授权的 MCP 工具。',
  skill: '执行已审批的可复用 Skill。',
  supervisor: '汇总结果并进行治理判断。',
};

export function workflowNodeLabel(type: string): string {
  return workflowNodeLabels[type] ?? type;
}

export function workflowNodeDescription(type: string): string {
  return workflowNodeDescriptions[type] ?? '执行此节点的已配置任务。';
}
