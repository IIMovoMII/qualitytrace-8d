# QualityTrace 8D：LLM 语义层与失败回退

日期：2026-08-24
状态：代码与 provider-free 定向测试已完成；未执行真实 Provider 兼容性探针

## 1. 为什么接入 LLM

原工作流已经能够用规则完成证据齐备性、对象一致性、规格比较、状态流转、人工审批和幂等控制，但三个所谓 Agent 仍只是确定性职责模块。为了让“AI 辅助 8D 起草”成为实际能力而不是规划描述，本次增加一个可选语义层：把已经通过代码核验的证据、根因候选和整改动作整理为结构化 8D 草稿。

LLM 不负责判断证据是否有效，也不负责确认根因、批准措施、确认有效性或结案。没有模型配置时，工作流继续使用本地结构化草稿；模型失败时也回到同一离线基线。

## 2. 运行链路

```text
合成 case 与可见证据
        ↓
确定性缺件/冲突/对象/规格检查
        ↓
确定性根因候选与整改动作
        ↓
可选 LiteLLM：整理 EightDDraftPayload
        ↓
Pydantic Schema + case_id + evidence allowlist + authority status
        ↓
通过：origin=llm           失败：origin=fallback
        └──────────────┬──────────────┘
                       ↓
        LangGraph 人工审批、outbox、有效性与结案门禁
```

`src/qualitytrace/semantic.py` 实现请求最小化、LiteLLM 适配、JSON 提取、Pydantic 校验、证据白名单、权限状态检查、本地草稿和失败分类。`QualityTraceEngine` 通过依赖注入接收 `SemanticProvider`，因此测试不需要真实网络或凭据。

## 3. 结构化输出

`EightDDraftPayload` 固定包含 D0-D8 九个段落。每段由以下字段组成：

- `text`：待人工复核的草稿文本；
- `evidence_ids`：引用的当前可见证据；
- `status`：`draft` 或 `pending_human_confirmation`。

本地校验要求：

1. `case_id` 必须与当前案件一致；
2. 所有 evidence ID 必须属于本轮白名单；
3. 问题描述、根因候选和纠正措施必须绑定证据；
4. 遏制措施、根因、整改和结案必须保持 `pending_human_confirmation`；
5. `EV-EFFECTIVENESS` 在初始调查阶段不可见，模型不能提前引用未来复检结果。

Provider 支持三种返回约束模式：`json_schema`、`json_object` 和 `prompt_only`。无论上游是否原生支持 JSON Schema，本地 Pydantic 与业务校验都必须执行。

## 4. BYOK 与数据边界

运行时只从环境变量读取：

- `QUALITYTRACE_LLM_MODEL`；
- `QUALITYTRACE_LLM_API_BASE`；
- `QUALITYTRACE_LLM_API_KEY`；
- `QUALITYTRACE_LLM_RESPONSE_MODE`；
- `QUALITYTRACE_LLM_TIMEOUT_SECONDS`。

凭据不写入仓库、SQLite、trace 或输出页面。外发内容仅包括合成 case 的必要字段、当前可见的合成证据、代码已核验的候选根因与纠正措施，以及输出 Schema。Base URL、API Key、未来证据、本地路径和数据库内容不进入 prompt。

真实企业资料不属于当前项目数据。若未来替换为真实业务数据，必须另行完成脱敏、数据出境/供应商授权、最小字段和日志保留审查。

## 5. 失败回退

LLM 每次草稿只尝试一次；下面任一情况都回退到确定性本地草稿：

- LiteLLM 未安装或 Provider 请求失败；
- 超时、空响应或消息结构异常；
- 非法 JSON 或 Pydantic Schema 校验失败；
- case ID 不一致；
- 引用不存在、不可见或未来证据；
- 把需要人工确认的节点标成普通草稿或已完成状态。

回退不会改变根因候选、纠正措施、审批、outbox 或结案规则。`SemanticTrace` 只记录 `mode`、provider、model alias、attempts、失败类别和输入/输出 sha256，不保存原始异常、Prompt 或凭据。

## 6. 验收证据

当前完整离线测试为 `19 passed`，其中新增 6 项语义层测试：

1. 合法结构化输出成功进入工作流；
2. 非 JSON 返回触发本地回退；
3. Provider 异常只调用一次并回退；
4. 不可见 evidence ID 被拒绝；
5. 越过人工权限状态被拒绝；
6. LiteLLM 请求携带 JSON Schema、关闭 SDK 自动重试且配置对象不回显 Key。

这些测试证明适配器、结构化合同和失败安全已经实现，不证明某个真实模型或中转站已经通过兼容性测试。真实兼容性探针只有在使用者自行配置 BYOK 并明确启动 `llm-demo` 后才发生。
