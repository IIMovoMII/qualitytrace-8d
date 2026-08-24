---
document_id: QT-POL-005
title: 质量工作流审批权限矩阵
version: "1.0"
effective_date: 2026-08-21
scope: QualityTrace 8D 合成来料规格偏差场景
authority_role: synthetic_internal_policy
not_real_company_policy: true
---

# 质量工作流审批权限矩阵

本文件是为个人 POC 原创编写的合成规则，不代表任何真实企业的授权表。

| 角色 | 可以做 | 不可以做 |
|---|---|---|
| `quality_engineer` | 登记案件、补充证据、提出调查意见 | 批准自己生成的纠正措施、关闭案件 |
| `supplier_quality` | 提交供应商回复、执行已批准措施 | 批准措施、确认有效性、关闭案件 |
| `quality_manager` | 批准或拒绝纠正措施、确认或拒绝有效性 | 绕过证据完整性和对象一致性门禁 |
| Agent/模型 | 整理证据、提出候选根因、起草措施 | 认定最终根因、签发措施、确认有效性、关闭案件 |

只有持久化的 `HumanDecision` 且角色为 `quality_manager` 时，才允许创建措施副作用或确认有效性。文本里出现“已批准”不构成权限。

## 方法来源边界

角色与提交/验证关系参考 ERPNext 质量对象中的 inspector、verifier、process owner 和权限设计；本矩阵由本项目按人机责任边界重新定义。
