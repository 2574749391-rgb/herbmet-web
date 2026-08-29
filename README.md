# HerbMet

HerbMet 是一个面向科研与学习的中药材代谢文献分析助手。

当前版本：V0.5.4

它会进行两阶段文献检索，并围绕代表性成分整理吸收、分布、代谢和排泄（ADME）证据。公开体验版要求访问者使用自己的 OpenAI 兼容 API Key；Key 不写入项目文件或研究记录。

## Streamlit Community Cloud

- Main file path: `streamlit_app.py`
- Python dependencies: `requirements.txt`

登录账号通过 Streamlit Community Cloud 的 Secrets 配置，不写入 GitHub 仓库。
测试账号可由服务端 Secrets 提供平台模型配置；普通用户模式保留自带 API Key 的设计。
Supabase 提供邮箱注册、用户隔离的云端历史记录；加密会话 Cookie 用于刷新后保持登录。

本工具不用于临床诊疗，关键结论请回查 PMID、DOI 与论文全文。
