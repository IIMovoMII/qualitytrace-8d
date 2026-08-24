---
document_id: QT-POL-001
title: 来料检验与规格判定规则
version: "1.0"
effective_date: 2026-08-21
scope: QualityTrace 8D 合成来料规格偏差场景
authority_role: synthetic_internal_policy
not_real_company_policy: true
---

# 来料检验与规格判定规则

本文件是为个人 POC 原创编写的合成规则，不代表任何真实企业的 SOP。

## 必需记录

来料检验记录必须绑定批次、供应商、产品、检验日期、抽样数量、检测设备、适用规格版本、单位和逐件读数。缺少批次、规格、检验或供应商回复中的任一项时，只能列出缺口，不能进入根因确认和措施批准。

## 判定方法

- 本场景的最低初检样本量为 5 件。这个数字只用于本 POC 的可重复验收，不声称是通用行业抽样标准。
- 数值型规格下限为 `nominal - tolerance`，上限为 `nominal + tolerance`，上下限均包含在合格范围内。
- 任一读数超出上下限，该批次在本场景中判为不合格并进入隔离流程；模型不能改写测量值或自行放行。
- 非数字、缺单位、规格版本未知或检测对象不一致时，结果记为证据不完整，不把格式错误猜成测量结果。

## 方法来源边界

字段关系参考 ERPNext `Quality Inspection`、`Quality Inspection Reading` 及其测试中的批次、样本量、上下限、读数和 Accepted/Rejected 关系。本文件没有复制 ERPNext 代码或真实记录。
