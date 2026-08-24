# QualityTrace 8D 数据来源与合成规则

日期：2026-08-21

当前数据集：`QT8D-SYNTHETIC-20260821-A`

生成器版本：`1.0.0`

真实性结论：全部业务记录和内部规则均为原创合成资料，不是客户数据、工厂事故或企业 SOP。

## 一句话说明

这个项目没有可公开使用的真实工厂历史数据，因此没有让模型自由编故事，也没有把 GitHub 示例冒充企业数据。实际做法是：用公开项目确定字段关系，用公开 8D 方法确定流程边界，再用一个带固定种子、业务约束和自动校验的本地生成器生产完整案例、失败变体和历史案例。

## 最终有哪些数据

| 数据层 | 实际内容 | 数量 | 用途 |
|---|---|---:|---|
| 合成内部规则 | 来料检验、规格变更、不合格隔离、供应商纠正、审批矩阵、有效性结案 | 6 份 | 约束证据、权限和状态迁移 |
| 母案例 | `REV-7` 生效后，合成供应商仍使用 `REV-6` 工装，5 件初检中 2 件超上限 | 1 个 | 所有路径的同一事实基线 |
| 受控路径 | complete、missing evidence、conflict、wrong object、tool failure recovery | 5 条 | 验证正常、缺件、冲突、越权和恢复 |
| 合成历史案例 | 旧工装、过期校准误报、批次串错 | 3 条 | 提出候选检查方向，不证明当前根因 |
| 独立证据文件 | 批次、规格、初检、供应商回复、复检及冲突回复 | 25 份 | 让每个 evidence ID 都能落到实际文件 |

`5` 条路径不是 5 个互不相关的故事，而是 `1` 个母案例按 `5` 种声明过的 mutation 派生。这样路径差异可以归因，不会同时改规则、事实和预期状态。

## GitHub 项目里的数据从哪里来

### ERPNext：字段和状态来自业务对象，测试数据由代码创建

[frappe/erpnext](https://github.com/frappe/erpnext) 在本次快照为 38,329 stars、12,546 forks、GPL-3.0。`Quality Inspection` 定义了检验类型、引用对象、物料、批次、样本量、模板、读数、检验人、验证人和状态；`Quality Inspection Reading` 定义规格、上下限、逐件读数和 Accepted/Rejected；Non Conformance 与 Quality Action 再记录问题、流程负责人、纠正/预防措施、责任人和完成日期。

它的测试并不是一套可直接拿来讲的真实制造业事故库，而是通过 `_Test Item`、`create_quality_inspection()` 等测试构造器生成记录，再验证超规格阻断、上下限判定和状态变化。因此本项目采用其“对象和关系”，不复制测试记录，也不声称 ERPNext 提供了我们的案例。

### DataFlow：数据不是一次生成完，而是流水线处理

[OpenDCAI/DataFlow](https://github.com/OpenDCAI/DataFlow) 在快照时为 7,632 stars、1,042 forks、Apache-2.0。源码里的 SFT pipeline 明确拆分 generator、refiner 和 filter；seed generator 从原始内容生成结构化字段，无法解析的输出不会直接混入结果。

QualityTrace 借用的是“生成、规范化、规则过滤、保存中间结果”的思路。由于本项目只有一个小型数值场景，实际生成器用 Python 标准库和确定性公式，不调用 LLM 造数据。

### SDV：先定义元数据和约束，再评价合成数据

[sdv-dev/SDV](https://github.com/sdv-dev/SDV) 在快照时为 3,548 stars、419 forks，当前采用 Business Source License。其 README 的示例数据是 fictional hotel guests，并同时提供列类型、主键等 metadata；SDV 可从真实表学习分布，保留主外键关系和业务约束，再比较真实/合成数据质量。

本项目没有真实工厂表可供学习，因此没有声称“保持了真实分布”，也没有引入 SDV 运行时。只迁移三条方法：字段元数据显式化、跨字段约束显式化、生成后逐条验证。

### Faker：适合身份类假数据和固定种子，本项目不需要安装

[joke2k/faker](https://github.com/joke2k/faker) 在快照时为 19,370 stars、2,110 forks、MIT。它通过 provider 生成虚构姓名、地址等数据，支持唯一值和固定 seed，但同一个 seed 只有在依赖版本固定时才能保证完全相同。

QualityTrace 没有姓名、地址或个人资料，所以不为了“看起来专业”增加 Faker 依赖。项目只采用固定种子和虚构 ID 的原则，ID 模板由本地规范直接控制。

### AWS 制造业合成示例：只作异常注入旁证

[AWS 的制造业合成数据示例](https://github.com/aws-samples/amazon-bedrock-synthetic-manufacturing-data-generator) 只有 14 stars、2 forks、MIT-0，采用度不足以主导架构。它的 README 展示了先生成设备清单，再生成按分钟时间戳和偶发异常的传感器数据。

本项目只借鉴“异常必须由明确规则注入”这一点，没有采用 Bedrock、Lambda、DynamoDB、CodePipeline 或一年传感器数据。

所有仓库的精确 revision、检查路径、许可证和采用边界保存在 `data/source_register.json`。

## 小红书项目经验带来的约束

小红书材料只作实践信号，不是企业制度或科学证据：

- 《质量工程师的 AI 实操：8D 报告20 min 搞定》给出的实际输入边界是问题描述、5M1E 排查结果、测量对比和人工确认的根因；AI 可以起草，但数字、根因链和责任/期限必须由人核对。
- 《Agent 工具轨迹数据怎么构造？》强调轨迹要保留目标、工具、参数、结果、最终回答、失败样本和无需工具的任务。
- PKU-DCAI 的 DataFlow 笔记提出“生成→评估→过滤→精炼”，本项目又回到 GitHub 源码交叉核验后才采用。
- 《（小踩坑）Kaggle 代码做轨迹数据合成》提醒，不能从一个完成答案倒推一条看似完美的假轨迹；更合理的是从可执行母体派生并保留失败。
- 《FDE-从数据标注到Agent交付》只作为“Agent 失败可能源于数据质量”的个人经验信号，不用来证明本项目效果。

因此，QualityTrace 的失败路径由同一母案例在执行前注入，工具错误会留在 trace；不会先跑出想要的终态，再补一条假的过程。

## 精确生成规则

生成规范位于 `data/generation_spec.json`，固定 seed 为 `20260821`：

1. 名义值 `N=10.00 mm`，公差 `T=0.05 mm`，合格区间为 `[N-T, N+T] = [9.95, 10.05]`。
2. 初检共 5 件：3 件从 `N ± 0.6T` 内生成，2 件从 `N + [2.4T, 3.8T]` 生成并随机打乱。本次固定结果为 `9.97、10.03、10.14、10.15、10.03`，程序重新计算得到 2 件超差。
3. 纠正后复检共 5 件，全部从 `N ± 0.4T` 内生成。本次固定结果为 `10.01、10.00、9.99、9.98、10.00`，程序重新计算得到 0 件超差。
4. complete 不改母案例；missing evidence 只删除 `EV-SUPPLIER`；conflict 只新增一份相反工装版本回复；wrong object 只替换批次证据中的批次/供应商；tool failure recovery 只让第一次只读调用失败，事实不变。
5. 复检文件虽然属于完整生命周期数据，但初始调查工具会主动排除 `effectiveness` 类型，只有措施执行后显式调用 `add_effectiveness` 才进入结案门禁，防止看到未来答案。

这些读数、5 件门槛、48 小时回复和 2 天措施期限都是 POC 内部规则，不是抽样标准、供应商协议或行业 KPI。

## 自动检查什么

`scripts/generate_synthetic_data.py --check` 会核验：

- 同一 seed 和规范是否得到完全一致的 case/history；
- 5 条变体是否只改变声明过的维度；
- 每个 evidence source 是否有本地文件；
- 每个 policy reference 是否能解析到 6 份规则之一；
- 样本量、逐件读数和 `out_of_spec` 是否一致；
- 批次、供应商、单位、规格生效日和代表测量值是否互相一致；
- 25 份证据文件、生成结果和输入规则的 SHA-256 是否与 manifest 一致。

工作流还会单独执行权限和结案门禁：只有 `quality_manager` 的持久化决定可以批准措施和确认有效性；复检样本不足、对象错误、规格版本错误或存在超差读数时不能关闭。

## 文件入口

| 文件 | 作用 |
|---|---|
| `data/source_register.json` | GitHub/XHS 来源、revision、许可证和采用边界 |
| `data/rule_registry.json` | 6 份规则索引及机器可读门槛 |
| `data/generation_spec.json` | seed、母案例、变体和数值公式 |
| `data/policies/` | 6 份原创合成内部规则 |
| `data/schemas/qualitytrace_case.schema.json` | case/evidence JSON Schema |
| `data/generated/cases.json` | 5 条可运行路径 |
| `data/generated/history_cases.json` | 3 条合成历史案例 |
| `data/generated/evidence/` | 25 份独立证据文件 |
| `data/generated/manifest.json` | 输入和输出哈希、生成统计、真实性标记 |

## 运行与复核

```powershell
.\run_project.ps1 generate-data
.\run_project.ps1 check-data
.\run_project.ps1 acceptance
```

`generate-data` 会按冻结规范重建本项目数据；`check-data` 只读核验；`acceptance` 回放五条业务路径。项目不需要联网，也不读取任何模型凭据。
