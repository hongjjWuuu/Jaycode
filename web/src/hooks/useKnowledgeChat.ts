import { useCallback, useState } from 'react';
import { chatLearningCoach, createTaskLearningPlan, listLearningPlans, updateLearningPlanStatus } from '../services/learning';
import { addKnowledgeNote, confirmMemory, deleteMemory, extractMemoryCandidates, listKnowledgeDocuments, listMemories, queryKnowledge, rejectMemory } from '../services/rag';
import type { LearningPlanRecord, MemoryRecord, RagDocument, RagResult } from '../types';
import { firstLine } from '../utils/taskRuntime';

export type ChatMode = 'task' | 'knowledge' | 'coach';
export type ChatMessage = { role: 'user' | 'assistant'; content: string; source?: string; day?: number | null; theme?: string | null };
type Options = { taskId: string; fallbackGoal: string; askTask: (question: string) => Promise<{ answer: string; answer_source?: string; sources: RagResult[] }>; onNavigate: (view: 'chat') => void };

/** Owns RAG, memory, learning-plan, and chat presentation state. */
export function useKnowledgeChat({ taskId, fallbackGoal, askTask, onNavigate }: Options) {
  const [knowledgeDocs, setKnowledgeDocs] = useState<RagDocument[]>([]);
  const [knowledgeResults, setKnowledgeResults] = useState<RagResult[]>([]);
  const [knowledgeNote, setKnowledgeNote] = useState('');
  const [memories, setMemories] = useState<MemoryRecord[]>([]);
  const [chatMode, setChatMode] = useState<ChatMode>('task');
  const [chatInput, setChatInput] = useState('这个项目我应该先看哪些模块？');
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatSources, setChatSources] = useState<RagResult[]>([]);
  const [learningPlans, setLearningPlans] = useState<LearningPlanRecord[]>([]);
  const [knowledgeQuestion, setKnowledgeQuestion] = useState('项目结构');
  const [coachTurn, setCoachTurn] = useState(0);

  const refreshMemories = useCallback(async () => setMemories(await listMemories()), []);
  const refreshLearningPlans = useCallback(async (id = taskId) => setLearningPlans(await listLearningPlans(id || undefined)), [taskId]);
  const query = useCallback(async (question = knowledgeQuestion || fallbackGoal, limit = 5) => {
    const [docs, results] = await Promise.all([listKnowledgeDocuments('project-memory'), queryKnowledge('project-memory', question, limit)]);
    setKnowledgeDocs(docs); setKnowledgeResults(results); setChatSources(results); return results;
  }, [fallbackGoal, knowledgeQuestion]);
  const changeMode = useCallback(async (mode: ChatMode) => {
    setChatMode(mode); setChatSources([]);
    if (mode === 'coach') await refreshLearningPlans();
    if (mode === 'knowledge') await query();
  }, [query, refreshLearningPlans]);
  const confirm = useCallback(async (id: string) => { await confirmMemory(id); await refreshMemories(); }, [refreshMemories]);
  const reject = useCallback(async (id: string) => { await rejectMemory(id); await refreshMemories(); }, [refreshMemories]);
  const remove = useCallback(async (id: string) => { await deleteMemory(id); await refreshMemories(); }, [refreshMemories]);
  const saveKnowledgeNote = useCallback(async () => {
    if (!knowledgeNote.trim()) return; await addKnowledgeNote('project-memory', `note/${Date.now()}`, knowledgeNote);
    setKnowledgeNote(''); await query(); setChatMode('knowledge'); onNavigate('chat');
  }, [knowledgeNote, onNavigate, query]);
  const saveReviewKnowledge = useCallback(async (message: string, reviewQuery: string) => {
    setKnowledgeQuestion(reviewQuery); const results = await query(reviewQuery); setChatMode('knowledge'); onNavigate('chat');
    setChatMessages((items) => [...items, { role: 'assistant', content: `${message}\n\nproject-memory 当前有 ${knowledgeDocs.length} 条文档记录。` }]);
    return results;
  }, [knowledgeDocs.length, onNavigate, query]);
  const startLearning = useCallback(async (comment: string) => {
    if (!taskId) return null;
    const topic = `任务复盘：${fallbackGoal}`;
    const plan = await createTaskLearningPlan(taskId, { topic, level: 'beginner', days: 7, goal: fallbackGoal, comment });
    await refreshLearningPlans(taskId); setChatMode('coach'); onNavigate('chat');
    const prompt = [`基于当前任务生成学习陪练：${fallbackGoal}`, `任务 ID：${taskId}`, comment ? `审核意见：${comment}` : '', '请先给我一个学习目标，然后连续追问我对项目结构、风险和 LangGraph 工作流的理解。'].filter(Boolean).join('\n');
    const turn = coachTurn + 1; setCoachTurn(turn); setChatInput('我先回答：'); setChatMessages((items) => [...items, { role: 'user', content: prompt }]);
    const coach = await chatLearningCoach({ topic, level: 'beginner', question: prompt, answer: comment || fallbackGoal, task_id: taskId, turn });
    setChatMessages((items) => [...items, { role: 'assistant', content: `已生成学习计划：${plan.topic}（${plan.status}）\n\n${coach.reply}\n\n${coach.next_questions.map((item) => `Q: ${item}`).join('\n')}`, source: coach.answer_source, day: coach.day, theme: coach.theme }]);
    return plan;
  }, [coachTurn, fallbackGoal, onNavigate, refreshLearningPlans, taskId]);
  const setPlanStatus = useCallback(async (id: string, status: LearningPlanRecord['status']) => {
    const updated = await updateLearningPlanStatus(id, status); await refreshLearningPlans(); setChatMode('coach'); onNavigate('chat');
    setChatMessages((items) => [...items, { role: 'assistant', content: `学习计划状态已更新：${updated.topic} -> ${updated.status}` }]); return updated;
  }, [onNavigate, refreshLearningPlans]);
  const send = useCallback(async () => {
    const question = chatInput.trim(); if (!question) return;
    setChatMessages((items) => [...items, { role: 'user', content: question }]); setChatInput('');
    try {
      await extractMemoryCandidates({ text: question, source_ref: `chat/${chatMode}` }); await refreshMemories();
      if (chatMode === 'task') {
        const result = await askTask(question); setChatSources(result.sources ?? []);
        setChatMessages((items) => [...items, { role: 'assistant', content: result.answer, source: result.answer_source }]);
      } else if (chatMode === 'knowledge') {
        const results = await queryKnowledge('project-memory', question, 6); setChatSources(results);
        setChatMessages((items) => [...items, { role: 'assistant', content: results.length ? `在 project-memory 中找到 ${results.length} 条相关知识：\n\n${results.map((item) => `- ${item.path}: ${firstLine(item.content)}`).join('\n')}` : 'project-memory 中暂时没有命中内容。你可以先在报告页保存知识笔记，或运行 RAG Processor。' }]);
      } else {
        const turn = coachTurn + 1; setCoachTurn(turn);
        const result = await chatLearningCoach({ topic: 'Jaycode 项目理解', level: 'beginner', question, answer: question, task_id: taskId || undefined, turn });
        setChatMessages((items) => [...items, { role: 'assistant', content: `${result.reply}\n\n${result.next_questions.map((item) => `Q: ${item}`).join('\n')}`, source: result.answer_source, day: result.day, theme: result.theme }]);
      }
      await refreshMemories();
    } catch (error) { setChatMessages((items) => [...items, { role: 'assistant', content: error instanceof Error ? error.message : String(error) }]); }
  }, [askTask, chatInput, chatMode, coachTurn, refreshMemories, taskId]);

  return { knowledgeDocs, knowledgeResults, knowledgeNote, memories, chatMode, chatInput, chatMessages, chatSources, learningPlans,
    refreshMemories, refreshLearningPlans, changeMode, confirm, reject, remove, saveKnowledgeNote, saveReviewKnowledge,
    startLearning, setPlanStatus, send, query, setKnowledgeNote, setChatInput };
}
