
## 一、增量索引：不要每次都全量重建

**Demo 级做法**：每次有文档更新，把整个知识库重新切片、重新入库。慢，且浪费。

**治理化做法：增量索引**

核心机制是 **文件内容 Hash 比对**：

1. 系统记录每个文件上一次处理时的 MD5/SHA256 哈希值。
    
2. 索引任务启动时，扫描所有文件，计算当前哈希，和记录比对。
    
3. **哈希相同 → 跳过**，文件没变，不用重新处理。
    
4. **哈希不同或新文件 → 标记变更**，只对这些文件重新切片、向量化，生成新版本入库。
    

**好处**：假设你有 10000 个文档，只改了其中 3 个，索引时间从几小时降到几秒。

---

## 二、文档版本管理：不只是“最新版”

**Demo 级做法**：文档更新，旧版本直接覆盖，历史数据丢失。

**治理化做法：历史版本保留，用于审计**

每个文档有多版本，每条 Chunk 都标记它属于哪个文档的哪个版本。

场景举例：

- **回退**：新版本索引质量下降，可以一键切回 V2 版本。
    
- **审计**：客服说“上个月我问过这个问题，AI 回答不是这样的”。你能查到上个月用的是 V3 版本的知识库，当时的回答基于哪段文本。一切可溯源。
    
- **对比调试**：同一个问题，分别用 V3 和 V4 版本的索引去检索，看哪个效果好。
    

**本质上就是把 Git 的思想搬到知识库管理上。**

---

## 三、混合检索：不让任何一种方法独裁

**Demo 级做法**：纯向量检索。把问题转成向量，找最近似的 Chunk。

**问题**：向量擅长“语义相似”，但不擅长“精准命中关键词”。比如用户搜“AK-47”，向量可能返回一堆“步枪”“武器”相关内容，反而找不到包含精确术语“AK-47”的那段文档。

**治理化做法：三层检索堆叠**

|层级|方法|擅长|
|---|---|---|
|第一层|**BM25 关键词检索**|精准命中术语、缩写、编号|
|第二层|**向量语义检索**|理解意思，找“换种说法”的内容|
|第三层|**RRF 融合**|把上面两种结果按排名加权合并|

**RRF（Reciprocal Rank Fusion）融合**是一个公式，简单说就是：“在关键词结果里排名第2，在向量结果里排名第5，综合得分 = 1/2 + 1/5 = 0.7”。两种方法都认为好的排最前。

**LLM Rerank 重排（可选）**：上面三轮跑完后，再拿前几十条结果，让一个轻量级 LLM 逐一打分：“这条和用户问题真的相关吗？几分？”最终只保留最高分的前几条。

**这样的四层漏斗，既召回“意思像的”，也不漏掉“名字对的”。**

---

## 四、文档 ACL 权限控制：不同人搜到不同结果

**Demo 级做法**：所有文档公有，谁搜都一样。

**问题**：企业内部有权限隔离。财务部的文档，研发部不该看到；A 项目组的代码库，B 项目组不该搜到。

**治理化做法：文档 ACL（Access Control List）**

每条 Chunk 入库时就带上权限标签，比如：

```
chunk_id: 12345
content: "..."
doc_id: "财务制度_v2.pdf"
acl: ["finance_team", "cfo", "auditor"]
```

用户搜的时候，系统先筛掉他不该看的 Chunk，再做检索。

**这是在数据库查询阶段就做拦截，不是返回结果后再过滤。** 后者会有两个致命问题：

1. 返回结果数量不准确（说要 10 条，过滤完只剩 2 条）。
    
2. 向量检索时，不可见文档也会占掉排名位置，把本该排在前面的可见文档挤出去。
    

---

## 五、Benchmark 评测体系：用数字说话，不是用感觉

**Demo 级做法**：开发者自己搜几条看看，“嗯，结果还行”，就上线了。

**问题**：你怎么知道调了切片大小、换了嵌入模型之后，效果变好了还是变差了？怎么说服别人“这个 RAG 系统靠谱”？

**治理化做法：内置 Gold Set 黄金测试集 + 自动评测**

### 第一步：构建黄金数据集

人工标注一批“标准问答对”：

~~~
json

{
  "query": "项目什么时候立项的？",
  "relevant_chunks": ["chunk_0001", "chunk_0042"]
}
~~~

### 第二步：自动计算指标

每次你调整了索引策略，系统自动用这些 query 去检索，对比结果和黄金答案，算三个指标：

- **Recall@K**：相关的 Chunk 有没有被找回来？
    
    - 比如 @5 表示“返回的 5 条里，包含了多少条真正相关的”。衡量的是“有没有遗漏”。
        
- **Precision@K**：找回来的 Chunk 里有多少是真正相关的？
    
    - 衡量的是“有没有噪音”。
        
- **MRR（Mean Reciprocal Rank）**：第一个相关结果排在第几名？排得越靠前越好。
    
    - 衡量的是“最好的答案是不是排在了最上面”。




**RAG 在项目里是怎么运作的**

核心调用链大致是：

```
前端/任务/技能
  -> FastAPI 接口
  -> rag_process_graph 或直接 rag_store
  -> rag_store 负责入库 / 查询 / ACL / Gold Set
  -> 返回结果给前端或任务流程
```

你可以把它理解成两条主线：

1. **写入线**
    
    - 扫描项目文件
    - 切成 documents 和 chunks
    - 写进 RAG 存储
2. **读取线**
    
    - 输入问题
    - 先做混合检索
    - 再做 ACL 过滤
    - 必要时再做 LLM rerank
    - 返回 Top N 结果

---

**具体在哪些文件里**

最关键的是这几个：

- [app/persistence/rag_store.py](/F:/JayAgent/Jaycode/app/persistence/rag_store.py)
- [app/api/routes.py](/F:/JayAgent/Jaycode/app/api/routes.py)
- [app/agents/rag_tools.py](/F:/JayAgent/Jaycode/app/agents/rag_tools.py)
- [app/benchmark_runner.py](/F:/JayAgent/Jaycode/app/benchmark_runner.py)

前端对应的调用入口主要在：

- [web/src/api.ts](/F:/JayAgent/Jaycode/web/src/api.ts)
- [web/src/App.tsx](/F:/JayAgent/Jaycode/web/src/App.tsx)

---

**存储在哪里**

这里要分两种后端模式看。

## 1. 默认 SQLite 模式

当前默认配置通常是：

- `JAYCODE_RAG_STORE=sqlite`

这时 RAG 存在本地 SQLite 数据库里，默认路径是：

```
data/dev_agent_studio.db
```

这个路径就在 [app/persistence/rag_store.py](/F:/JayAgent/Jaycode/app/persistence/rag_store.py) 里：

```
def __init__(self, db_path: str | Path = "data/dev_agent_studio.db"):
```

也就是说，SQLite 模式下，RAG 的数据不是散在前端或文件夹里，而是集中放在这个数据库文件中。

### SQLite 里保存的内容包括

- `rag_document`
- `rag_chunk`
- `rag_gold_case`

这些表都在 [app/persistence/rag_store.py](/F:/JayAgent/Jaycode/app/persistence/rag_store.py) 里初始化。

---

## 2. PgVector 模式

如果你把配置切到：

- `JAYCODE_RAG_STORE=pgvector`

并配置：

- `PGVECTOR_DATABASE_URL`
- 或 `DATABASE_URL`

那么 RAG 会存到 PostgreSQL 里，依赖 pgvector 做向量检索。

这部分也在 [app/persistence/rag_store.py](/F:/JayAgent/Jaycode/app/persistence/rag_store.py) 中的 `PgVectorRagStore` 实现里。

---

**RAG 里到底存什么**

这点很重要。

Jaycode 的 RAG 存的不是“整个文件原样文本”这么简单，而是分层存储。

## 1. 文档层 `rag_document`

存的是“文档元信息”和版本信息，比如：

- `collection`
- `path`
- `size`
- `created_at`
- `content_hash`
- `version`
- `is_current`
- `valid_to`
- `acl_json`

这意味着：

- 同一个文件可以有多个版本
- 旧版本不会立刻消失
- 当前版本会标记 `is_current = 1`
- 可以做 ACL 权限控制

## 2. 切片层 `rag_chunk`

存的是切片后的知识片段，比如：

- `chunk_id`
- `path`
- `content`
- `created_at`
- `document_version`

它是查询时真正拿来检索的对象。

## 3. Gold Set `rag_gold_case`

这是评测用的黄金数据集，用于 benchmark。

存的是：

- 问题 `question`
- 期望命中的 chunk id
- 期望命中的路径
- 关键词
- 元数据
- 是否启用

这就是为什么 Jaycode 的 RAG 比一般 demo 更像“可治理知识库”，因为它不仅能查，还能评估查得好不好。

---

**RAG 的入库流程**

RAG 入库有两种方式。

## 方式 1：先扫描，再入库

API 路由里有：

- `POST /rag/process`
- `POST /rag/ingest`

在 [app/api/routes.py](/F:/JayAgent/Jaycode/app/api/routes.py) 中：

- `/rag/process`
    
    - 先调用 `rag_process_graph`
    - 生成 documents / chunks / keywords / faq / report
    - 但不一定写库
- `/rag/ingest`
    
    - 先调用 `rag_process_graph`
    - 再调用 `rag_store.ingest(...)`
    - 真正写入数据库

也就是说：

```
扫描 -> 切片 -> 计算 hash -> 版本判断 -> 写 rag_document / rag_chunk
```

---

## 方式 2：手动添加知识笔记

还有一个更轻的入口：

- `add_note(collection, path, content)`

它也在 [app/persistence/rag_store.py](/F:/JayAgent/Jaycode/app/persistence/rag_store.py) 里。

这个方法适合把：

- 人工总结
- 学习笔记
- 追问结论
- 任务报告
- 审核意见

直接塞进知识库。

在 [app/api/routes.py](/F:/JayAgent/Jaycode/app/api/routes.py) 里你也能看到很多地方会调用它，比如：

- 学习计划沉淀
- 审核备注保存
- memory 确认后写回 RAG

---

**RAG 的查询流程**

查询入口是：

- `POST /rag/query`

对应 [app/api/routes.py](/F:/JayAgent/Jaycode/app/api/routes.py)：

```
results = rag_store.query(request.collection, request.question, request.limit, actor_id=actor_id)
```

查询时会做这几步：

## 1. 取当前 collection 的当前版本 chunk

只查：

- 当前 collection
- 当前版本
- is_current = 1

## 2. ACL 过滤

会根据 `actor_id` 过滤你能不能看这个文档。

也就是说不是所有知识都对所有人可见。

这个逻辑在 [app/persistence/rag_store.py](/F:/JayAgent/Jaycode/app/persistence/rag_store.py) 里的：

- `_acl_allows(...)`

## 3. 混合检索

当前实现不是单纯向量检索，而是混合检索：

- token / 关键词相似度
- BM25 风格分数
- 向量或 token overlap
- RRF 排序

SQLite 模式下，主要是：

- `hybrid_bm25_token_rrf`

PgVector 模式下，主要是：

- `vector_bm25_rrf`

## 4. 可选 LLM rerank

如果你把：

- `JAYCODE_RAG_RERANKER=llm`

打开，系统还会让 LLM 对候选结果重新排序。

这部分也在 [app/persistence/rag_store.py](/F:/JayAgent/Jaycode/app/persistence/rag_store.py) 里。

---

**RAG 的 collection 是什么**

`collection` 就是知识库集合名。

常见的有：

- `default`
- `project-memory`

在前端和 API 里你会经常看到它。

### 它的作用

它相当于知识库的“分类空间”：

- 不同项目可以用不同 collection
- 任务报告可以写到 `project-memory`
- 某次查询可以只查某个 collection

### 典型用途

- 项目分析结果
- 项目知识沉淀
- 学习笔记
- 审核结论
- FAQ
- Gold Set 评测集

---

**RAG 和 Memory 是两套系统**

这个项目里这点很重要。

## RAG

RAG 负责：

- 文档
- 切片
- 检索
- 知识库
- 评测

## Memory

Memory 负责：

- 长期记忆候选
- 用户偏好
- 项目事实
- 团队规则
- 确认 / 拒绝 / 冲突 / 过期

这两个不是同一个东西。

在 [app/persistence/memory_store.py](/F:/JayAgent/Jaycode/app/persistence/memory_store.py) 里你会看到注释已经说明了：

- Memory 是 governed long-term memory candidates
- 它和 RAG corpus 分开

你可以简单理解为：

- **RAG = 知识库**
- **Memory = 长期记忆**

---

**权限是怎么控制的**

RAG 不是完全公开的。

查询时会传一个 `actor_id`，来源有：

- 请求头 `x_devagent_actor`
- 或请求体里的 `actor_id`

然后在 `rag_store.query(...)` 和 `rag_store.list_documents(...)` 里做 ACL 校验。

也就是说：

- 文档可以设置允许哪些 principal 看
- 查询时会过滤你没权限看的 chunk

这个设计在多人协作或治理场景里很重要。

---

**Gold Set 是干什么的**

Gold Set 是“标准答案集合”。

它用于评测 RAG 检索质量。

你可以往里面存：

- question
- 期望命中的 chunk id
- 期望路径
- 关键词

然后 Benchmark 可以用它来算：

- Recall@K
- Precision@K
- MRR
- 其他检索指标

对应接口在 [app/api/routes.py](/F:/JayAgent/Jaycode/app/api/routes.py)：

- `GET /rag/gold-cases`
- `POST /rag/gold-cases`
- `DELETE /rag/gold-cases/{case_id}`

---

**前端是怎么用它的**

前端主要通过这些接口：

- `queryKnowledge(collection, question, limit)`
- `listKnowledgeDocuments(collection)`
- `addKnowledgeNote(collection, path, content)`
- `listRagGoldCases(...)`
- `saveRagGoldCase(...)`

都在 [web/src/api.ts](/F:/JayAgent/Jaycode/web/src/api.ts) 里。

对应到页面上，主要是：

- 追问页里的知识库查询
- 报告页里的知识沉淀
- RAG / Bench 相关页面

---

**你可以把它理解成什么样的系统**

Jaycode 的 RAG 更像一个“知识治理系统”，不是单纯向量检索 demo。

它有这几层：

```
文件/笔记
  -> 切片
  -> 文档版本
  -> chunk
  -> ACL
  -> query
  -> rerank
  -> gold set 评测
  -> benchmark 回归
```

---

**最简短的结论**

### 存在哪里

- 默认存在本地：`data/dev_agent_studio.db`
- 如果切换 PgVector，就存在 PostgreSQL 里

### 怎么运作

- 先把文档切成 chunks
- 存文档版本和切片
- 查询时做混合检索
- 再按 ACL 过滤
- 可选 LLM rerank
- 用 Gold Set 做评测

### 它和 Memory 的区别

- RAG = 文档知识库
- Memory = 长期记忆候选