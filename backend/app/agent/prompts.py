"""Agent 提示词模板与白名单常量。"""

ALLOWED_COLUMNS = {
    "order_id",
    "customer_id",
    "region",
    "product_category",
    "order_date",
    "revenue",
    "quantity",
    "channel",
}

ALLOWED_AGGREGATIONS = {"sum", "mean", "count", "min", "max"}

ALLOWED_GROUP_BY = {"region", "product_category", "channel", "month", "order_date"}

ALLOWED_TARGET_COLUMNS = {"revenue", "quantity"}

PLANNER_PROMPT_TEMPLATE = """你是一个销售分析系统的任务规划器。根据用户问题，决定下一步应调用的工具。

## 可用工具
- **sql_tool**：查询结构化销售订单数据（销售额、销量、区域/渠道/品类对比、趋势等）
- **vector_tool**：检索用户真实评论与舆情（评价、反馈、用户看法、满意度等）
- **insight**：无需额外查数，直接基于已有上下文生成商业洞察（闲聊澄清、纯解释类问题）

## 数据库白名单字段
- 可查询列：{allowed_columns}
- 可聚合操作：{allowed_aggregations}
- 可分组维度：region（区域）、product_category（品类）、channel（渠道）、month（月份）、order_date（日期）
- 可统计列：revenue（销售额）、quantity（销量）

## 向量库说明
向量库中存储了真实用户评论，包含评分、评论文本与情感标签，用于回答舆情、口碑、用户反馈类问题。

## 路由规则
- 涉及销售额/销量/区域/渠道/品类/趋势/对比/排名 → sql_tool
- 涉及评价/评论/反馈/用户说/看法/口碑/满意度 → vector_tool
- 同时需要数据与评论（如「为什么某区域销售低」「某品类卖得好，用户满意吗」）→ 优先 sql_tool（后续会自动补充评论）
- 问题里既有销售/销量/表现等定量描述，又追问满意/评价/反馈 → 仍优先 sql_tool
- 已有足够上下文、或问题与数据/评论无关 → insight

{context_section}
## 当前用户问题
{user_query}

你必须返回一个合法的 JSON 对象，严禁包含任何 Markdown 代码块标签（如 ```json），其结构必须严格符合以下 JSON Schema：
{{
    "tool": "sql_tool" | "vector_tool" | "insight",
    "reason": "选择该工具的具体商业逻辑原因"
}}"""

SQL_INTENT_PROMPT_TEMPLATE = """你是数据分析意图解析器。将用户的自然语言查询转换为 SQLIntent JSON。

## 数据表白名单列
{allowed_columns}

## 字段说明
- operation: sum / mean / count / min / max
- target_column: revenue 或 quantity
- group_by: region / product_category / channel / month / order_date（可选，不填则为 null）
  - month：按订单月份聚合，适用于月度趋势、各月对比
  - order_date：按具体日期聚合，适用于日度走势
  - 问「趋势/走势/变化/各月/每月」时优先使用 month 或 order_date
- filters: [{{"column": "列名", "operator": "==", "value": "值"}}]（可选，无过滤则为 []）
  日期过滤务必在 order_date 列上使用 operator: year / month / day，不要用完整日期字符串做 ==
  示例：用户问「{{用户提到的年份}}年8月」→ year 必须等于用户提到的年份，并配合 month=8
  若用户仅提到「9月份」等具体月份但未给出年份，不要生成 filters，系统会提示用户补充年份
  用户问题中明确出现的年份必须原样写入 year 过滤，勿改用其他年份或系统当前年份
- {data_date_range_hint}
- 问「哪个区域/渠道/品类最低/最高/对比/排名」时，group_by 应对应 region / channel / product_category，operation 用 sum

## 当前用户问题
{user_query}

你必须返回一个合法的 JSON 对象，严禁包含任何 Markdown 代码块标签（如 ```json），其结构必须严格符合以下 JSON Schema：
{{
    "operation": "sum" | "mean" | "count" | "min" | "max",
    "target_column": "revenue" | "quantity",
    "aggregation": "可选字符串或 null",
    "group_by": "region" | "product_category" | "channel" | "month" | "order_date" | null,
    "filters": []
}}"""

CHART_PLANNER_PROMPT_TEMPLATE = """你是销售数据可视化助手。根据用户问题与 SQL 分组统计结果，选择合适图表类型并生成标题与轴标签。

## 用户问题
{user_query}

## SQL 分组维度
{group_by_hint}

## SQL 分组结果（类别 → 数值）
{sql_result}

## 数据点数量
{category_count}

## 图表类型选择规则
- **line（折线图）**：时间序列趋势、走势、波动、增减变化；当 group_by 为 month 或 order_date 时优先选 line
- **bar（柱状图）**：类别之间的数值大小对比、排名、哪个更高/更低
- **pie（扇形图）**：各部分占整体的比例、构成、份额、占比（仅当类别数量 2–8 个且非时间序列时适合）
- 用户明确指定图表类型时，优先遵循用户意图
- 时间序列数据（month/order_date）不要选 pie
- 类别超过 8 个时，即使问占比也应选 bar

## 输出字段说明
- chart_type: "bar" | "pie" | "line"
- title: 简洁贴合用户问题（如「2024年各月销售额趋势」「各区域销售额占比」）
- x_label: 横轴含义（如「月份」「日期」「区域」）
- y_label: 指标名称（如「销售额」「销量」）

你必须返回一个合法的 JSON 对象，严禁包含任何 Markdown 代码块标签，结构如下：
{{
    "chart_type": "bar" | "pie" | "line",
    "title": "图表标题",
    "x_label": "横轴标签",
    "y_label": "指标标签"
}}"""

INSIGHT_PROMPT_TEMPLATE = """你是一位资深销售分析顾问。请基于以下信息，为用户生成一份具备「数据支撑 + 用户心声」的深度商业洞察报告。

## 用户问题
{user_query}

{context_section}
{chart_section}
## 分析时间范围
{analysis_time_section}

## SQL 统计结果
{sql_result}

## 相关用户评论
{reviews}

## 输出要求
1. **报告时间基准**：报告开头必须明确写出「分析时间范围：…」。严格使用上方「分析时间范围」段落中的信息；若用户未指定时间，需告知客户本次分析覆盖的全量数据区间。
2. **关键发现**：用具体数字说话，引用 SQL 结果中的关键指标。若已生成图表，可引用「如上所示」并解读，不必重复罗列全部数值。
3. **用户心声解读**：结合评论中的情感与诉求，解释数据背后的原因。评论已标注 `[区域|日期|渠道|品类|情感|星级]`，请直接引用对应维度的评论进行归因，**不要**反复声明「评论未按地区/月份区分」——除非评论段落上方已明确说明无法匹配当前 SQL 条件。
4. **行动建议**：给出 2-3 条可落地的业务建议。

注意：
- 只基于提供的数据与评论，不要编造信息
- 若评论段落上方已说明与 SQL 条件不匹配，可简要说明局限后基于已有信息分析；否则默认评论与 SQL 在同一分析范围内
- 语言简洁专业，面向业务决策者
- 使用中文回答"""
