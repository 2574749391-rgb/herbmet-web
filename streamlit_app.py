import base64
import csv
import hashlib
import hmac
import io
import json
import re
import time
from collections import Counter

import streamlit as st
from cryptography.fernet import Fernet, InvalidToken
from openai import APIConnectionError, APITimeoutError, AuthenticationError, BadRequestError, RateLimitError
from streamlit_cookies_controller import CookieController
from supabase import create_client

from main import (
    HERB_PROFILES,
    answer_report_question,
    collect_adme,
    collect_overview,
    discover_constituents,
    generate_report,
    resolve_herb,
    terminology_warnings,
)


COMPOUND_CHINESE_NAMES = {
    "1-Deoxynojirimycin": "1-脱氧野尻霉素",
    "6-Gingerol": "6-姜酚",
    "8-Gingerol": "8-姜酚",
    "10-Gingerol": "10-姜酚",
    "6-Shogaol": "6-姜烯酚",
    "Aconitine": "乌头碱",
    "Mesaconitine": "新乌头碱",
    "Hypaconitine": "次乌头碱",
    "Acteoside": "毛蕊花糖苷（麦角甾苷）",
    "Allantoin": "尿囊素",
    "Aloe-emodin": "芦荟大黄素",
    "Amygdalin": "苦杏仁苷",
    "Apigenin": "芹菜素",
    "Astragaloside IV": "黄芪甲苷 IV（黄芪皂苷 IV）",
    "Atractylenolide I": "白术内酯 I",
    "Atractylenolide II": "白术内酯 II",
    "Atractylenolide III": "白术内酯 III",
    "Baicalein": "黄芩素",
    "Baicalin": "黄芩苷",
    "Benzaldehyde": "苯甲醛",
    "Berberine": "小檗碱（黄连素）",
    "Beta-eudesmol": "β-桉叶醇",
    "Betaine": "甜菜碱",
    "Bilobalide": "白果内酯",
    "Calcium sulfate dihydrate": "二水硫酸钙",
    "Calycosin": "毛蕊异黄酮",
    "Catalpol": "梓醇",
    "Chlorogenic acid": "绿原酸",
    "Cinnamaldehyde": "肉桂醛",
    "Cinnamic acid": "肉桂酸",
    "Coptisine": "黄连碱",
    "Coumarin": "香豆素",
    "Crocin": "西红花苷（藏红花素）",
    "Cryptotanshinone": "隐丹参酮",
    "Cycloastragenol": "环黄芪醇",
    "Daidzein": "大豆苷元",
    "Daidzin": "大豆苷",
    "Diosgenin": "薯蓣皂苷元",
    "Emodin": "大黄素",
    "Ephedrine": "麻黄碱",
    "Epigoitrin": "表告依春",
    "Epimedin C": "朝藿定 C",
    "Ferulic acid": "阿魏酸",
    "Forsythiaside A": "连翘酯苷 A",
    "Genipin": "京尼平",
    "Geniposide": "栀子苷",
    "Ginkgolide A": "银杏内酯 A",
    "Ginkgolide B": "银杏内酯 B",
    "Ginsenoside Rb1": "人参皂苷 Rb1",
    "Ginsenoside Rd": "人参皂苷 Rd",
    "Ginsenoside Rg1": "人参皂苷 Rg1",
    "Glycyrrhetinic acid": "甘草次酸",
    "Glycyrrhizin": "甘草酸（甘草甜素）",
    "Hesperidin": "橙皮苷",
    "Hydroxysafflor yellow A": "羟基红花黄色素 A",
    "Icariin": "淫羊藿苷",
    "Icaritin": "淫羊藿素",
    "Imperatorin": "欧前胡素",
    "Indigo": "靛蓝",
    "Indirubin": "靛玉红",
    "Isoimperatorin": "异欧前胡素",
    "Jujuboside A": "酸枣仁皂苷 A",
    "Kaempferol": "山柰酚",
    "Liquiritigenin": "甘草素",
    "Loganin": "马钱苷",
    "Luteolin": "木犀草素",
    "Mangiferin": "芒果苷",
    "Menthol": "薄荷醇（薄荷脑）",
    "Menthone": "薄荷酮",
    "Methylephedrine": "甲基麻黄碱",
    "Naringin": "柚皮苷",
    "Neohesperidin": "新橙皮苷",
    "Nobiletin": "川陈皮素",
    "Notoginsenoside R1": "三七皂苷 R1",
    "Oleic acid": "油酸",
    "Pachymic acid": "茯苓酸",
    "Palmatine": "巴马汀（掌叶防己碱）",
    "Perillaldehyde": "紫苏醛",
    "Phillygenin": "连翘脂素",
    "Phillyrin": "连翘苷",
    "Pseudoephedrine": "伪麻黄碱",
    "Puerarin": "葛根素",
    "Quercetin": "槲皮素",
    "Rhein": "大黄酸",
    "Rosmarinic acid": "迷迭香酸",
    "Rutin": "芦丁",
    "Saikosaponin A": "柴胡皂苷 A",
    "Saikosaponin C": "柴胡皂苷 C",
    "Saikosaponin D": "柴胡皂苷 D",
    "Salvianolic acid B": "丹酚酸 B",
    "Scopoletin": "东莨菪内酯",
    "Senkyunolide A": "洋川芎内酯 A",
    "Spinosin": "斯皮诺素（棘苷）",
    "Synephrine": "辛弗林（对羟福林）",
    "Tangeretin": "橘皮素",
    "Tanshinone IIA": "丹参酮 IIA",
    "Timosaponin AIII": "知母皂苷 AIII",
    "Timosaponin BII": "知母皂苷 BII",
    "Wogonin": "汉黄芩素",
    "Z-ligustilide": "Z-藁本内酯",
    "Zeaxanthin": "玉米黄质",
    "Zingerone": "姜酮（姜油酮）",
}


def compound_display_name(name):
    chinese_name = COMPOUND_CHINESE_NAMES.get(name, "暂无常用中文名")
    return f"{name}（{chinese_name}）"


st.set_page_config(page_title="HerbMet · 中药材代谢研究助手", page_icon="🌿", layout="wide")

st.markdown(
    """
    <style>
    html, body, [class*="css"] { font-family: "Songti SC", "STSong", "Noto Serif SC", serif; }
    .stApp {
        background-color: #f7f1e6;
        background-image:
            radial-gradient(circle at 12% 8%, rgba(139,101,66,.08), transparent 25%),
            linear-gradient(rgba(116,82,52,.025) 1px, transparent 1px);
        background-size: auto, 100% 28px;
        color: #3d2b1f;
    }
    .block-container { max-width: 1240px; padding-top: 2.2rem; padding-bottom: 3rem; }
    .herbmet-hero {
        padding: 1.8rem 2rem; margin-bottom: 1.1rem; border-radius: 14px;
        border: 1px solid #d7c3a7; border-left: 6px solid #7a4e34;
        background: linear-gradient(120deg, #fffaf1, #eadcc7);
        box-shadow: 0 10px 28px rgba(83,57,35,.10);
    }
    .herbmet-eyebrow { color: #8a5a3b; font-size: .8rem; letter-spacing: .16em; font-weight: 800; }
    .herbmet-title { font-size: 2.25rem; line-height: 1.15; font-weight: 800; margin: .4rem 0 .6rem; color: #38251a; }
    .herbmet-subtitle { color: #776554; font-size: 1rem; margin: 0; }
    .catalog-card {
        border: 1px solid #ddcdb7; border-radius: 12px;
        padding: 1rem 1.15rem; background: rgba(255,251,244,.82); margin: .5rem 0 1rem;
    }
    div[data-testid="stForm"] { border-radius: 12px; border-color: #ddcdb7; background: rgba(255,251,244,.72); }
    div[data-testid="stMetric"] { background: rgba(255,250,242,.92); border: 1px solid #dfcfb9; padding: .8rem 1rem; border-radius: 12px; box-shadow: 0 4px 14px rgba(83,57,35,.05); }
    .stButton > button, .stFormSubmitButton > button { border-radius: 8px; font-weight: 700; }
    div[data-testid="stSidebar"] { border-right: 1px solid #d8c5aa; }
    div[data-testid="stExpander"] { border-color: #ddcdb7; background: rgba(255,251,244,.55); }
    hr { border-color: #d8c7b0 !important; }
    .workflow-step {
        min-height: 112px; padding: 1rem 1.05rem; border-radius: 11px;
        background: #fffaf2; border: 1px solid #dfcfb9;
    }
    .workflow-number { color: #8a5a3b; font-size: .78rem; font-weight: 800; letter-spacing: .08em; }
    .workflow-title { color: #3d2b1f; font-size: 1.02rem; font-weight: 750; margin: .28rem 0; }
    .workflow-copy { color: #7d6b5b; font-size: .86rem; line-height: 1.45; }
    @media (max-width: 760px) {
        .block-container { padding: 1rem .8rem 2rem; }
        .herbmet-hero { padding: 1.25rem 1.15rem; border-radius: 12px; }
        .herbmet-title { font-size: 1.65rem; }
        .herbmet-subtitle { font-size: .9rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

COOKIE_NAME = "herbmet_session_v1"
COOKIE_MAX_AGE = 30 * 24 * 60 * 60
cookies = CookieController(key="herbmet-cookies")

CATEGORY_FALLBACK = {
    "解表药": ("麻黄", "桂枝", "紫苏", "生姜", "葛根"),
    "清热药": ("石膏", "知母", "金银花", "连翘", "黄连"),
    "补气药": ("人参", "黄芪", "党参", "甘草"),
    "补血药": ("当归", "熟地黄"),
    "补阴药": ("枸杞",),
    "活血化瘀药": ("丹参", "川芎"),
    "温经止血药": ("艾叶",),
    "其他常用药": ("银杏",),
}


def herb_category(name, profile):
    category = profile.get("category")
    if category:
        return category
    return next((group for group, names in CATEGORY_FALLBACK.items() if name in names), "其他")


def supabase_client():
    return create_client(str(st.secrets["supabase"]["url"]), str(st.secrets["supabase"]["key"]))


def session_cipher():
    source = str(st.secrets["platform_api"]["api_key"]) + "|" + str(st.secrets["supabase"]["key"])
    key = base64.urlsafe_b64encode(hashlib.sha256(source.encode("utf-8")).digest())
    return Fernet(key)


def save_login_cookie(session, account_type):
    payload = {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "account_type": account_type,
    }
    encrypted = session_cipher().encrypt(json.dumps(payload).encode("utf-8")).decode("ascii")
    cookies.set(
        COOKIE_NAME,
        encrypted,
        max_age=COOKIE_MAX_AGE,
        secure=True,
        same_site="lax",
    )
    # 给浏览器组件时间写入 Cookie，避免立即 rerun 中断写入。
    time.sleep(1)


def establish_login(client, response, account_type):
    if not response.user or not response.session:
        return False
    st.session_state["authenticated"] = True
    st.session_state["user_id"] = str(response.user.id)
    st.session_state["username"] = response.user.email or "用户"
    st.session_state["account_type"] = account_type
    st.session_state["sb_client"] = client
    save_login_cookie(response.session, account_type)
    return True


def restore_login():
    if st.session_state.get("authenticated"):
        return
    encrypted = cookies.get(COOKIE_NAME)
    if encrypted is None:
        # 组件首次加载时可能先返回空值，短暂等待后再次读取。
        time.sleep(0.8)
        encrypted = cookies.get(COOKIE_NAME)
    if not encrypted:
        return
    try:
        payload = json.loads(session_cipher().decrypt(encrypted.encode("ascii")).decode("utf-8"))
        client = supabase_client()
        response = client.auth.set_session(payload["access_token"], payload["refresh_token"])
        establish_login(client, response, payload.get("account_type", "byok"))
    except (InvalidToken, KeyError, ValueError, TypeError):
        cookies.remove(COOKIE_NAME)
    except Exception:
        cookies.remove(COOKIE_NAME)


def sign_out():
    client = st.session_state.get("sb_client")
    if client:
        try:
            client.auth.sign_out()
        except Exception:
            pass
    cookies.remove(COOKIE_NAME)
    st.session_state.clear()
    st.rerun()


def test_account_login(username, password):
    expected_username = str(st.secrets["auth"]["username"])
    expected_password = str(st.secrets["auth"]["password"])
    if not (hmac.compare_digest(username.strip(), expected_username) and hmac.compare_digest(password, expected_password)):
        st.error("账号或密码不正确。")
        return
    client = supabase_client()
    test_email = f"{expected_username}@herbmet.local"
    try:
        response = client.auth.sign_in_with_password({"email": test_email, "password": expected_password})
    except Exception:
        try:
            response = client.auth.sign_up({
                "email": test_email,
                "password": expected_password,
                "options": {"data": {"display_name": expected_username}},
            })
        except Exception as error:
            st.error(f"账号初始化失败：{error}")
            return
    if establish_login(client, response, "platform"):
        st.rerun()
    st.error("账号登录失败，请联系管理员检查账户配置。")


def email_login(email, password):
    if not valid_email(email):
        st.error("邮箱格式不正确，请输入类似 name@example.com 的完整邮箱地址。")
        return
    try:
        client = supabase_client()
        response = client.auth.sign_in_with_password({"email": email.strip(), "password": password})
        if establish_login(client, response, "byok"):
            st.rerun()
    except Exception:
        st.error("邮箱或密码不正确，或者邮箱尚未完成确认。")


def email_register(display_name, email, password, password_again):
    if not display_name.strip():
        st.error("请输入显示名称。")
        return
    if not valid_email(email):
        st.error("邮箱格式不正确，请输入类似 name@example.com 的完整邮箱地址。")
        return
    if len(password) < 8:
        st.error("密码至少需要 8 位。")
        return
    if password != password_again:
        st.error("两次输入的密码不一致。")
        return
    try:
        client = supabase_client()
        response = client.auth.sign_up({
            "email": email.strip(),
            "password": password,
            "options": {"data": {"display_name": display_name.strip()}},
        })
        if response.session and establish_login(client, response, "byok"):
            st.rerun()
        st.success("注册成功。请前往邮箱完成确认后再登录。")
    except Exception as error:
        st.error(f"注册失败：{friendly_auth_error(error)}")


def valid_email(email):
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()))


def friendly_auth_error(error):
    message = str(error).lower()
    if "invalid format" in message or "validate email" in message:
        return "邮箱格式不正确。"
    if "already registered" in message or "already exists" in message:
        return "该邮箱已经注册，请直接登录。"
    if "password" in message and ("weak" in message or "characters" in message):
        return "密码不符合要求，请使用至少 8 位密码。"
    if "rate limit" in message or "too many" in message:
        return "操作过于频繁，请稍后再试。"
    if "signup" in message and "disabled" in message:
        return "当前暂未开放新用户注册。"
    return "暂时无法完成注册，请稍后重试。"


def login_gate():
    restore_login()
    if st.session_state.get("authenticated"):
        with st.sidebar:
            st.success(f"已登录：{st.session_state.get('username', '用户')}")
            if st.button("退出登录", use_container_width=True):
                sign_out()
        return
    st.markdown(
        """
        <section class="herbmet-hero">
          <div class="herbmet-eyebrow">HERBMET · 本草循证研究</div>
          <div class="herbmet-title">🌿 中药材代谢研究助手</div>
          <p class="herbmet-subtitle">登录后检索文献、生成报告，并在不同设备查看个人研究记录。</p>
        </section>
        """,
        unsafe_allow_html=True,
    )
    login_tab, register_tab, reset_tab = st.tabs(("账号登录", "注册账号", "忘记密码"))
    with login_tab:
        with st.form("account_login_form"):
            identifier = st.text_input("账号或邮箱")
            password = st.text_input("密码", type="password", key="account_password")
            submitted = st.form_submit_button("登录", type="primary")
        if submitted:
            expected_username = str(st.secrets["auth"]["username"])
            if hmac.compare_digest(identifier.strip(), expected_username):
                test_account_login(identifier, password)
            else:
                email_login(identifier, password)
    with register_tab:
        with st.form("register_form"):
            display_name = st.text_input("显示名称")
            email = st.text_input("邮箱", key="register_email")
            password = st.text_input("密码（至少 8 位）", type="password", key="register_password")
            password_again = st.text_input("再次输入密码", type="password")
            submitted = st.form_submit_button("注册", type="primary")
        if submitted:
            email_register(display_name, email, password, password_again)
    with reset_tab:
        st.caption("普通邮箱账号可通过一次性验证码重置密码；平台测试账号请联系站点管理员。")
        with st.form("send_reset_code_form"):
            reset_email = st.text_input("注册邮箱", key="password_reset_email")
            send_code_submitted = st.form_submit_button("发送验证码")
        if send_code_submitted:
            send_password_reset_code(reset_email)
        if st.session_state.get("reset_email"):
            st.info(f"验证码已请求发送至：{st.session_state['reset_email']}")
            with st.form("verify_reset_code_form"):
                reset_code = st.text_input("邮箱验证码", placeholder="输入邮件中的验证码")
                reset_new_password = st.text_input("新密码（至少 8 位）", type="password", key="reset_new_password")
                reset_new_password_again = st.text_input("再次输入新密码", type="password", key="reset_new_password_again")
                reset_submitted = st.form_submit_button("验证并重置密码", type="primary")
            if reset_submitted:
                reset_password_with_code(reset_code, reset_new_password, reset_new_password_again)
    st.caption("登录信息会以加密会话保存，刷新页面后仍可保持登录。")
    st.stop()


def display_papers(papers):
    for index, paper in enumerate(papers, start=1):
        st.markdown(f"**{index}. {paper['title']}**")
        st.caption(
            f"目标：{paper.get('research_target', '未知')} ｜ {paper['evidence_type']} ｜ "
            f"{paper.get('study_context', '研究场景未明确')} ｜ 等级 {paper.get('evidence_grade', 'D')} ｜ "
            f"相关性：{paper['relevance_score']}/100"
        )
        identifiers = []
        if paper.get("pmid"):
            identifiers.append(f"[PMID {paper['pmid']}](https://pubmed.ncbi.nlm.nih.gov/{paper['pmid']}/)")
        if paper.get("doi"):
            identifiers.append(f"DOI: {paper['doi']}")
        st.markdown(" ｜ ".join(identifiers) or "无 PMID/DOI")
        st.divider()


def display_screening_audit(excluded_papers, title="查看未纳入文献与原因"):
    if not excluded_papers:
        return
    with st.expander(f"{title}（{len(excluded_papers)} 篇）", expanded=False):
        st.caption("排除仅针对本次快速报告，不代表论文没有科研价值。")
        for index, paper in enumerate(excluded_papers, start=1):
            st.markdown(f"**{index}. {paper['title']}**")
            st.caption(
                f"排除原因：{paper.get('exclusion_reason', '未达到筛选标准')} ｜ "
                f"相关性：{paper.get('relevance_score', 0)}/100 ｜ "
                f"{paper.get('study_context', '研究场景未明确')}"
            )


def papers_to_csv(papers):
    """把入选文献整理为便于 Excel 打开的 UTF-8 CSV。"""
    output = io.StringIO()
    fields = ("研究目标", "标题", "作者", "年份", "研究场景", "证据等级", "证据类型", "相关性", "PMID", "DOI")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for paper in papers:
        writer.writerow({
            "研究目标": paper.get("research_target", ""),
            "标题": paper.get("title", ""),
            "作者": paper.get("authors", ""),
            "年份": paper.get("year", ""),
            "研究场景": paper.get("study_context", "研究场景未明确"),
            "证据等级": paper.get("evidence_grade", "D"),
            "证据类型": paper.get("evidence_type", ""),
            "相关性": paper.get("relevance_score", 0),
            "PMID": paper.get("pmid", ""),
            "DOI": paper.get("doi", ""),
        })
    return "\ufeff" + output.getvalue()


def display_evidence_overview(papers, herb, download_key):
    contexts = Counter(paper.get("study_context", "研究场景未明确") for paper in papers)
    human = contexts["人体研究"]
    animal = contexts["动物体内研究"]
    laboratory = contexts["体外研究"] + contexts["肠道菌群/微生物转化"]
    other = len(papers) - human - animal - laboratory
    st.subheader("证据结构概览")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("人体研究", human)
    c2.metric("动物体内", animal)
    c3.metric("体外 / 菌群", laboratory)
    c4.metric("综述 / 未明确", other)
    st.caption("A–D 仅表示研究场景层级，不能替代对论文质量、偏倚风险和全文的人工评价。")
    st.download_button(
        "下载入选文献清单（CSV）",
        data=papers_to_csv(papers),
        file_name=f"HerbMet-{herb}-papers.csv",
        mime="text/csv",
        key=f"{download_key}-papers",
    )


def split_report_sections(report):
    """按报告中的编号标题拆页；旧报告格式无法识别时保留完整显示。"""
    pattern = re.compile(r"(?m)^(?:#{1,4}\s*)?(?:\*\*)?([1-9])(?:[.、])\s+.+$")
    matches = list(pattern.finditer(report))
    if len(matches) < 2:
        return [("完整报告", report)]
    sections = []
    for index, match in enumerate(matches):
        start = 0 if index == 0 else match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(report)
        content = report[start:end].strip()
        title_line = match.group(0)
        title = re.sub(r"[#*]", "", title_line).strip()
        sections.append((title[:36], content))
    return sections


@st.dialog("报告问答助手", width="large")
def report_qa_dialog(report, herb, api_key, base_url, model, state_key):
    st.warning("回答仅根据当前自动生成的报告整理，可能遗漏或误解信息。重要结论请核对 PMID、DOI 和论文全文；不得用于诊断或用药决策。")
    history_key = f"qa-history-{state_key}"
    history = st.session_state.setdefault(history_key, [])
    for item in history[-6:]:
        with st.chat_message("user"):
            st.markdown(item["question"])
        with st.chat_message("assistant"):
            st.markdown(item["answer"])
    with st.form(f"qa-form-{state_key}"):
        question = st.text_input("围绕当前报告提问", placeholder=f"例如：{herb}目前有人体药代动力学证据吗？")
        ask = st.form_submit_button("发送问题", type="primary")
    if ask:
        if not question.strip():
            st.warning("请先输入问题。")
        elif not api_key or not base_url or not model:
            st.error("问答助手需要模型 API Key。请先在左侧模型设置中填写。")
        else:
            try:
                with st.spinner("正在核对当前报告…"):
                    answer = answer_report_question(report, question.strip(), api_key, base_url, model)
                history.append({"question": question.strip(), "answer": answer})
                with st.chat_message("assistant"):
                    st.markdown(answer)
            except Exception as error:
                show_model_error(error)


def display_report(report, herb, papers=None, download_key="report", api_key="", base_url="", model=""):
    if papers:
        display_evidence_overview(papers, herb, download_key)
        with st.expander("查看入选文献与相关性", expanded=False):
            display_papers(papers)
    st.header("文献分析报告")
    sections = split_report_sections(report)
    if len(sections) > 1:
        st.caption(f"报告共 {len(sections)} 页，可按章节阅读，减少长页面滚动。")
        section_labels = [title for title, _ in sections]
        selected_section = st.selectbox("报告分页", section_labels, key=f"section-{download_key}")
        section_content = dict(sections)[selected_section]
        with st.container(border=True):
            st.markdown(section_content)
    else:
        with st.container(border=True):
            st.markdown(report)
    warnings = terminology_warnings(report)
    if warnings:
        st.warning("术语检查发现潜在冲突：\n\n- " + "\n- ".join(warnings))
    action1, action2 = st.columns(2)
    with action1:
        st.download_button("下载完整 Markdown 报告", data=report, file_name=f"HerbMet-{herb}-report.md", mime="text/markdown", key=download_key, use_container_width=True)
    with action2:
        if st.button("打开报告问答助手", key=f"qa-open-{download_key}", use_container_width=True):
            report_qa_dialog(report, herb, api_key, base_url, model, download_key)


def save_study(herb, scientific_name, overview_papers, adme_papers, model, report):
    st.session_state["sb_client"].table("studies").insert({
        "user_id": st.session_state["user_id"],
        "herb_name": herb,
        "scientific_name": scientific_name,
        "report": report,
        "papers": [*overview_papers, *adme_papers],
        "overview_count": len(overview_papers),
        "adme_count": len(adme_papers),
        "model_name": model,
    }).execute()


def load_studies():
    response = st.session_state["sb_client"].table("studies").select("*").order("created_at", desc=True).limit(50).execute()
    return response.data or []


def change_email_password(current_password, new_password, new_password_again):
    if len(new_password) < 8:
        st.error("新密码至少需要 8 位。")
        return
    if new_password != new_password_again:
        st.error("两次输入的新密码不一致。")
        return
    if current_password == new_password:
        st.error("新密码不能与当前密码相同。")
        return
    try:
        client = supabase_client()
        response = client.auth.sign_in_with_password({
            "email": st.session_state["username"],
            "password": current_password,
        })
        client.auth.update_user({"password": new_password})
        st.session_state["sb_client"] = client
        if response.session:
            save_login_cookie(response.session, "byok")
        st.success("密码修改成功，下次登录请使用新密码。")
    except Exception:
        st.error("当前密码不正确，或密码修改暂时失败。")


def send_password_reset_code(email):
    email = email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        st.error("请输入正确的邮箱地址。")
        return
    try:
        client = supabase_client()
        client.auth.sign_in_with_otp({
            "email": email,
            "options": {"should_create_user": False},
        })
        st.session_state["reset_email"] = email
        st.success("如果该邮箱已经注册，验证码将发送到邮箱。请检查收件箱和垃圾邮件。")
    except Exception:
        # 不暴露邮箱是否注册，避免被用来探测用户账号。
        st.success("如果该邮箱已经注册，验证码将发送到邮箱。请检查收件箱和垃圾邮件。")


def reset_password_with_code(code, new_password, new_password_again):
    email = st.session_state.get("reset_email", "")
    if not email:
        st.error("请先发送邮箱验证码。")
        return
    if not code.strip():
        st.error("请输入邮箱中的验证码。")
        return
    if len(new_password) < 8:
        st.error("新密码至少需要 8 位。")
        return
    if new_password != new_password_again:
        st.error("两次输入的新密码不一致。")
        return
    try:
        client = supabase_client()
        response = client.auth.verify_otp({
            "email": email,
            "token": code.strip(),
            "type": "email",
        })
        if not response.session:
            raise ValueError("验证码未建立有效会话")
        client.auth.update_user({"password": new_password})
        establish_login(client, response, "byok")
        st.session_state.pop("reset_email", None)
        st.success("密码重置成功，正在进入系统。")
        time.sleep(0.8)
        st.rerun()
    except Exception:
        st.error("验证码无效或已过期，请重新获取后再试。")


def show_model_error(error):
    if isinstance(error, AuthenticationError):
        st.error("API Key 无效，或它与当前服务商不匹配。")
    elif isinstance(error, RateLimitError):
        st.error("模型服务当前限流，或账号额度/余额不足。")
    elif isinstance(error, (APIConnectionError, APITimeoutError)):
        st.error("暂时无法连接模型服务，请检查 Base URL 和网络。")
    elif isinstance(error, BadRequestError):
        st.error("模型拒绝了请求，请检查模型名称和使用权限。")
    else:
        st.error("大模型调用暂时失败，请检查 API 配置后重试。")
    with st.expander("查看技术详情（排查问题时使用）"):
        st.code(str(error))


login_gate()
platform_account = st.session_state.get("account_type") == "platform"

st.markdown(
    """
    <section class="herbmet-hero">
      <div class="herbmet-eyebrow">HERBMET · EVIDENCE RESEARCH</div>
      <div class="herbmet-title">🌿 中药材代谢研究助手</div>
      <p class="herbmet-subtitle">从真实文献出发，自动整理代表性成分的吸收、分布、代谢与排泄证据。</p>
    </section>
    """,
    unsafe_allow_html=True,
)
overview_1, overview_2, overview_3 = st.columns(3)
overview_1.metric("预设药材", f"{len(HERB_PROFILES)} 种")
overview_2.metric("功效分类", f"{len({herb_category(n, p) for n, p in HERB_PROFILES.items()})} 类")
overview_3.metric("分析流程", "两阶段检索")

with st.expander("第一次使用？查看三步说明", expanded=False):
    guide_1, guide_2, guide_3 = st.columns(3)
    with guide_1:
        st.markdown('<div class="workflow-step"><div class="workflow-number">STEP 01</div><div class="workflow-title">选择药材</div><div class="workflow-copy">按功效分类快速选择，或直接输入中文名、英文学名。</div></div>', unsafe_allow_html=True)
    with guide_2:
        st.markdown('<div class="workflow-step"><div class="workflow-number">STEP 02</div><div class="workflow-title">检索与筛选</div><div class="workflow-copy">先查成分概览，再围绕代表性成分检索直接 ADME 证据。</div></div>', unsafe_allow_html=True)
    with guide_3:
        st.markdown('<div class="workflow-step"><div class="workflow-number">STEP 03</div><div class="workflow-title">生成报告</div><div class="workflow-copy">整理吸收、分布、代谢、排泄、酶与证据局限，并保存历史。</div></div>', unsafe_allow_html=True)
if platform_account:
    st.info("当前账号已接入平台模型，无需填写 API Key。")
else:
    st.info("普通账号可以无 Key 使用第一阶段基础检索；填写自己的模型 API Key 后可自动发现新成分并生成报告。")

with st.sidebar:
    st.header("模型设置")
    if platform_account:
        api_key = str(st.secrets["platform_api"]["api_key"])
        base_url = str(st.secrets["platform_api"]["base_url"])
        model = str(st.secrets["platform_api"]["model"])
        st.success(f"平台模型：{model}")
        st.caption("当前账号使用平台额度，请仅提供给可信用户。")
    else:
        provider = st.selectbox("服务商", ("阿里云百炼", "OpenAI 兼容接口（自定义）"))
        base_url = st.text_input("Base URL", value="https://dashscope.aliyuncs.com/compatible-mode/v1" if provider == "阿里云百炼" else "")
        model = st.text_input("模型名称", value="qwen-plus" if provider == "阿里云百炼" else "")
        api_key = st.text_input("API Key", type="password", placeholder="仅用于当前会话")
    st.divider()
    with st.expander("账号安全"):
        if platform_account:
            st.caption("平台账号密码由站点管理员在 Streamlit Secrets 的 [auth] 配置中修改。")
        else:
            with st.form("change_password_form"):
                current_password = st.text_input("当前密码", type="password")
                new_password = st.text_input("新密码（至少 8 位）", type="password")
                new_password_again = st.text_input("再次输入新密码", type="password")
                change_submitted = st.form_submit_button("修改密码", use_container_width=True)
            if change_submitted:
                change_email_password(current_password, new_password, new_password_again)

if api_key.strip():
    st.success("当前模式：有 Key 增强模式 · 自动提取候选成分，并可完成 ADME 报告")
else:
    st.warning("当前模式：无 Key 基础模式 · 可检索成分概览并读取预设成分；自动提取和报告生成不可用")

with st.expander("无 Key与有 Key有什么区别？", expanded=False):
    mode_left, mode_right = st.columns(2)
    with mode_left:
        st.markdown("**无 Key基础模式**")
        st.markdown("- 检索成分概览文献\n- 显示目录预设代表性成分\n- 不调用模型、不消耗 Token\n- 目录外药材不能自动识别新成分")
    with mode_right:
        st.markdown("**有 Key增强模式**")
        st.markdown("- 包含基础模式全部功能\n- 从文献摘要自动提取新成分\n- 可继续检索 ADME 并生成报告\n- 提取和报告生成会消耗 Token")

analysis_tab, history_tab = st.tabs(("新建分析", "我的历史记录"))
with analysis_tab:
    catalog_categories = {herb_category(name, profile) for name, profile in HERB_PROFILES.items()}
    categories = ["全部", *[name for name in CATEGORY_FALLBACK if name in catalog_categories]]
    categories.extend(sorted(catalog_categories - set(categories)))
    st.markdown(
        f'<div class="catalog-card"><b>药材知识库</b><br><span style="color:#9fb0a7">已收录 {len(HERB_PROFILES)} 种常用药材，选择分类可快速定位，也可直接输入其他药材。</span></div>',
        unsafe_allow_html=True,
    )
    popular_herb = st.pills(
        "常用药材快捷入口",
        ("黄芪", "人参", "甘草", "当归", "丹参", "生姜", "黄连", "三七"),
        selection_mode="single",
        key="popular_herb",
    )
    picker_left, picker_right = st.columns((1, 1.35), gap="medium")
    with picker_left:
        category = st.selectbox("功效分类", categories, help="先选分类可以更快找到已收录的药材。")
    herb_options = [
        name
        for name, profile in HERB_PROFILES.items()
        if category == "全部" or herb_category(name, profile) == category
    ]
    with picker_right:
        quick_herb = st.selectbox("快速选择药材", ["手动输入", *herb_options])
    if quick_herb != "手动输入":
        selected_profile = HERB_PROFILES[quick_herb]
        components = "、".join(compound_display_name(item) for item in selected_profile.get("constituents", [])[:4]) or "检索后识别"
        st.caption(f"已选择：{quick_herb} · {selected_profile.get('scientific_name', '')}　｜　代表性成分：{components}")
    with st.form("analysis_form"):
        manual_herb = st.text_input(
            "或直接输入中药材名称",
            placeholder="例如：黄芪",
            help="手动输入优先于上方的快速选择，也可以输入尚未收录的药材或英文学名。",
        )
        submitted = st.form_submit_button("第一阶段：发现候选成分", type="primary")
    if submitted:
        st.session_state.pop("latest_report_result", None)
        st.session_state.pop("qa-history-latest-report", None)
        herb = manual_herb.strip() or popular_herb or (quick_herb if quick_herb != "手动输入" else "")
        herb, api_key, base_url, model = herb.strip(), api_key.strip(), base_url.strip(), model.strip()
        if not herb:
            st.warning("请输入中药材名称。")
            st.stop()
        if api_key and (not base_url or not model):
            st.error("使用增强模式时，Base URL 和模型名称必须填写。")
            st.stop()
        profile = resolve_herb(herb)
        scientific_name = profile["scientific_name"]
        try:
            with st.status("第一阶段：正在检索成分概览…", expanded=True) as status:
                overview_papers, overview_excluded = collect_overview(profile, return_audit=True)
                status.write(f"成分概览文献：{len(overview_papers)} 篇")
                if api_key:
                    status.write("增强模式：正在从摘要中识别候选成分…")
                    try:
                        candidates = discover_constituents(profile, overview_papers, api_key, base_url, model)
                        discovery_mode = "有 Key增强模式"
                        extraction_warning = ""
                    except Exception:
                        candidates = list(profile.get("constituents") or [])
                        discovery_mode = "增强模式提取失败，已使用目录预设成分"
                        extraction_warning = "模型暂时无法自动提取新成分，本次已退回药材目录中的预设成分；文献检索结果不受影响。"
                        status.write("自动提取暂时失败，已安全退回目录预设成分。")
                else:
                    status.write("基础模式：读取药材目录中的预设成分，不调用模型。")
                    candidates = list(profile.get("constituents") or [])
                    discovery_mode = "无 Key基础模式"
                    extraction_warning = ""
                status.update(label="第一阶段完成，请确认候选成分", state="complete")
        except RuntimeError as error:
            st.error(str(error))
            st.stop()
        except Exception as error:
            show_model_error(error)
            st.stop()
        st.session_state["stage1_result"] = {
            "herb": herb,
            "profile": profile,
            "overview": overview_papers,
            "overview_excluded": overview_excluded,
            "candidates": candidates,
            "mode": discovery_mode,
            "extraction_warning": extraction_warning,
        }

    stage1 = st.session_state.get("stage1_result")
    if stage1:
        result_title, restart_col = st.columns((5, 1))
        with result_title:
            st.success(f"第一阶段完成：{stage1['herb']}（{stage1['profile']['scientific_name']}） · {stage1.get('mode', '基础模式')}")
        with restart_col:
            if st.button("重新开始", use_container_width=True, key="restart_analysis"):
                st.session_state.pop("stage1_result", None)
                st.session_state.pop("latest_report_result", None)
                st.session_state.pop("qa-history-latest-report", None)
                st.rerun()
        if stage1.get("extraction_warning"):
            st.warning(stage1["extraction_warning"])
        summary1, summary2, summary3 = st.columns(3)
        summary1.metric("入选概览文献", len(stage1["overview"]))
        summary2.metric("未纳入文献", len(stage1.get("overview_excluded", [])))
        summary3.metric("候选成分", len(stage1["candidates"]))
        if stage1["overview"]:
            with st.expander("查看第一阶段入选文献", expanded=False):
                st.caption("这些文献用于认识药材整体成分，不等同于具体成分的直接 ADME 证据。")
                display_papers(stage1["overview"])
        display_screening_audit(stage1.get("overview_excluded", []), "查看第一阶段未纳入文献与原因")
        st.caption("下面的成分来自药材目录与第一阶段文献摘要。请取消不需要的成分，也可以补充一个英文成分名。")
        if not stage1["candidates"]:
            st.warning("该药材不在预设目录中，无 Key模式无法自动识别候选成分。您可以填写成分英文名，或添加 API Key 后重新运行第一阶段。")
        selected_targets = st.multiselect(
            "候选成分（建议选择 1–5 个）",
            stage1["candidates"],
            default=stage1["candidates"][:5],
            format_func=compound_display_name,
        )
        extra_target = st.text_input("补充成分英文名（可选）", placeholder="例如：Astragaloside II")
        if st.button("第二阶段：检索 ADME 并生成报告", type="primary"):
            targets = list(selected_targets)
            if extra_target.strip() and extra_target.strip().lower() not in {item.lower() for item in targets}:
                targets.append(extra_target.strip())
            if not targets:
                st.warning("请至少选择或填写一个候选成分。")
                st.stop()
            api_key, base_url, model = api_key.strip(), base_url.strip(), model.strip()
            if not api_key or not base_url or not model:
                st.error("API Key、Base URL 和模型名称都必须填写。")
                st.stop()
            with st.status("第二阶段：正在逐个检索 ADME 证据…", expanded=True) as status:
                for target in targets:
                    status.write(f"正在检索：{compound_display_name(target)}")
                try:
                    adme_papers, adme_excluded = collect_adme(targets, return_audit=True)
                except RuntimeError as error:
                    st.error(str(error))
                    st.stop()
                status.update(label="第二阶段检索完成", state="complete")
            if not adme_papers:
                st.warning("没有找到达到标准的直接 ADME 或生物转化文献。可以减少候选成分或更换英文名称后重试。")
                st.stop()
            report_profile = dict(stage1["profile"])
            report_profile["constituents"] = targets
            try:
                with st.spinner("正在基于入选证据生成结构化报告…"):
                    report = generate_report(stage1["herb"], report_profile, stage1["overview"], adme_papers, api_key, base_url=base_url, model=model)
            except Exception as error:
                show_model_error(error)
                st.stop()
            try:
                save_study(stage1["herb"], report_profile["scientific_name"], stage1["overview"], adme_papers, model, report)
                st.success("分析完成，已保存到您的云端历史记录。")
            except Exception as error:
                st.warning(f"报告已生成，但云端保存失败：{error}")
            st.session_state["latest_report_result"] = {
                "herb": stage1["herb"],
                "report": report,
                "papers": [*stage1["overview"], *adme_papers],
                "targets": targets,
                "overview_count": len(stage1["overview"]),
                "adme_count": len(adme_papers),
                "adme_excluded": adme_excluded,
            }

        latest = st.session_state.get("latest_report_result")
        if latest and latest.get("herb") == stage1["herb"]:
            st.divider()
            st.header("本次分析结果")
            st.caption("报告和问答助手会保留在当前的新建分析页面；云端副本也可在“我的历史记录”中查看。")
            col1, col2, col3 = st.columns(3)
            col1.metric("候选成分", len(latest["targets"]))
            col2.metric("成分概览文献", latest["overview_count"])
            col3.metric("ADME / 生物转化证据", latest["adme_count"])
            display_screening_audit(latest.get("adme_excluded", []), "查看第二阶段未纳入文献与原因")
            display_report(latest["report"], latest["herb"], latest["papers"], "latest-report", api_key, base_url, model)

with history_tab:
    st.header("我的历史记录")
    st.caption("历史报告保存在 Supabase，刷新或更换设备后仍可查看。")
    try:
        studies = load_studies()
    except Exception as error:
        st.error(f"历史记录加载失败：{error}")
        studies = []
    if not studies:
        st.info("还没有历史记录。完成一次分析后会显示在这里。")
    else:
        history_query = st.text_input("搜索历史记录", placeholder="输入药材中文名或英文学名", key="history_query").strip().lower()
        if history_query:
            studies = [
                study for study in studies
                if history_query in str(study.get("herb_name", "")).lower()
                or history_query in str(study.get("scientific_name", "")).lower()
            ]
        st.caption(f"找到 {len(studies)} 条记录")
    if studies:
        labels = {f"{s['herb_name']} · {s['created_at'][:16].replace('T', ' ')}": s for s in studies}
        selected = labels[st.selectbox("选择报告", tuple(labels.keys()))]
        c1, c2, c3 = st.columns(3)
        c1.metric("药材", selected["herb_name"])
        c2.metric("ADME 证据", selected["adme_count"])
        c3.metric("模型", selected.get("model_name") or "未知")
        display_report(selected["report"], selected["herb_name"], selected.get("papers") or [], f"history-{selected['id']}", api_key, base_url, model)
    elif 'history_query' in st.session_state and st.session_state["history_query"]:
        st.info("没有找到匹配的历史记录，请更换关键词。")

st.divider()
st.caption("仅用于科研与学习辅助，不用于临床诊疗。关键结论请回查 PMID、DOI 与论文全文。")
