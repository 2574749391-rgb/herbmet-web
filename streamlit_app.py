import streamlit as st

from main import collect_evidence, generate_report, resolve_herb, terminology_warnings


st.set_page_config(
    page_title="HerbMet · 中药材代谢研究助手",
    page_icon="🌿",
    layout="wide",
)


def display_papers(papers):
    for index, paper in enumerate(papers, start=1):
        st.markdown(f"**{index}. {paper['title']}**")
        st.caption(
            f"目标：{paper.get('research_target', '未知')} ｜ "
            f"{paper['evidence_type']} ｜ 相关性：{paper['relevance_score']}/100"
        )
        identifiers = []
        if paper.get("pmid"):
            identifiers.append(
                f"[PMID {paper['pmid']}](https://pubmed.ncbi.nlm.nih.gov/{paper['pmid']}/)"
            )
        if paper.get("doi"):
            identifiers.append(f"DOI: {paper['doi']}")
        st.markdown(" ｜ ".join(identifiers) or "无 PMID/DOI")
        st.divider()


st.title("🌿 HerbMet")
st.subheader("中药材代谢研究助手")
st.caption("检索真实文献，按成分整理吸收、分布、代谢与排泄证据。")
st.info("公开体验版：请使用您自己的模型 API Key。Key 仅用于本次会话，不写入项目文件或研究记录。")

with st.sidebar:
    st.header("模型设置")
    provider = st.selectbox("服务商", ("阿里云百炼", "OpenAI 兼容接口（自定义）"))
    base_url = st.text_input(
        "Base URL",
        value=(
            "https://dashscope.aliyuncs.com/compatible-mode/v1"
            if provider == "阿里云百炼"
            else ""
        ),
    )
    model = st.text_input(
        "模型名称", value="qwen-plus" if provider == "阿里云百炼" else ""
    )
    api_key = st.text_input(
        "API Key", type="password", placeholder="仅用于当前浏览器会话"
    )
    st.caption("请勿使用他人的 API Key。关闭或刷新页面后需要重新填写。")

with st.form("analysis_form"):
    herb = st.text_input(
        "中药材名称",
        placeholder="例如：黄芪",
        help="当前优先支持：黄芪、人参、丹参、甘草、当归，也可以输入英文学名。",
    )
    submitted = st.form_submit_button("开始分析", type="primary")

if submitted:
    herb = herb.strip()
    api_key = api_key.strip()
    base_url = base_url.strip()
    model = model.strip()

    if not herb:
        st.warning("请输入中药材名称。")
        st.stop()
    if not api_key or not base_url or not model:
        st.error("API Key、Base URL 和模型名称都必须填写。")
        st.stop()

    profile = resolve_herb(herb)
    scientific_name = profile["scientific_name"]
    st.info(f"检索对象：{herb}（{scientific_name}）")
    if profile["constituents"]:
        st.write("代表性成分：", "、".join(profile["constituents"]))

    try:
        with st.status("正在进行两阶段文献检索…", expanded=True) as status:
            st.write("检索药材成分概览")
            st.write("检索代表性成分的 ADME 与生物转化证据")
            overview_papers, adme_papers = collect_evidence(profile)
            status.update(label="文献检索与初筛完成", state="complete")
    except RuntimeError as error:
        st.error(str(error))
        st.stop()

    if not adme_papers:
        st.warning("没有找到达到标准的直接 ADME 或生物转化文献。")
        st.stop()

    col1, col2 = st.columns(2)
    col1.metric("成分概览文献", len(overview_papers))
    col2.metric("ADME / 生物转化证据", len(adme_papers))

    try:
        with st.spinner("正在基于入选证据生成结构化报告…"):
            report = generate_report(
                herb,
                profile,
                overview_papers,
                adme_papers,
                api_key,
                base_url=base_url,
                model=model,
            )
    except Exception as error:
        st.error(f"大模型调用暂时失败：{error}")
        st.stop()

    st.success("分析完成。")
    with st.expander("查看入选文献与相关性", expanded=False):
        display_papers([*overview_papers, *adme_papers])
    st.header("文献分析报告")
    st.markdown(report)
    warnings = terminology_warnings(report)
    if warnings:
        st.warning("术语检查发现潜在冲突：\n\n- " + "\n- ".join(warnings))
    st.download_button(
        "下载 Markdown 报告",
        data=report,
        file_name=f"HerbMet-{herb}-report.md",
        mime="text/markdown",
    )

st.divider()
st.caption("仅用于科研与学习辅助，不用于临床诊疗。关键结论请回查 PMID、DOI 与论文全文。")
