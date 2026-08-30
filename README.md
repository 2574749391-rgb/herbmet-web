# HerbMet

HerbMet 是一个面向科研与学习的中药材代谢文献分析助手。

当前版本：V1.8.1

它会进行两阶段文献检索，并围绕代表性成分整理吸收、分布、代谢和排泄（ADME）证据。公开体验版要求访问者使用自己的 OpenAI 兼容 API Key；Key 不写入项目文件或研究记录。

## Streamlit Community Cloud

- Main file path: `streamlit_app.py`
- Python dependencies: `requirements.txt`

登录账号通过 Streamlit Community Cloud 的 Secrets 配置，不写入 GitHub 仓库。
测试账号可由服务端 Secrets 提供平台模型配置；普通用户模式保留自带 API Key 的设计。
Supabase 提供邮箱注册、用户隔离的云端历史记录；加密会话 Cookie 用于刷新后保持登录。

药材资料独立保存在 `herbs.json`，当前预设 50 种常用药材。网页支持按功效分类快速选择，也保留中文名、英文学名自由输入；后续扩充药材时只需更新该目录文件。

本工具不用于临床诊疗，关键结论请回查 PMID、DOI 与论文全文。

V1.8 在报告结果中增加证据结构概览，分别统计人体、动物、体外/菌群及综述/未明确研究，并支持下载可用 Excel 打开的入选文献 CSV 清单。

V1.8.1 增加第一阶段检索摘要：展示入选、未纳入文献和候选成分数量，可在进入第二阶段前核查文献，并支持一键重新开始分析。
