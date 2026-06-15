# AI Sales Analytics Copilot

面向商业销售与运营决策的对话式 BI Agent 系统。

---

## 项目简介

**AI Sales Analytics Copilot** 是一款面向销售与运营团队的对话式商业智能（BI）分析助手。用户通过自然语言提问，系统即可自动完成销售数据统计、用户评论检索、图表生成与商业洞察输出，无需编写 SQL 或操作传统 BI 工具。

系统基于 **LangGraph** 构建多节点 Agent 工作流，将「结构化查询意图 + SQLAlchemy Core 安全构建」与 **ChromaDB** 向量检索混合编排，并通过 **FastAPI SSE** 实时推送节点状态与洞察内容，前端以 **React + Recharts** 呈现流式对话与动态图表。

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | Python 3.11+、FastAPI、Uvicorn |
| Agent 编排 | LangGraph、OpenAI 兼容 API |
| 数据存储 | MySQL（asyncmy 异步访问）、ChromaDB（本地持久化） |
| 向量嵌入 | Sentence Transformers（BAAI/bge-small-zh-v1.5） |
| 查询构建 | SQLAlchemy Core、Pydantic |
| 流式传输 | SSE（sse-starlette） |
| 前端 | React 19、TypeScript、Vite、Tailwind CSS |
| 图表渲染 | Recharts |

---

## 核心功能

- **多节点 Agent 工作流** — Planner → SQL Tool / Vector Tool → Chart Spec → Insight，固定拓扑、路径有界
- **安全可控的数据查询** — LLM 输出结构化 `SQLIntent`，后端经白名单校验后由 SQLAlchemy Core 动态构建 SQL，拦截越权查询与注入风险
- **混合检索** — MySQL 存储销售订单，ChromaDB 存储评论向量；支持纯定量统计、纯舆情检索及「数据 + 评论」归因分析链路
- **流式响应** — SSE 推送节点状态（`node_start`、`sql_result`、`reviews`、`chart_spec`）与 Insight 逐字输出
- **智能可视化** — LLM 结合规则选择柱状图 / 折线图 / 扇形图，生成 Chart Spec 并由 Recharts 渲染
- **前端聊天界面** — 会话管理、CSV 拖拽上传、流式打字机效果、图表动态嵌入消息

---

## 架构亮点

### Agent 工作流

```text
planner
  ├─ sql_tool ──┬─ vector_tool ──┬─ chart_spec ── insight ── END
  │             │                └─ insight ──────────────── END
  │             ├─ chart_spec ── insight ── END
  │             └─ insight ──────────────── END
  ├─ vector_tool ──┬─ chart_spec ── insight ── END
  │                └─ insight ──────────────── END
  └─ insight ──────────────────────────────── END
```

- **Planner**：根据用户问题路由至 `sql_tool`、`vector_tool` 或直接 `insight`
- **SQL Tool**：解析自然语言为 `SQLIntent`，白名单校验列名与操作符后执行聚合查询
- **Vector Tool**：BGE 嵌入 + ChromaDB 语义检索，默认返回 Top-5 相关评论
- **Chart Spec**：对可图表化的分组 SQL 结果，LLM 选图 + 规则降级（时间序列优先折线、类别过多降级柱状图）
- **Insight**：融合 SQL 结果、评论与图表信息，流式生成商业洞察报告

### 安全查询设计

LLM **不直接生成 SQL 字符串**，而是输出受 Pydantic 约束的查询意图 JSON：

```json
{
  "operation": "sum",
  "target_column": "revenue",
  "group_by": "region",
  "filters": [{"column": "channel", "operator": "==", "value": "线上"}]
}
```

后端通过 `ALLOWED_COLUMNS`、`ALLOWED_AGGREGATIONS` 白名单与操作符映射，用 SQLAlchemy Core 安全构建并执行查询。

### 数据入库策略

- **销售数据（MySQL）**：CSV 上传后全量覆盖写入 `sales_orders` 表
- **评论数据（MySQL + ChromaDB）**：MySQL 批量插入 `reviews` 表；向量写入 Chroma 时按 **500 条分块**，并以 **asyncio 并发（10 路）** 提升效率

---

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- MySQL 8.0+
- OpenAI 兼容 LLM API Key（如 DeepSeek、GPT 等）

### 1. 克隆项目

```bash
git clone <repository-url>
cd ai-sales-agentics-copilot
```

### 2. 配置后端

```bash
cd backend
cp .env.example .env
```

编辑 `backend/.env`，至少配置以下项：

```env
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=sales_copilot

OPENAI_API_KEY=your_api_key
MODEL_NAME=deepseek-chat
MODEL_BASE_URL=https://api.deepseek.com/v1
```

创建 MySQL 数据库：

```sql
CREATE DATABASE sales_copilot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

安装依赖并启动后端：

```bash
pip install -r requirements.txt
python run.py
```

后端默认运行于 `http://localhost:8000`，启动时自动建表。

### 3. 配置并启动前端

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

前端默认运行于 `http://localhost:5173`，开发模式下通过 Vite 代理转发 `/api` 至后端。

### 4. 导入测试数据（可选）

生成示例 CSV：

```bash
cd backend/数据测试
python generate_test_data.py
```

在浏览器打开 `http://localhost:5173/upload`，分别上传 `sales_data.csv` 与 `reviews_data.csv`。

**销售数据 CSV 列**：`order_id`, `customer_id`, `region`, `product_category`, `order_date`, `revenue`, `quantity`, `channel`

**评论数据 CSV 列**：`review_id`, `order_id`, `rating`, `comment`, `sentiment`

### 5. 开始对话

访问 `http://localhost:5173`，创建会话后即可提问，例如：

- 「各区域销售额对比」
- 「2024 年各月销售额趋势」
- 「华东区销售低的原因，用户怎么说？」

---

## API 概览

所有业务接口前缀为 `/api/v1`。

### 健康检查

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 服务状态与当前模型名称 |

### 会话管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/conversations` | 创建会话 |
| `GET` | `/api/v1/conversations/user/{user_id}` | 获取用户会话列表 |
| `PUT` | `/api/v1/conversations/{conversation_id}` | 更新会话标题 |
| `DELETE` | `/api/v1/conversations/{conversation_id}` | 删除会话（软删除） |
| `GET` | `/api/v1/conversations/{conversation_id}/messages` | 获取会话消息历史 |

**创建会话请求示例：**

```json
{
  "user_id": "user_abc123",
  "title": "新会话"
}
```

### 对话流式接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/chat/stream` | SSE 流式对话（核心接口） |

**请求体：**

```json
{
  "conversation_id": "conv_xxx",
  "user_id": "user_abc123",
  "message": "各区域销售额对比"
}
```

**SSE 事件类型：**

| 事件 | 说明 |
|------|------|
| `node_start` | Agent 节点开始执行 |
| `planner_decision` | Planner 路由决策（工具 + 原因） |
| `sql_result` | SQL 查询结果 |
| `reviews` | 向量检索到的评论列表 |
| `chart_spec` | 图表规格（类型、标题、数据点） |
| `text_chunk` | Insight 逐字流式文本 |

### 数据上传

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/upload/sales` | 上传销售 CSV（`multipart/form-data`，字段名 `file`） |
| `POST` | `/api/v1/upload/reviews` | 上传评论 CSV（同步写入 MySQL 与 ChromaDB） |

---

## 项目结构

```text
ai-sales-agentics-copilot/
├── backend/
│   ├── app/
│   │   ├── agent/          # LangGraph 工作流、工具、图表逻辑
│   │   ├── api/            # FastAPI 路由（chat / conversation / upload）
│   │   ├── database/       # MySQL + ChromaDB 客户端
│   │   ├── models/         # ORM 模型
│   │   ├── repositories/   # 数据访问层
│   │   └── services/       # 业务服务
│   ├── test/               # 后端测试
│   ├── 数据测试/            # 测试数据生成脚本
│   ├── requirements.txt
│   └── run.py
├── frontend/
│   ├── src/
│   │   ├── components/     # 聊天、图表、侧边栏组件
│   │   ├── pages/          # Chat、Upload 页面
│   │   └── services/       # API 与 SSE 客户端
│   └── package.json
└── README.md
```

---

## License

See [LICENSE](LICENSE).

---

# AI Sales Analytics Copilot

A conversational BI Agent for sales and operations decision-making.

---

## Overview

**AI Sales Analytics Copilot** is a conversational business intelligence (BI) assistant built for sales and operations teams. Users ask questions in natural language, and the system automatically performs sales data aggregation, user review retrieval, chart generation, and business insight synthesis — no SQL or traditional BI tooling required.

Powered by a **LangGraph** multi-node Agent workflow, the system orchestrates **structured query intents + SQLAlchemy Core safe query building** with **ChromaDB** vector retrieval. **FastAPI SSE** streams node status and insight text in real time, while the **React + Recharts** frontend delivers a streaming chat experience with dynamic charts.

---

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| Backend | Python 3.11+, FastAPI, Uvicorn |
| Agent Orchestration | LangGraph, OpenAI-compatible API |
| Data Storage | MySQL (asyncmy async driver), ChromaDB (local persistence) |
| Embeddings | Sentence Transformers (BAAI/bge-small-zh-v1.5) |
| Query Building | SQLAlchemy Core, Pydantic |
| Streaming | SSE (sse-starlette) |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS |
| Charts | Recharts |

---

## Core Features

- **Multi-node Agent workflow** — Planner → SQL Tool / Vector Tool → Chart Spec → Insight, with a fixed topology and bounded execution paths
- **Safe, controlled data queries** — LLM outputs structured `SQLIntent`; the backend validates against whitelists and builds SQL via SQLAlchemy Core, blocking unauthorized queries and injection risks
- **Hybrid retrieval** — MySQL for sales orders, ChromaDB for review vectors; supports pure quantitative stats, sentiment retrieval, and combined attribution analysis
- **Streaming responses** — SSE pushes node status (`node_start`, `sql_result`, `reviews`, `chart_spec`) and token-by-token Insight output
- **Intelligent visualization** — LLM + rule-based chart type selection (bar / line / pie), Chart Spec generation, and Recharts rendering
- **Chat UI** — Session management, CSV drag-and-drop upload, typewriter streaming effect, and inline chart rendering

---

## Architecture Highlights

### Agent Workflow

```text
planner
  ├─ sql_tool ──┬─ vector_tool ──┬─ chart_spec ── insight ── END
  │             │                └─ insight ──────────────── END
  │             ├─ chart_spec ── insight ── END
  │             └─ insight ──────────────── END
  ├─ vector_tool ──┬─ chart_spec ── insight ── END
  │                └─ insight ──────────────── END
  └─ insight ──────────────────────────────── END
```

- **Planner** — Routes user queries to `sql_tool`, `vector_tool`, or directly to `insight`
- **SQL Tool** — Parses natural language into `SQLIntent`, validates columns/operators against whitelists, and executes aggregation queries
- **Vector Tool** — BGE embeddings + ChromaDB semantic search, returning Top-5 relevant reviews by default
- **Chart Spec** — For groupable SQL results, LLM selects chart type with rule-based fallbacks (time series → line, too many categories → bar)
- **Insight** — Streams a business insight report synthesizing SQL results, reviews, and chart context

### Safe Query Design

The LLM **does not generate raw SQL strings**. Instead, it outputs Pydantic-constrained query intent JSON:

```json
{
  "operation": "sum",
  "target_column": "revenue",
  "group_by": "region",
  "filters": [{"column": "channel", "operator": "==", "value": "线上"}]
}
```

The backend enforces `ALLOWED_COLUMNS` and `ALLOWED_AGGREGATIONS` whitelists with operator mapping, then safely builds and executes queries via SQLAlchemy Core.

### Data Ingestion Strategy

- **Sales data (MySQL)** — CSV upload triggers a full replace into the `sales_orders` table
- **Review data (MySQL + ChromaDB)** — Batch insert into `reviews`; vector writes to Chroma are **chunked in batches of 500** with **asyncio concurrency (10 workers)**

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- MySQL 8.0+
- OpenAI-compatible LLM API key (e.g., DeepSeek, GPT)

### 1. Clone the Repository

```bash
git clone <repository-url>
cd ai-sales-agentics-copilot
```

### 2. Configure the Backend

```bash
cd backend
cp .env.example .env
```

Edit `backend/.env` with at minimum:

```env
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=sales_copilot

OPENAI_API_KEY=your_api_key
MODEL_NAME=deepseek-chat
MODEL_BASE_URL=https://api.deepseek.com/v1
```

Create the MySQL database:

```sql
CREATE DATABASE sales_copilot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Install dependencies and start the server:

```bash
pip install -r requirements.txt
python run.py
```

The backend runs at `http://localhost:8000` and auto-creates tables on startup.

### 3. Configure and Start the Frontend

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

The frontend runs at `http://localhost:5173`. In dev mode, Vite proxies `/api` requests to the backend.

### 4. Import Test Data (Optional)

Generate sample CSV files:

```bash
cd backend/数据测试
python generate_test_data.py
```

Open `http://localhost:5173/upload` in your browser and upload `sales_data.csv` and `reviews_data.csv`.

**Sales CSV columns**: `order_id`, `customer_id`, `region`, `product_category`, `order_date`, `revenue`, `quantity`, `channel`

**Reviews CSV columns**: `review_id`, `order_id`, `rating`, `comment`, `sentiment`

### 5. Start Chatting

Visit `http://localhost:5173`, create a session, and try questions like:

- "Compare sales revenue across regions"
- "Monthly sales revenue trend for 2024"
- "Why are sales low in East China? What are users saying?"

---

## API Reference

All business endpoints are prefixed with `/api/v1`.

### Health Check

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Service status and current model name |

### Conversation Management

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/conversations` | Create a conversation |
| `GET` | `/api/v1/conversations/user/{user_id}` | List conversations for a user |
| `PUT` | `/api/v1/conversations/{conversation_id}` | Update conversation title |
| `DELETE` | `/api/v1/conversations/{conversation_id}` | Delete a conversation (soft delete) |
| `GET` | `/api/v1/conversations/{conversation_id}/messages` | Get message history |

**Create conversation request example:**

```json
{
  "user_id": "user_abc123",
  "title": "New Chat"
}
```

### Streaming Chat

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/chat/stream` | SSE streaming chat (core endpoint) |

**Request body:**

```json
{
  "conversation_id": "conv_xxx",
  "user_id": "user_abc123",
  "message": "Compare sales revenue across regions"
}
```

**SSE event types:**

| Event | Description |
|-------|-------------|
| `node_start` | Agent node execution started |
| `planner_decision` | Planner routing decision (tool + reason) |
| `sql_result` | SQL query result |
| `reviews` | Retrieved review list from vector search |
| `chart_spec` | Chart specification (type, title, data points) |
| `text_chunk` | Token-by-token Insight streaming text |

### Data Upload

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/upload/sales` | Upload sales CSV (`multipart/form-data`, field name `file`) |
| `POST` | `/api/v1/upload/reviews` | Upload reviews CSV (writes to both MySQL and ChromaDB) |

---

## Project Structure

```text
ai-sales-agentics-copilot/
├── backend/
│   ├── app/
│   │   ├── agent/          # LangGraph workflow, tools, chart logic
│   │   ├── api/            # FastAPI routes (chat / conversation / upload)
│   │   ├── database/       # MySQL + ChromaDB clients
│   │   ├── models/         # ORM models
│   │   ├── repositories/   # Data access layer
│   │   └── services/       # Business services
│   ├── test/               # Backend tests
│   ├── 数据测试/            # Test data generation scripts
│   ├── requirements.txt
│   └── run.py
├── frontend/
│   ├── src/
│   │   ├── components/     # Chat, chart, sidebar components
│   │   ├── pages/          # Chat, Upload pages
│   │   └── services/       # API and SSE client
│   └── package.json
└── README.md
```

---

## License

See [LICENSE](LICENSE).
