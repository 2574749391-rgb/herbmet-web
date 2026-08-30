import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from literature import search_literature
from prompt import SYSTEM_PROMPT


HERB_PROFILES = {
    "黄芪": {
        "scientific_name": "Astragalus membranaceus",
        "constituents": ["Astragaloside IV", "Cycloastragenol", "Calycosin"],
    },
    "人参": {
        "scientific_name": "Panax ginseng",
        "constituents": ["Ginsenoside Rg1", "Ginsenoside Rb1", "Ginsenoside Rd"],
    },
    "丹参": {
        "scientific_name": "Salvia miltiorrhiza",
        "constituents": ["Tanshinone IIA", "Cryptotanshinone", "Salvianolic acid B"],
    },
    "甘草": {
        "scientific_name": "Glycyrrhiza uralensis",
        "constituents": ["Glycyrrhizin", "Glycyrrhetinic acid", "Liquiritigenin"],
    },
    "当归": {
        "scientific_name": "Angelica sinensis",
        "constituents": ["Ferulic acid", "Z-ligustilide", "Senkyunolide A"],
    },
    "黄连": {
        "scientific_name": "Coptis chinensis",
        "constituents": ["Berberine", "Coptisine", "Palmatine"],
    },
    "葛根": {
        "scientific_name": "Pueraria lobata",
        "constituents": ["Puerarin", "Daidzein", "Daidzin"],
    },
    "川芎": {
        "scientific_name": "Ligusticum chuanxiong",
        "constituents": ["Ferulic acid", "Z-ligustilide", "Senkyunolide A"],
    },
    "枸杞": {
        "scientific_name": "Lycium barbarum",
        "constituents": ["Betaine", "Zeaxanthin", "Scopoletin"],
    },
    "银杏": {
        "scientific_name": "Ginkgo biloba",
        "constituents": ["Ginkgolide A", "Ginkgolide B", "Bilobalide"],
    },
    "生姜": {
        "scientific_name": "Zingiber officinale",
        "constituents": ["6-Gingerol", "8-Gingerol", "10-Gingerol", "6-Shogaol"],
    },
    "艾叶": {
        "scientific_name": "Artemisia argyi",
        "constituents": ["Eupatilin", "Jaceosidin"],
    },
    "麻黄": {
        "scientific_name": "Ephedra sinica",
        "constituents": ["Ephedrine", "Pseudoephedrine", "Methylephedrine"],
    },
    "桂枝": {
        "scientific_name": "Cinnamomum cassia",
        "constituents": ["Cinnamaldehyde", "Cinnamic acid", "Coumarin"],
        "research_note": "桂枝为肉桂的嫩枝，不能把树皮或肉桂油研究无条件等同于桂枝。",
    },
    "紫苏": {
        "scientific_name": "Perilla frutescens",
        "constituents": ["Perillaldehyde", "Rosmarinic acid", "Luteolin"],
    },
    "石膏": {
        "scientific_name": "Gypsum Fibrosum",
        "constituents": ["Calcium sulfate dihydrate"],
        "research_note": "石膏是矿物药，不应套用植物次生代谢物框架；需单独说明钙、硫酸根处置及证据边界。",
    },
    "知母": {
        "scientific_name": "Anemarrhena asphodeloides",
        "constituents": ["Timosaponin BII", "Timosaponin AIII", "Mangiferin"],
    },
    "金银花": {
        "scientific_name": "Lonicera japonica",
        "constituents": ["Chlorogenic acid", "Loganin", "Luteolin"],
    },
    "连翘": {
        "scientific_name": "Forsythia suspensa",
        "constituents": ["Forsythiaside A", "Phillyrin", "Phillygenin"],
    },
    "党参": {
        "scientific_name": "Codonopsis pilosula",
        "constituents": ["Lobetyolin", "Tangshenoside I", "Atractylenolide III"],
    },
    "熟地黄": {
        "scientific_name": "Rehmannia glutinosa",
        "constituents": ["Catalpol", "Rehmannioside D", "Acteoside"],
        "research_note": "熟地黄是炮制品，炮制会改变成分谱；鲜地黄、生地黄证据不能直接等同于熟地黄。",
    },
}

HERB_ALIASES = {
    "枸杞子": "枸杞",
}


def load_herb_catalog():
    """从独立 JSON 文件加载药材目录，方便后续不改程序即可扩充。"""
    catalog_path = Path(__file__).with_name("herbs.json")
    with catalog_path.open("r", encoding="utf-8") as catalog_file:
        catalog = json.load(catalog_file)
    herbs = catalog.get("herbs", {})
    if not herbs:
        raise RuntimeError("药材目录 herbs.json 为空或格式不正确。")
    return herbs, catalog.get("aliases", {})


# 独立目录是唯一生效的数据源；上面的旧表仅用于旧版本代码回溯。
HERB_PROFILES, HERB_ALIASES = load_herb_catalog()


def resolve_herb(user_input):
    user_input = HERB_ALIASES.get(user_input, user_input)
    if user_input in HERB_PROFILES:
        return HERB_PROFILES[user_input]
    return {"scientific_name": user_input, "constituents": [], "research_note": ""}


def build_overview_query(scientific_name):
    return (
        f'TITLE:"{scientific_name}" AND '
        "(TITLE:review OR TITLE:phytochemistry) AND "
        "(TITLE_ABS:constituent* OR TITLE_ABS:phytochemistry "
        "OR TITLE_ABS:\"chemical composition\")"
    )


def build_adme_query(target):
    return (
        f'TITLE_ABS:"{target}" AND '
        "(TITLE_ABS:pharmacokinetic* OR TITLE_ABS:bioavailability "
        "OR TITLE_ABS:absorption OR TITLE_ABS:distribution "
        "OR TITLE_ABS:metabolite* OR TITLE_ABS:biotransformation "
        "OR TITLE_ABS:excretion OR TITLE_ABS:\"plasma concentration\")"
    )


def paper_key(paper):
    return paper.get("pmid") or paper.get("doi") or paper["title"].strip().lower()


def merge_papers(groups):
    """跨检索目标去重；重复命中时保留更高分，并记录全部命中目标。"""
    merged = {}
    for papers in groups:
        for paper in papers:
            key = paper_key(paper)
            if not key:
                continue
            if key not in merged:
                paper["matched_targets"] = [paper["research_target"]]
                merged[key] = paper
            else:
                existing = merged[key]
                if paper["research_target"] not in existing["matched_targets"]:
                    existing["matched_targets"].append(paper["research_target"])
                if paper["relevance_score"] > existing["relevance_score"]:
                    targets = existing["matched_targets"]
                    merged[key] = paper
                    merged[key]["matched_targets"] = targets
    return sorted(merged.values(), key=lambda p: p["relevance_score"], reverse=True)


def label_papers(papers, target, role):
    for paper in papers:
        paper["research_target"] = target
        paper["evidence_role"] = role
    return papers


def format_literature(papers):
    sections = []
    for index, paper in enumerate(papers, start=1):
        targets = "、".join(paper.get("matched_targets", [paper["research_target"]]))
        sections.append(f"""文献{index}
证据用途：{paper['evidence_role']}
研究目标：{targets}
证据类型：{paper['evidence_type']}
研究场景：{paper.get('study_context', '未标记')}
证据等级：{paper.get('evidence_grade', '未标记')}（仅表示研究场景层级，不代表论文质量）
规则初筛相关性：{paper['relevance_score']}/100
标题：{paper['title']}
作者：{paper['authors']}
年份：{paper['year']}
PMID：{paper['pmid'] or '无'}
DOI：{paper['doi'] or '无'}
摘要：
{paper['abstract']}""")
    return "\n\n".join(sections)


def terminology_warnings(text):
    """检查几类已知高风险错译；不擅自改写科研内容。"""
    compact = text.replace(" ", "")
    checks = (
        (("黄芪甲苷(Cycloastragenol", "黄芪甲苷（Cycloastragenol"),
         "Cycloastragenol 应译为“环黄芪醇”，不是“黄芪甲苷”。"),
        (("木犀草素-7-O-β-D-葡萄糖苷(Calycosin", "木犀草素-7-O-β-D-葡萄糖苷（Calycosin"),
         "Calycosin-7-O-glucoside 应译为“毛蕊异黄酮-7-O-葡萄糖苷”。"),
    )
    warnings = []
    for patterns, message in checks:
        if any(pattern in compact for pattern in patterns):
            warnings.append(message)
    return warnings


def collect_overview(profile, return_audit=False):
    """第一阶段：获取药材成分概览综述。"""
    scientific_name = profile["scientific_name"]
    candidates = label_papers(
        search_literature(build_overview_query(scientific_name),
                          search_name=scientific_name, max_results=5),
        scientific_name, "药材成分概览",
    )
    overview = [
        paper for paper in candidates
        if paper["evidence_type"] == "综述证据"
        and paper["relevance_score"] >= 20
    ][:2]
    included_keys = {paper_key(paper) for paper in overview}
    excluded = []
    for paper in candidates:
        if paper_key(paper) in included_keys:
            continue
        item = dict(paper)
        if paper["evidence_type"] != "综述证据":
            item["exclusion_reason"] = "不是成分概览综述"
        elif paper["relevance_score"] < 20:
            item["exclusion_reason"] = "相关性评分低于 20"
        else:
            item["exclusion_reason"] = "超过概览文献数量上限"
        excluded.append(item)
    return (overview, excluded) if return_audit else overview


def discover_constituents(profile, overview_papers, api_key, base_url, model):
    """从第一阶段摘要提取明确出现的候选成分，并与目录预设合并。"""
    preset = list(profile.get("constituents") or [])
    if not overview_papers:
        return preset
    evidence = "\n\n".join(
        f"标题：{paper['title']}\n摘要：{paper['abstract']}"
        for paper in overview_papers
    )
    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "你是药物化学文献筛选助手，只提取材料中明确出现的具体化合物英文名称，不推测。",
            },
            {
                "role": "user",
                "content": f"""从以下文献标题和摘要中提取最多 8 个适合继续检索药代动力学的代表性具体化合物。
不要返回多糖、黄酮、皂苷等大类名称，不要补充材料中未出现的化合物。
只返回 JSON，格式：{{"constituents": ["Compound A", "Compound B"]}}

{evidence}""",
            },
        ],
    )
    raw = response.choices[0].message.content or ""
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    extracted = []
    if match:
        try:
            parsed = json.loads(match.group(0))
            extracted = [str(item).strip() for item in parsed.get("constituents", []) if str(item).strip()]
        except (json.JSONDecodeError, TypeError):
            extracted = []
    merged = []
    for item in [*preset, *extracted]:
        if item.lower() not in {existing.lower() for existing in merged}:
            merged.append(item)
    return merged[:8]


def collect_adme(targets, return_audit=False):
    """第二阶段：围绕用户确认的候选成分检索直接 ADME 证据。"""

    adme_groups = []
    for target in targets:
        print(f"  正在检索成分/对象：{target}")
        papers = search_literature(build_adme_query(target), search_name=target,
                                   max_results=6)
        adme_groups.append(label_papers(papers, target, "ADME/生物转化"))

    candidates = merge_papers(adme_groups)
    eligible = [
        paper for paper in candidates
        if paper["relevance_score"] >= 40
        and paper["evidence_type"] in ("直接ADME证据", "生物转化证据")
    ]
    adme = eligible[:8]
    included_keys = {paper_key(paper) for paper in adme}
    excluded = []
    for paper in candidates:
        if paper_key(paper) in included_keys:
            continue
        item = dict(paper)
        if paper["relevance_score"] < 40:
            item["exclusion_reason"] = "相关性评分低于 40"
        elif paper["evidence_type"] not in ("直接ADME证据", "生物转化证据"):
            item["exclusion_reason"] = "缺少直接 ADME 或生物转化终点"
        else:
            item["exclusion_reason"] = "超过主证据数量上限"
        excluded.append(item)
    return (adme, excluded) if return_audit else adme


def collect_evidence(profile):
    """兼容命令行使用的一键两阶段检索。"""
    overview = collect_overview(profile)
    targets = profile["constituents"] or [profile["scientific_name"]]
    adme = collect_adme(targets)
    return overview, adme


def generate_report(
    herb,
    profile,
    overview_papers,
    adme_papers,
    api_key,
    base_url="https://maas.nscc-cs.cn/external/api/v1",
    model="Qwen3.5",
):
    """基于已经检索和筛选的证据调用模型生成报告。"""
    scientific_name = profile["scientific_name"]
    selected = [*overview_papers, *adme_papers]
    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"""请分析中药材：{herb}
学名：{scientific_name}
预设代表性成分：{'、'.join(profile['constituents']) or '未预设'}
对象特别说明：{profile.get('research_note') or '无'}

下面的证据已分为“药材成分概览”和“成分级 ADME/生物转化”：

{format_literature(selected)}

要求：
1. 成分概览文献只能支持“主要化学成分”，不能用于推断具体 ADME 参数。
2. 发酵产物必须单列为“体外/微生物转化产物”，不得称为人体内代谢物。
3. 药效通路不得写成药物代谢通路；CYP 相互作用不得写成该成分由 CYP 代谢。
4. 每个关键结论后直接写 PMID 或 DOI，不能只写 [1]、[2]。
5. 只允许使用本批材料中的标识符、数据和结论；无直接证据时写“当前检索文献证据不足”。
6. 明确区分药材整体证据、具体成分证据、体外证据、动物证据和人体证据。"""},
        ],
    )
    return response.choices[0].message.content


def answer_report_question(report, question, api_key, base_url, model):
    """只根据当前报告回答追问，避免把模型常识伪装成已检索证据。"""
    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": """你是 HerbMet 报告问答助手。只能依据用户提供的当前报告回答，不得补充报告外的论文、数据、PMID 或 DOI。报告没有答案时，必须明确说“当前报告证据不足，建议回查论文全文或重新检索”。使用中文，先给简短结论，再说明依据和不确定性。不提供诊断、处方或用药建议。"""},
            {"role": "user", "content": f"当前报告：\n\n{report}\n\n用户问题：{question}"},
        ],
    )
    return response.choices[0].message.content


def answer_general_question(question, history, api_key, base_url, model):
    """首页智能体对话；明确标识未经过实时文献检索。"""
    client = OpenAI(api_key=api_key, base_url=base_url)
    messages = [{"role": "system", "content": """你是 HerbMet 中药材代谢研究智能体。你可以解释中药材、化学成分、药代动力学、吸收、分布、代谢、排泄和文献研究方法。

当前是“快速问答模式”，没有执行实时文献检索。因此：
1. 不得声称回答已经检索数据库或核对论文全文。
2. 不得编造 PMID、DOI、论文、实验数值或确定性结论。
3. 涉及具体证据时，提醒用户使用“两阶段研究”功能检索并核查原文。
4. 不提供诊断、处方、剂量、配伍或个体化用药建议。
5. 使用中文，表达清楚、简洁；区分已知概念、合理推测和不确定信息。
6. 若用户要求临床决策，说明本平台仅用于科研与学习，并建议咨询合格专业人员。"""}]
    for item in history[-8:]:
        if item.get("role") in ("user", "assistant") and item.get("content"):
            messages.append({"role": item["role"], "content": item["content"]})
    messages.append({"role": "user", "content": question})
    response = client.chat.completions.create(model=model, messages=messages)
    return response.choices[0].message.content


def main():
    load_dotenv()
    api_key = os.getenv("CHANGSHA_API_KEY")
    if not api_key:
        print("未找到 CHANGSHA_API_KEY，请检查 .env 文件。")
        return

    herb = input("请输入中药材名称（中文或英文学名）：").strip()
    if not herb:
        print("名称不能为空，请重新运行后输入中药材名称。")
        return

    profile = resolve_herb(herb)
    scientific_name = profile["scientific_name"]
    print(f"正在进行两阶段检索：{herb}（{scientific_name}）")
    if profile["constituents"]:
        print("代表性成分：" + "、".join(profile["constituents"]))
    else:
        print("暂未配置代表性成分，将先检索药材整体证据。")

    try:
        overview_papers, adme_papers = collect_evidence(profile)
    except RuntimeError as error:
        print(error)
        return

    if not adme_papers:
        print("没有找到达到标准的直接 ADME 或生物转化文献。")
        return

    print(f"检索完成：成分概览 {len(overview_papers)} 篇，"
          f"直接 ADME/生物转化证据 {len(adme_papers)} 篇。")
    try:
        result_text = generate_report(
            herb, profile, overview_papers, adme_papers, api_key)
    except Exception as error:
        print(f"大模型调用暂时失败：{error}")
        return

    print("\n===== HerbMet Agent 两阶段文献分析结果 =====\n")
    print(result_text)
    warnings = terminology_warnings(result_text)
    if warnings:
        print("\n===== 术语检查警告 =====")
        for warning in warnings:
            print(f"- {warning}")


if __name__ == "__main__":
    main()
