---
document_id: QT-POL-004
title: 供应商纠正措施资料规则
version: "1.0"
effective_date: 2026-08-21
scope: QualityTrace 8D 合成来料规格偏差场景
authority_role: synthetic_internal_policy
not_real_company_policy: true
---

# 供应商纠正措施资料规则

本文件是为个人 POC 原创编写的合成规则，不代表任何真实企业的供应商协议。

## 回复与行动字段

- 本合成场景要求供应商在 48 小时内回复。该时限只用于演示截止日期和状态流转，不是行业统一要求。
- 回复至少说明关联批次、当前工装/规格版本、初步原因和后续资料计划；回复缺失时只催补资料，不由 Agent 代写供应商事实。
- 供应商的初步回复是待核验证据，不因措辞确定就自动升级为最终根因。
- 纠正措施必须包含标题、责任角色、截止天数、具体步骤、证据 ID 和版本号。本场景的措施截止期固定为 2 天。

## 方法来源边界

责任人、完成日期、问题和解决动作的字段关系参考 ERPNext `Quality Action Resolution`；具体时限和文本均为本项目原创合成规则。
