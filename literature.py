import time
from xml.etree import ElementTree

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


EUROPE_PMC_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
PUBMED_FETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
RELEVANCE_CONCEPTS = (
    (("pharmacokinetic", "pharmacokinetics"), 18, "pharmacokinetics"),
    (("metabolite", "metabolites"), 12, "metabolite"),
    (("absorption",), 12, "absorption"),
    (("distribution",), 10, "distribution"),
    (("metabolism",), 10, "metabolism"),
    (("biotransformation",), 16, "biotransformation"),
    (("excretion",), 12, "excretion"),
    (("bioavailability",), 12, "bioavailability"),
    (("cyp",), 8, "CYP"), (("ugt",), 8, "UGT"),
    (("plasma",), 5, "plasma"), (("urine",), 5, "urine"),
)

DIRECT_ADME_TERMS = (
    "pharmacokinetic", "bioavailability", "cmax", "tmax", "half-life",
    "half life", "area under the curve", "plasma concentration",
    "tissue distribution", "urinary excretion", "biliary excretion",
    "oral administration", "intravenous administration",
)
BIOTRANSFORMATION_TERMS = (
    "biotransformation", "microbial transformation", "fermentation",
    "metabolite identification", "metabolite profiling",
)
INDIRECT_CONTEXT_TERMS = (
    "broiler", "chicken", "feed additive", "stems and leaves",
    "serum metabolome", "anti-aging", "anticancer", "hyperuricemia",
    "antioxidant", "immune status", "fecal fermentation",
)


def classify_study_context(paper):
    """按标题、摘要和出版类型给出透明的研究场景标签，不替代人工质量评价。"""
    text = f"{paper['title']} {paper['abstract']} {' '.join(paper.get('publication_types', []))}".lower()
    if "review" in text or "meta-analysis" in text:
        return "综述证据", "D"
    if any(term in text for term in ("healthy volunteer", "human pharmacokinetic", "clinical trial", "patients", "subjects")):
        return "人体研究", "A"
    if any(term in text for term in ("rat", "rats", "mouse", "mice", "rabbit", "dog", "beagle", "zebrafish")):
        return "动物体内研究", "B"
    if any(term in text for term in ("gut microbiota", "intestinal bacteria", "microbial transformation", "fecal fermentation")):
        return "肠道菌群/微生物转化", "C"
    if any(term in text for term in ("in vitro", "caco-2", "microsome", "hepatocyte", "cell culture")):
        return "体外研究", "C"
    return "研究场景未明确", "D"


def create_session():
    """创建带自动重试的网络会话。"""
    retry = Retry(total=3, backoff_factor=0.8,
                  status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=("GET",))
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": "HerbMet/0.2 (research prototype)"})
    return session


def get_abstract(pmid, session=None):
    """根据 PMID 从 PubMed 获取摘要；失败时返回可识别状态。"""
    if not pmid:
        return "暂无摘要"
    session = session or create_session()
    try:
        response = session.get(
            PUBMED_FETCH_URL,
            params={"db": "pubmed", "id": pmid, "rettype": "abstract", "retmode": "xml"},
            timeout=20,
        )
        response.raise_for_status()
        root = ElementTree.fromstring(response.content)
        parts = []
        for abstract in root.findall(".//AbstractText"):
            text = "".join(abstract.itertext()).strip()
            label = abstract.attrib.get("Label")
            if text:
                parts.append(f"{label}: {text}" if label else text)
        return "\n".join(parts) if parts else "暂无摘要"
    except (requests.RequestException, ElementTree.ParseError):
        return "摘要获取失败"


def score_relevance(paper, search_name):
    """使用透明的关键词规则给论文计算 0—100 的初筛分数。"""
    combined = f"{paper['title']} {paper['abstract']}".lower()
    score, reasons = 0, []
    if search_name.lower() in combined:
        score += 25
        reasons.append("包含检索目标")
    for terms, weight, label in RELEVANCE_CONCEPTS:
        if any(term in combined for term in terms):
            score += weight
            reasons.append(label)
    if paper["abstract"] not in ("暂无摘要", "摘要获取失败"):
        score += 10
        reasons.append("有摘要")

    direct_hits = [term for term in DIRECT_ADME_TERMS if term in combined]
    transformation_hits = [term for term in BIOTRANSFORMATION_TERMS if term in combined]
    indirect_hits = [term for term in INDIRECT_CONTEXT_TERMS if term in combined]
    publication_types = " ".join(paper.get("publication_types", [])).lower()
    is_review = "review" in publication_types or "review" in paper["title"].lower()
    if is_review:
        evidence_type = "综述证据"
        score -= 15
        reasons.append("综述而非直接实验")
    elif direct_hits:
        evidence_type = "直接ADME证据"
        score += 20
        reasons.append("直接ADME指标")
    elif transformation_hits:
        evidence_type = "生物转化证据"
        reasons.append("生物转化研究")
    else:
        evidence_type = "间接证据"

    if indirect_hits and not direct_hits:
        score -= min(30, 10 * len(indirect_hits))
        reasons.append("研究对象或终点偏离ADME")

    return max(0, min(score, 100)), reasons[:7], evidence_type


def _deduplicate(papers):
    unique, seen = [], set()
    for paper in papers:
        key = paper.get("pmid") or paper.get("doi") or paper["title"].strip().lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(paper)
    return unique


def search_literature(query, search_name, max_results=10):
    """检索、补充摘要、去重并按相关性排序。"""
    session = create_session()
    try:
        response = session.get(
            EUROPE_PMC_URL,
            params={"query": query, "format": "json", "pageSize": max_results,
                    "resultType": "core"},
            timeout=20,
        )
        response.raise_for_status()
        items = response.json().get("resultList", {}).get("result", [])
    except (requests.RequestException, ValueError) as error:
        raise RuntimeError(f"文献检索暂时失败：{error}") from error

    papers = []
    for index, item in enumerate(items):
        pmid = item.get("pmid")
        abstract = item.get("abstractText") or get_abstract(pmid, session)
        paper = {
            "title": item.get("title", "无标题"),
            "authors": item.get("authorString", "未知"),
            "year": item.get("pubYear", "未知"),
            "pmid": pmid or "", "doi": item.get("doi", ""),
            "abstract": abstract,
            "publication_types": item.get("pubTypeList", {}).get("pubType", []),
        }
        (paper["relevance_score"], paper["relevance_reasons"],
         paper["evidence_type"]) = score_relevance(paper, search_name)
        paper["study_context"], paper["evidence_grade"] = classify_study_context(paper)
        papers.append(paper)
        if pmid and not item.get("abstractText") and index < len(items) - 1:
            time.sleep(0.12)

    return sorted(_deduplicate(papers),
                  key=lambda paper: paper["relevance_score"], reverse=True)


if __name__ == "__main__":
    results = search_literature(
        '"Astragalus membranaceus" AND '
        "(pharmacokinetics OR biotransformation OR metabolites OR absorption OR excretion)",
        search_name="Astragalus membranaceus", max_results=5)
    for i, paper in enumerate(results, start=1):
        print(f"\n===== 文献 {i}｜相关性 {paper['relevance_score']} =====")
        print("标题：", paper["title"])
        print("PMID：", paper["pmid"] or "无")
        print("DOI：", paper["doi"] or "无")
        print("证据类型：", paper["evidence_type"])
        print("评分依据：", "、".join(paper["relevance_reasons"]) or "未命中关键词")
