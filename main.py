import os

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


def collect_evidence(profile):
    scientific_name = profile["scientific_name"]
    overview = label_papers(
        search_literature(build_overview_query(scientific_name),
                          search_name=scientific_name, max_results=5),
        scientific_name, "药材成分概览",
    )
    overview = [
        paper for paper in overview
        if paper["evidence_type"] == "综述证据"
        and paper["relevance_score"] >= 20
    ][:2]

    adme_groups = []
    # 已配置代表性成分时，只把成分级论文送入 ADME 主证据池；
    # 药材整体论文仅用于成分背景，避免再次混入宽泛药效研究。
    targets = profile["constituents"] or [scientific_name]
    for target in targets:
        print(f"  正在检索成分/对象：{target}")
        papers = search_literature(build_adme_query(target), search_name=target,
                                   max_results=6)
        adme_groups.append(label_papers(papers, target, "ADME/生物转化"))

    adme = [
        paper for paper in merge_papers(adme_groups)
        if paper["relevance_score"] >= 40
        and paper["evidence_type"] in ("直接ADME证据", "生物转化证据")
    ][:8]
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
