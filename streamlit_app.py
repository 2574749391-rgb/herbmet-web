import base64
import hashlib
import hmac
import json
import re
import time

import streamlit as st
from cryptography.fernet import Fernet, InvalidToken
from openai import APIConnectionError, APITimeoutError, AuthenticationError, BadRequestError, RateLimitError
from streamlit_cookies_controller import CookieController
from supabase import create_client

from main import HERB_PROFILES, collect_evidence, generate_report, resolve_herb, terminology_warnings


st.set_page_config(page_title="HerbMet · 中药材代谢研究助手", page_icon="🌿", layout="wide")

st.markdown(
    """
    <style>
    .stApp { background: radial-gradient(circle at 75% 0%, rgba(47,158,104,.10), transparent 30%), #0e1117; }
    .block-container { max-width: 1240px; padding-top: 2.2rem; padding-bottom: 3rem; }
    .herbmet-hero {
        padding: 1.7rem 1.9rem; margin-bottom: 1.1rem; border-radius: 20px;
        border: 1px solid rgba(91, 207, 145, .23);
        background: linear-gradient(120deg, rgba(25,72,54,.82), rgba(20,33,46,.72));
        box-shadow: 0 14px 36px rgba(0,0,0,.18);
    }
    .herbmet-eyebrow { color: #77dfa8; font-size: .82rem; letter-spacing: .13em; font-weight: 700; }
    .herbmet-title { font-size: 2.25rem; line-height: 1.15; font-weight: 800; margin: .35rem 0 .55rem; color: #f4fff8; }
    .herbmet-subtitle { color: #b9c8c0; font-size: 1rem; margin: 0; }
    .catalog-card {
        border: 1px solid rgba(255,255,255,.10); border-radius: 16px;
        padding: 1rem 1.15rem; background: rgba(255,255,255,.025); margin: .5rem 0 1rem;
    }
    div[data-testid="stForm"] { border-radius: 16px; border-color: rgba(91,207,145,.20); }
    div[data-testid="stMetric"] { background: rgba(255,255,255,.035); border: 1px solid rgba(255,255,255,.08); padding: .8rem 1rem; border-radius: 14px; }
    .stButton > button, .stFormSubmitButton > button { border-radius: 10px; font-weight: 700; }
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
    st.title("🌿 HerbMet")
    st.subheader("登录中药材代谢研究助手")
    login_tab, register_tab = st.tabs(("账号登录", "注册账号"))
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
    st.caption("登录信息会以加密会话保存，刷新页面后仍可保持登录。")
    st.stop()


def display_papers(papers):
    for index, paper in enumerate(papers, start=1):
        st.markdown(f"**{index}. {paper['title']}**")
        st.caption(f"目标：{paper.get('research_target', '未知')} ｜ {paper['evidence_type']} ｜ 相关性：{paper['relevance_score']}/100")
        identifiers = []
        if paper.get("pmid"):
            identifiers.append(f"[PMID {paper['pmid']}](https://pubmed.ncbi.nlm.nih.gov/{paper['pmid']}/)")
        if paper.get("doi"):
            identifiers.append(f"DOI: {paper['doi']}")
        st.markdown(" ｜ ".join(identifiers) or "无 PMID/DOI")
        st.divider()


def display_report(report, herb, papers=None, download_key="report"):
    if papers:
        with st.expander("查看入选文献与相关性", expanded=False):
            display_papers(papers)
    st.header("文献分析报告")
    st.markdown(report)
    warnings = terminology_warnings(report)
    if warnings:
        st.warning("术语检查发现潜在冲突：\n\n- " + "\n- ".join(warnings))
    st.download_button("下载 Markdown 报告", data=report, file_name=f"HerbMet-{herb}-report.md", mime="text/markdown", key=download_key)


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
if platform_account:
    st.info("当前账号已接入平台模型，无需填写 API Key。")
else:
    st.info("普通账号使用自己的模型 API Key；Key 仅保存在当前网页会话中。")

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

analysis_tab, history_tab = st.tabs(("新建分析", "我的历史记录"))
with analysis_tab:
    catalog_categories = {herb_category(name, profile) for name, profile in HERB_PROFILES.items()}
    categories = ["全部", *[name for name in CATEGORY_FALLBACK if name in catalog_categories]]
    categories.extend(sorted(catalog_categories - set(categories)))
    st.markdown(
        f'<div class="catalog-card"><b>药材知识库</b><br><span style="color:#9fb0a7">已收录 {len(HERB_PROFILES)} 种常用药材，选择分类可快速定位，也可直接输入其他药材。</span></div>',
        unsafe_allow_html=True,
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
        components = "、".join(selected_profile.get("constituents", [])[:4]) or "检索后识别"
        st.caption(f"已选择：{quick_herb} · {selected_profile.get('scientific_name', '')}　｜　代表性成分：{components}")
    with st.form("analysis_form"):
        manual_herb = st.text_input(
            "或直接输入中药材名称",
            placeholder="例如：黄芪",
            help="手动输入优先于上方的快速选择，也可以输入尚未收录的药材或英文学名。",
        )
        submitted = st.form_submit_button("开始分析", type="primary")
    if submitted:
        herb = manual_herb.strip() or (quick_herb if quick_herb != "手动输入" else "")
        herb, api_key, base_url, model = herb.strip(), api_key.strip(), base_url.strip(), model.strip()
        if not herb:
            st.warning("请输入中药材名称。")
            st.stop()
        if not api_key or not base_url or not model:
            st.error("API Key、Base URL 和模型名称都必须填写。")
            st.stop()
        profile = resolve_herb(herb)
        scientific_name = profile["scientific_name"]
        st.info(f"检索对象：{herb}（{scientific_name}）")
        try:
            with st.status("正在进行两阶段文献检索…", expanded=True) as status:
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
                report = generate_report(herb, profile, overview_papers, adme_papers, api_key, base_url=base_url, model=model)
        except Exception as error:
            show_model_error(error)
            st.stop()
        try:
            save_study(herb, scientific_name, overview_papers, adme_papers, model, report)
            st.success("分析完成，已保存到您的云端历史记录。")
        except Exception as error:
            st.warning(f"报告已生成，但云端保存失败：{error}")
        display_report(report, herb, [*overview_papers, *adme_papers], "latest-report")

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
        labels = {f"{s['herb_name']} · {s['created_at'][:16].replace('T', ' ')}": s for s in studies}
        selected = labels[st.selectbox("选择报告", tuple(labels.keys()))]
        c1, c2, c3 = st.columns(3)
        c1.metric("药材", selected["herb_name"])
        c2.metric("ADME 证据", selected["adme_count"])
        c3.metric("模型", selected.get("model_name") or "未知")
        display_report(selected["report"], selected["herb_name"], selected.get("papers") or [], f"history-{selected['id']}")

st.divider()
st.caption("仅用于科研与学习辅助，不用于临床诊疗。关键结论请回查 PMID、DOI 与论文全文。")
