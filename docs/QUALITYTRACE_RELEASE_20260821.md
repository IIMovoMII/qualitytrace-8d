# QualityTrace 8D 成品说明

## 真实工作问题

来料检验发现关键规格偏差后，质量人员通常要在批次记录、规格版本、检验报告和供应商回复之间来回核对。真正危险的是：证据不全却先推进、对象串错、网络/工具失败后重复建单，以及措施没有经过授权就写进外部系统。

QualityTrace 8D 把这条链路做成一个有限状态工作流：每一步都有输入、输出、证据 ID 和可恢复的 checkpoint；模型可以帮助整理候选根因和措施草案，但不能替代证据门禁和人工决定。

## 8D 对应关系

| 阶段 | 成品行为 |
|---|---|
| D0 | 建立 case、批次和发现环节 |
| D1/D2 | 绑定批次、规格、检验和供应商证据 |
| D3 | 形成隔离/遏制措施草案，未经批准不写副作用 |
| D4 | 从规格、实测和供应商回复提出根因候选 |
| D5/D6 | 生成人工可审的纠正措施，并登记 owner/due_days |
| D7 | 等待复检证据并由质量负责人确认有效性 |
| D8 | 留下完整 trace，进入 `closed` |

## 为什么用 LangGraph + SQLite

LangGraph 负责把节点和条件路由显式化；本地 SQLite 负责保存每次 revision、HumanDecision、outbox event 和 ActionReceipt。这样进程中断后可以从最后一个状态恢复，`case_id + action_version` 又能保证同一措施重复提交只得到同一张本地收据。

## 数据层已经落到实际文件

当前冻结数据集为 `QT8D-SYNTHETIC-20260821-A`：1 个母案例派生 5 条路径，包含 3 条合成历史案例、6 份合成内部规则和 25 份独立证据文件。生成器使用 seed `20260821`，把规格、公差、初检异常、纠正后复检和每种 Bad Case mutation 写在 `data/generation_spec.json`，再将全部输入/输出 hash 写入 `data/generated/manifest.json`。

初始调查阶段只读取批次、规格、初检和供应商回复，主动排除未来的复检证据；措施执行后才能显式加入 `EV-EFFECTIVENESS`。工作流会代码核验批次/供应商对象、规格生效日、单位、初检样本量、逐件读数和超规格数量，结案时再核验复检至少 5 件、0 件超差、规格版本一致和 `quality_manager` 的持久化决定。

字段模型参考 ERPNext，生成→过滤思路参考 DataFlow，metadata/constraint 思路参考 SDV；所有业务值和规则均为原创合成。完整尽调与生成规则见 `DATA_PROVENANCE_AND_SYNTHETIC_GENERATION_20260821.md`。

## 成品验收

五条路径均有独立 fixture 和测试：完整路径最终关闭；缺件路径停在 `awaiting_evidence`；冲突和对象不一致进入 `blocked`；工具临时失败按最多两次只读重试后继续。新增测试还覆盖生成确定性、hash、规则引用、变体隔离、未授权审批、初检样本不足、复检样本不足和未来证据隔离。当前离线套件为 `13 passed`。QualityTrace 不读取 Minos Bench，不共享 EvidenceGate 的 corpus/索引，也不使用 Judge 分数。

## 2026-08-24 公开发布

- 公开仓库：`https://github.com/IIMovoMII/qualitytrace-8d`，public，MIT License。
- 公开候选共 `68` 个受控文件；`.env`、虚拟环境、SQLite、trace、outbox 运行工件和归档材料均未进入 Git。
- 全部 `13` 项 provider-free 测试、一键 acceptance、生成数据 hash 核验和公开提交安全审计均通过。
- GitHub Actions“离线测试与安全审计”已通过。公开 README 按真实问题、状态图、快速开始、数据、失败安全、验证和方法边界组织。
