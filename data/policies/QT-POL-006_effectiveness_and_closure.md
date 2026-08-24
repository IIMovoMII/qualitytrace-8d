---
document_id: QT-POL-006
title: 8D 有效性验证与结案规则
version: "1.0"
effective_date: 2026-08-21
scope: QualityTrace 8D 合成来料规格偏差场景
authority_role: synthetic_internal_policy
not_real_company_policy: true
---

# 8D 有效性验证与结案规则

本文件是为个人 POC 原创编写的合成规则，不代表任何真实企业的 8D 结案标准。

## 有效性证据

- 本合成场景要求纠正后复检至少 5 件，且所有读数落在当前规格上下限内，`out_of_spec` 必须为 0。
- 复检记录必须绑定当前批次、规格版本、单位和检测设备。历史案例、供应商承诺或措施收据都不能替代复检结果。
- 复检合格只满足数据条件；仍需 `quality_manager` 写入 `accept_effectiveness` 决定后才能进入 `closed`。
- 复检不合格、样本不足、证据对象不一致或人工拒绝时，保持等待或转人工复盘，不把案件包装成关闭。

## 方法来源边界

结案步骤参考公开 8D 方法对措施验证、防复发和关闭的区分；“5 件且 0 件超差”是本 POC 为可重复测试设定的合成门槛，不是通用质量标准。
