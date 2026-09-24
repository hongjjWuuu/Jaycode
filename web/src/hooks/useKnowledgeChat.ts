import { useCallback, useState } from 'react';
import { chatLearningCoach, createTaskLearningPlan, listLearningPlans, updateLearningPlanStatus } from '../services/learning';
import {
  addKnowledgeNote, confirmMemory, deleteMemory, extractMemoryCandidates,
  listKnowledgeDocuments, listMemories, queryKnowledge, rejectMemory,
} from '../services/rag';
import type { LearningPlanRecord, MemoryRecord, RagDocument, RagResult } from '../types';

export type ChatMode = 'task' | 'knowledge' | 'coach';
export type ChatMessage = { role: 'user' | 'assistant'; content: string; source?: string; day?: number | null; theme?: string | null };

export function useKnowledgeChat() {
  const [knowledgeDocs, setKnowledgeDocs] = useState<RagDocument[]>([]);
  const [knowledgeResults, setKnowledgeResults] = useState<RagResult[]>([]);
  const [knowledgeNote, setKnowledgeNote] = useState('');
  const [memories, setMemories] = useState<MemoryRecord[]>([]);
  const [chatMode, setChatMode] = useState<ChatMode>('task');
  const [chatInput, setChatInput] = useState('这个项目我应该先看哪些模块？');
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatSources, setChatSources] = useState<RagResult[]>([]);
  const [learningPlans, setLearningPlans] = useState<LearningPlanRecord[]>([]);

  const refreshMemories = useCallback(async () => setMemories(await listMemories()), []);
  const refreshLearningPlans = useCallback(async (taskId?: string) => setLearningPlans(await listLearningPlans(taskId)), []);
  const confirm = useCallback(async (memoryId: string) => { await confirmMemory(memoryId); await refreshMemories(); }, [refreshMemories]);
  const reject = useCallback(async (memoryId: string) => { await rejectMemory(memoryId); await refreshMemories(); }, [refreshMemories]);
  const remove = useCallback(async (memoryId: string) => { await deleteMemory(memoryId); await refreshMemories(); }, [refreshMemories]);
  const setPlanStatus = useCallback(async (planId: string, status: LearningPlanRecord['status']) => updateLearningPlanStatus(planId, status), []);

  return { knowledgeDocs, setKnowledgeDocs, knowledgeResults, setKnowledgeResults, knowledgeNote, setKnowledgeNote,
    memories, chatMode, setChatMode, chatInput, setChatInput, chatMessages, setChatMessages, chatSources, setChatSources,
    learningPlans, refreshMemories, refreshLearningPlans, confirm, reject, remove, setPlanStatus,
    chatLearningCoach, createTaskLearningPlan, addKnowledgeNote, extractMemoryCandidates,
    listKnowledgeDocuments, queryKnowledge,
  };
}
