---
document_id: QT-POL-003
title: 不合格批次隔离与对象边界规则
version: "1.0"
effective_date: 2026-08-21
scope: QualityTrace 8D 合成来料规格偏差场景
authority_role: synthetic_internal_policy
not_real_company_policy: true
---

# 不合格批次隔离与对象边界规则

本文件是为个人 POC 原创编写的合成规则，不代表任何真实企业的库存处置制度。

## 隔离规则

- 初检出现超规格读数后，目标批次必须保持“禁止直接放行”的状态，直到纠正措施和有效性验证分别完成审批。
- 隔离动作必须绑定当前 `case_id`、批次和供应商，不能把另一批次的记录作为当前对象。
- 批次证据与案件目标不一致时，工作流进入 `blocked`，不创建整改任务，也不修改任何其他对象。

## 数据边界

本 POC 的副作用只写入本地 outbox 和 SQLite 收据，不连接真实 ERP/MES，也不代表真实库存已经被冻结。

## 方法来源边界

字段关系参考 ERPNext 的 Non Conformance、Quality Inspection 和库存放行测试；“错误对象必须阻断”是本项目的安全规则。
