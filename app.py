import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import copy
import hashlib
import logging
from datetime import datetime, timedelta
from supabase import create_client, Client

# ============================================================
# 1. 系统配置与常量
# ============================================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

st.set_page_config(page_title="跨境 S&OP 系统 V12 - 优化版", layout="wide", page_icon="🚢")
st.markdown("""
<style>
    .stMetric {background-color: #f8f9fa; padding: 10px; border-radius: 8px; border: 1px solid #eee;}
    .stDataFrame {border: 1px solid #ddd; border-radius: 5px;}
    div[data-testid="stStatusWidget"] {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# Gemini API Key - 从 Streamlit Secrets 读取（不再硬编码）
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")

DEPTS = ["一部", "四部", "五部", "珍组", "琪组", "tt"]

# 密码使用 SHA-256 哈希存储
def _hash_pw(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

USER_CREDENTIALS = {
    "admin":  _hash_pw("admin888"),
    "一部":   _hash_pw("123"),
    "四部":   _hash_pw("1234"),
    "五部":   _hash_pw("12345"),
    "珍组":   _hash_pw("z"),
    "琪组":   _hash_pw("q"),
    "tt":     _hash_pw("tt"),
}

# ============================================================
# 2. Supabase 连接与数据函数
# ============================================================
@st.cache_resource
def init_supabase():
    """初始化 Supabase 客户端"""
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase: Client = init_supabase()


def load_all_sku_data():
    """从 Supabase 加载所有 SKU 数据"""
    try:
        result = supabase.table("sku_data").select("*").execute()
        full_db = {}
        for row in result.data:
            full_db[row["sku_name"]] = json.loads(row["data"])
        return full_db
    except Exception as e:
        logger.error(f"加载数据失败: {e}")
        st.error(f"数据加载失败: {e}")
        return {}


def save_sku_data(sku_name, data, user):
    """保存单个 SKU 数据到 Supabase"""
    try:
        supabase.table("sku_data").upsert({
            "sku_name": sku_name,
            "data": json.dumps(data, ensure_ascii=False),
            "updated_at": datetime.now().isoformat()
        }).execute()
        write_log(user, sku_name, "执行数据保存")
        if 'full_db' in st.session_state:
            del st.session_state['full_db']
    except Exception as e:
        logger.error(f"保存数据失败: {e}")
        st.error(f"数据保存失败: {e}")


def delete_sku_from_db(sku_name, user):
    """从 Supabase 删除 SKU"""
    try:
        supabase.table("sku_data").delete().eq("sku_name", sku_name).execute()
        write_log(user, sku_name, "删除SKU")
        if 'full_db' in st.session_state:
            del st.session_state['full_db']
    except Exception as e:
        logger.error(f"删除SKU失败: {e}")


def write_log(user, sku, action):
    """写入操作日志到 Supabase"""
    try:
        supabase.table("operation_logs").insert({
            "timestamp": datetime.now().isoformat(),
            "user": user,
            "sku": sku,
            "action": action
        }).execute()
    except Exception as e:
        logger.error(f"写入日志失败: {e}")


def load_tasks(sku):
    """加载 SKU 任务清单"""
    try:
        result = supabase.table("ai_tasks").select("*").eq("sku_name", sku).execute()
        if result.data:
            return json.loads(result.data[0]["tasks"])
    except Exception as e:
        logger.warning(f"加载任务失败: {e}")
    return []


def save_tasks(sku, tasks):
    """保存 SKU 任务清单"""
    try:
        supabase.table("ai_tasks").upsert({
            "sku_name": sku,
            "tasks": json.dumps(tasks, ensure_ascii=False),
            "updated_at": datetime.now().isoformat()
        }).execute()
    except Exception as e:
        logger.error(f"保存任务失败: {e}")


def read_memory_file():
    """读取 AI 专家规约"""
    try:
        result = supabase.table("ai_memory").select("*").eq("id", 1).execute()
        if result.data:
            return result.data[0]["content"]
    except Exception as e:
        logger.warning(f"读取规约失败: {e}")
    return ""


def save_memory(content):
    """保存 AI 专家规约"""
    try:
        supabase.table("ai_memory").upsert({
            "id": 1,
            "content": content,
            "updated_at": datetime.now().isoformat()
        }).execute()
    except Exception as e:
        logger.error(f"保存规约失败: {e}")


def load_report(sku):
    """加载 AI 诊断报告"""
    try:
        result = supabase.table("ai_reports").select("*").eq("sku_name", sku).execute()
        if result.data:
            return result.data[0]["content"]
    except Exception as e:
        logger.warning(f"加载报告失败: {e}")
    return ""


def save_report(sku, content):
    """保存 AI 诊断报告"""
    try:
        supabase.table("ai_reports").upsert({
            "sku_name": sku,
            "content": content,
            "updated_at": datetime.now().isoformat()
        }).execute()
    except Exception as e:
        logger.error(f"保存报告失败: {e}")


def delete_report(sku):
    """删除 AI 诊断报告"""
    try:
        supabase.table("ai_reports").delete().eq("sku_name", sku).execute()
    except Exception as e:
        logger.error(f"删除报告失败: {e}")


def load_operation_logs():
    """加载操作日志"""
    try:
        result = supabase.table("operation_logs").select("*").order("timestamp", desc=True).execute()
        return result.data
    except Exception as e:
        logger.error(f"加载日志失败: {e}")
        return []


# ============================================================
# 3. 登录验证
# ============================================================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔐 S&OP 决策系统 V12")
    with st.form("login"):
        u = st.selectbox("部门选择", ["请选择"] + list(USER_CREDENTIALS.keys()))
        p = st.text_input("登录密码", type="password")
        if st.form_submit_button("登录系统"):
            if USER_CREDENTIALS.get(u) == _hash_pw(p):
                st.session_state.logged_in = True
                st.session_state.user = u
                st.rerun()
            else:
                st.error("密码错误")
    st.stop()

current_user = st.session_state.user
is_admin = (current_user == "admin")

# ============================================================
# 4. 数据加载与侧边栏
# ============================================================
if 'full_db' not in st.session_state:
    st.session_state['full_db'] = load_all_sku_data()
full_db = st.session_state['full_db']

available_skus = sorted(list(full_db.keys())) if full_db else ["请先上传或创建SKU"]
target_sku = st.sidebar.selectbox("🎯 选择 SKU", available_skus)
sku_key = str(target_sku)

# Admin SKU 管理
if is_admin:
    with st.sidebar.expander("📦 SKU 管理"):
        new_sku_name = st.text_input("新建 SKU 名称")
        if st.button("➕ 创建 SKU") and new_sku_name:
            if new_sku_name not in full_db:
                full_db[new_sku_name] = {
                    "config": {"init_inv": 0, "price": 50, "target_doh": 30, "frozen_months": 2, "lt": 2},
                    "dept_plans": {}, "shipments": {}, "actual_sales": {}, "notes": {}
                }
                save_sku_data(new_sku_name, full_db[new_sku_name], current_user)
                write_log(current_user, new_sku_name, "新建SKU")
                st.success(f"SKU [{new_sku_name}] 创建成功")
                st.rerun()
            else:
                st.warning("该 SKU 已存在")

        if len(available_skus) > 0 and available_skus[0] != "请先上传或创建SKU":
            del_sku = st.selectbox("选择要删除的 SKU", ["--"] + available_skus)
            confirm_key = "confirm_del_sku"
            if confirm_key not in st.session_state:
                st.session_state[confirm_key] = False
            if st.button("🗑️ 删除 SKU") and del_sku != "--":
                st.session_state[confirm_key] = True
                st.session_state["del_target"] = del_sku
            if st.session_state.get(confirm_key) and st.session_state.get("del_target"):
                st.warning(f"确认删除 **{st.session_state['del_target']}**？此操作不可撤销。")
                c1, c2 = st.columns(2)
                if c1.button("✅ 确认删除", type="primary"):
                    target = st.session_state["del_target"]
                    if target in full_db:
                        del full_db[target]
                        delete_sku_from_db(target, current_user)
                    st.session_state[confirm_key] = False
                    st.session_state["del_target"] = None
                    st.rerun()
                if c2.button("❌ 取消"):
                    st.session_state[confirm_key] = False
                    st.session_state["del_target"] = None
                    st.rerun()

# 初始化 SKU 数据结构
if sku_key not in full_db:
    full_db[sku_key] = {
        "config": {"init_inv": 0, "price": 50, "target_doh": 30, "frozen_months": 2, "lt": 2},
        "dept_plans": {}, "shipments": {}, "actual_sales": {}, "notes": {}
    }
db = full_db[sku_key]
for field in ["notes", "actual_sales"]:
    if field not in db:
        db[field] = {}

editor_key = f"plan_editor_{sku_key}"
delta_key = f"plan_deltas_{sku_key}"
if delta_key not in st.session_state:
    st.session_state[delta_key] = {}

# 侧边栏参数
st.sidebar.divider()
st.sidebar.subheader("⚙️ 补货策略参数")
price = st.sidebar.number_input("产品单价 ($)", value=float(db["config"].get("price", 50.0)), disabled=not is_admin)
init_inv = st.sidebar.number_input("2026 期初在仓 (PCS)", value=int(db["config"].get("init_inv", 0)), disabled=not is_admin)
target_doh = st.sidebar.number_input("目标在仓备货周转(DOH)", value=int(db["config"].get("target_doh", 30)), disabled=not is_admin)
lt_months = st.sidebar.number_input("物流时效 (月)", value=int(db["config"].get("lt", 2)), min_value=1, disabled=not is_admin)
frozen_m = st.sidebar.slider("生产锁定窗口 (月)", 0, 6, int(db["config"].get("frozen_months", 2)), disabled=not is_admin)

# ============================================================
# 5. 隔离推演逻辑 (Working DB)
# ============================================================
working_db = copy.deepcopy(db)
start_date = datetime(2026, 1, 1)
f_dates = pd.date_range(start=start_date, periods=12, freq='MS')
today_str = datetime.now().strftime('%Y-%m')

# 合并编辑器增量到 working_db
if editor_key in st.session_state:
    curr_edits = st.session_state[editor_key].get('edited_rows', {})
    for row_idx_str, changes in curr_edits.items():
        if row_idx_str not in st.session_state[delta_key]:
            st.session_state[delta_key][row_idx_str] = {}
        st.session_state[delta_key][row_idx_str].update(changes)

for row_idx_str, changes in st.session_state[delta_key].items():
    row_idx = int(row_idx_str)
    if row_idx >= len(f_dates):
        continue
    m = f_dates[row_idx].strftime('%Y-%m')
    for col, val in changes.items():
        try:
            if col == "备注":
                working_db.setdefault("notes", {})[m] = str(val)
            else:
                val = int(float(val)) if val not in [None, ""] else 0
                if col == "发货计划(ETD)" and is_admin:
                    working_db["shipments"][m] = val
                elif "_预测" in col:
                    dept = col.split("_")[0]
                    working_db.setdefault("dept_plans", {}).setdefault(m, {})[dept] = val
                elif "_实绩" in col:
                    dept = col.split("_")[0]
                    working_db.setdefault("actual_sales", {}).setdefault(m, {})[dept] = val
        except (ValueError, TypeError, KeyError) as e:
            logger.warning(f"编辑应用异常 row={row_idx_str} col={col}: {e}")

working_db["config"].update({
    "price": price, "init_inv": init_inv,
    "target_doh": target_doh, "lt": lt_months, "frozen_months": frozen_m
})

# ============================================================
# 6. 自动补货推演（Admin）
# ============================================================
if is_admin:
    if st.sidebar.button("🤖 执行精准补货推演", type="primary"):
        today_m = today_str
        all_dates = pd.date_range(start="2026-01-01", periods=24, freq='MS')
        true_demands = []
        for d in all_dates:
            m_str = d.strftime('%Y-%m')
            if m_str < today_m:
                val = sum(working_db.get("actual_sales", {}).get(m_str, {}).values())
            else:
                ref_m = m_str if d.year == 2026 else "2026-12"
                val = sum(working_db.get("dept_plans", {}).get(ref_m, {}).values())
            true_demands.append(float(val))

        new_shipments = {}
        arrival_queue = [0.0] * 36
        for i in range(12):
            ds_t = all_dates[i].strftime('%Y-%m')
            if i < frozen_m:
                val = float(working_db["shipments"].get(ds_t, 0))
                new_shipments[ds_t] = val
                if i + lt_months < 36:
                    arrival_queue[i + lt_months] += val
            else:
                new_shipments[ds_t] = 0.0

        sim_inv = float(init_inv)
        for i in range(12):
            ds_t = all_dates[i].strftime('%Y-%m')
            sim_inv += arrival_queue[i]
            if i >= frozen_m:
                arrival_idx = i + lt_months
                target_stock = 0.0
                days_to_cover = target_doh
                temp_idx = arrival_idx + 1
                while days_to_cover > 0 and temp_idx < len(true_demands):
                    if days_to_cover >= 30:
                        target_stock += true_demands[temp_idx]
                        days_to_cover -= 30
                    else:
                        target_stock += true_demands[temp_idx] * (days_to_cover / 30)
                        days_to_cover = 0
                    temp_idx += 1
                gap = (sum(true_demands[i: arrival_idx + 1]) + target_stock) - \
                      (sim_inv + sum(arrival_queue[i + 1: arrival_idx + 1]))
                suggestion = max(0.0, gap)
                new_shipments[ds_t] = int(suggestion)
                if i + lt_months < 36:
                    arrival_queue[i + lt_months] += suggestion
            sim_inv -= true_demands[i]

        working_db["shipments"] = new_shipments
        full_db[sku_key] = working_db
        save_sku_data(sku_key, working_db, current_user)
        write_log(current_user, sku_key, "执行AI自动补货推演")
        if delta_key in st.session_state:
            del st.session_state[delta_key]
        st.success("推演成功并已同步到云端！")
        st.rerun()

# ============================================================
# 7. 模拟计算
# ============================================================
sim_res = []
curr_inv = int(working_db["config"]["init_inv"])
cumulative_plan = 0
cumulative_actual = 0

for i, d in enumerate(f_dates):
    ds = d.strftime('%Y-%m')
    actual_total = sum(working_db.get("actual_sales", {}).get(ds, {}).values())
    plan_total = sum(working_db["dept_plans"].get(ds, {}).values())

    if i >= lt_months:
        ship_month = f_dates[i - lt_months].strftime('%Y-%m')
        arr = working_db["shipments"].get(ship_month, 0)
    else:
        arr = 0

    if ds < today_str:
        demand_to_use = actual_total
        cumulative_plan += plan_total
        cumulative_actual += actual_total
    elif ds == today_str:
        if actual_total > 0:
            demand_to_use = actual_total
            cumulative_plan += plan_total
            cumulative_actual += actual_total
        else:
            shortfall = max(0, cumulative_plan - cumulative_actual)
            demand_to_use = plan_total + shortfall
            cumulative_plan = 0
            cumulative_actual = 0
    else:
        if cumulative_plan > 0 or cumulative_actual > 0:
            shortfall = max(0, cumulative_plan - cumulative_actual)
            demand_to_use = plan_total + shortfall
            cumulative_plan = 0
            cumulative_actual = 0
        else:
            demand_to_use = plan_total

    curr_inv = curr_inv + arr - demand_to_use

    in_transit = sum([
        working_db["shipments"].get(f_dates[i - j].strftime('%Y-%m'), 0)
        for j in range(lt_months) if i - j >= 0
    ])

    next_dem = sum(working_db["dept_plans"].get(f_dates[min(i + 1, 11)].strftime('%Y-%m'), {}).values())
    if next_dem > 0:
        effective_inv = max(0, curr_inv)
        doh = round(effective_inv / (next_dem / 30), 1)
    else:
        doh = 999.0 if curr_inv > 0 else 0.0

    sim_res.append({
        "月份": ds, "计划预测": int(plan_total), "实际销量": int(actual_total),
        "发货(ETD)": int(working_db["shipments"].get(ds, 0)), "预计到货": int(arr),
        "期末在仓": int(curr_inv), "期末在途": int(in_transit),
        "全口径库存": int(curr_inv + in_transit),
        "DOH": doh, "备注": working_db.get("notes", {}).get(ds, "")
    })

    curr_inv = max(0, curr_inv)

sim_df = pd.DataFrame(sim_res)

# ============================================================
# 8. 界面渲染
# ============================================================
st.title(f"🚢 {target_sku} 2026 滚动决策台")

has_unsaved = bool(st.session_state[delta_key])
st_col1, st_col2, st_col3 = st.columns([2, 1, 1])
st_col1.markdown(f"**当前用户:** {current_user} {'`(管理员)`' if is_admin else ''}")
if has_unsaved:
    st_col2.warning("⚠️ 有未保存的修改")
else:
    st_col2.success("✅ 数据已同步")
st_col3.markdown(f"**SKU:** `{target_sku}`")

c1, c2, c3, c4 = st.columns(4)
total_plan_yr = sim_df["计划预测"].sum()
avg_pipe_inv = sim_df["全口径库存"].mean()
ito = total_plan_yr / avg_pipe_inv if avg_pipe_inv > 0 else 0
c1.metric("2026 预测总需求", f"{total_plan_yr:,.0f} PCS")
c2.metric("平均全口径库存", f"{avg_pipe_inv:,.0f} PCS")
c3.metric("预估平均在仓周转", f"{365 / ito if ito > 0 else 0:.1f} 天")
c4.metric("周转率(ITO)", f"{round(float(ito), 2)} 次/年")

tab_edit, tab_chart, tab_log, tab_ai = st.tabs(["📝 计划录入与备注", "📈 供需分析图", "📜 审计日志", "🧠 AI 智能诊断"])

# -------- Tab 1: 计划录入 --------
with tab_edit:
    edit_data = []
    for i, r in sim_df.iterrows():
        m = r["月份"]
        row = {"月份": m, "发货计划(ETD)": r["发货(ETD)"], "备注": r["备注"]}
        target_depts = DEPTS if is_admin else [current_user]
        for dept in target_depts:
            row[f"{dept}_预测"] = working_db.get("dept_plans", {}).get(m, {}).get(dept, 0)
            row[f"{dept}_实绩"] = working_db.get("actual_sales", {}).get(m, {}).get(dept, 0)
        edit_data.append(row)

    st.data_editor(
        pd.DataFrame(edit_data),
        use_container_width=True,
        hide_index=True,
        key=editor_key,
        column_config={
            "备注": st.column_config.TextColumn("📝 决策备注", width="large"),
            "月份": st.column_config.TextColumn("月份", width="small")
        }
    )

    col_save1, col_save2 = st.columns([1, 4])
    if col_save1.button("💾 确认保存并同步", type="primary"):
        full_db[sku_key] = working_db
        save_sku_data(sku_key, working_db, current_user)
        if delta_key in st.session_state:
            del st.session_state[delta_key]
        st.success("同步成功！数据已保存到云端数据库。")
        st.rerun()
    if col_save2.button("🚫 放弃当前修改"):
        if delta_key in st.session_state:
            del st.session_state[delta_key]
        st.rerun()

# -------- Tab 2: 供需分析图 --------
with tab_chart:
    def color_doh(val):
        if val == 999.0:
            return 'background-color: #d4edda'
        if val < 15:
            return 'background-color: #f8d7da'
        if val < target_doh:
            return 'background-color: #fff3cd'
        return 'background-color: #d4edda'

    styled_df = sim_df.style \
        .highlight_between(left=-9999, right=-1, subset=['期末在仓'], color='#ffcccc') \
        .map(color_doh, subset=['DOH'])

    st.dataframe(
        styled_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "月份": st.column_config.TextColumn("月份", width="small"),
            "DOH": st.column_config.NumberColumn("DOH", format="%.1f", width="small",
                                                  help="999 = 下月无预测需求，库存充裕"),
            "全口径库存": st.column_config.NumberColumn("全口径库存", width="medium"),
            "备注": st.column_config.TextColumn("备注", width="large")
        }
    )

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=sim_df["月份"], y=sim_df["计划预测"], name="汇总预测",
                             line=dict(color='#BDC3C7', dash='dash')), secondary_y=False)
    fig.add_trace(go.Scatter(x=sim_df["月份"], y=sim_df["实际销量"], name="汇总实绩",
                             line=dict(color='black', width=3)), secondary_y=False)
    fig.add_trace(go.Bar(x=sim_df["月份"], y=sim_df["发货(ETD)"], name="发货(ETD)",
                         marker_color='#3498DB', opacity=0.6), secondary_y=False)
    fig.add_trace(go.Scatter(x=sim_df["月份"], y=sim_df["全口径库存"], name="全口径库存",
                             line=dict(color='#E74C3C', width=2)), secondary_y=False)

    doh_display = sim_df["DOH"].clip(upper=max(target_doh * 3, 120))
    fig.add_trace(go.Scatter(x=sim_df["月份"], y=doh_display, name="DOH(天)",
                             line=dict(color='#F1C40F', dash='dot')), secondary_y=True)

    fig.update_layout(title="2026 滚动供需分析（含预览数据）", hovermode="x unified", height=500)
    fig.update_yaxes(title_text="DOH (天)", secondary_y=True,
                     range=[0, max(target_doh * 3, 120)])
    st.plotly_chart(fig, use_container_width=True)

# -------- Tab 3: 审计日志 --------
with tab_log:
    st.subheader("📋 系统操作历史")
    log_data = load_operation_logs()
    if log_data:
        log_df = pd.DataFrame(log_data)
        log_df['时间'] = pd.to_datetime(log_df['timestamp'], errors='coerce')
        log_df = log_df.sort_values('时间', ascending=False).reset_index(drop=True)

        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            sku_options = ["全部"] + sorted(log_df['sku'].dropna().unique().tolist())
            sku_filter = st.selectbox("按 SKU 筛选", sku_options)
        with col_f2:
            user_options = ["全部"] + sorted(log_df['user'].dropna().unique().tolist())
            user_filter = st.selectbox("按用户筛选", user_options)
        with col_f3:
            page_size = st.selectbox("每页显示", [20, 50, 100], index=0)

        filtered_df = log_df.copy()
        if sku_filter != "全部":
            filtered_df = filtered_df[filtered_df['sku'] == sku_filter]
        if user_filter != "全部":
            filtered_df = filtered_df[filtered_df['user'] == user_filter]

        display_df = filtered_df[['时间', 'user', 'sku', 'action']].copy()
        display_df.columns = ['时间', '用户', 'SKU', '操作内容']

        total_records = len(display_df)
        total_pages = max(1, (total_records - 1) // page_size + 1)
        page = st.number_input("页码", min_value=1, max_value=total_pages, value=1)
        start_idx = (page - 1) * page_size

        st.dataframe(
            display_df.iloc[start_idx:start_idx + page_size],
            use_container_width=True, hide_index=True
        )
        st.caption(f"显示 {start_idx + 1}-{min(start_idx + page_size, total_records)} / 共 {total_records} 条 | 第 {page}/{total_pages} 页")
    else:
        st.info("暂无操作日志记录。")

# -------- Tab 4: AI 智能诊断 --------
with tab_ai:
    st.subheader(f"🤖 {target_sku} Gemini 智能分析大脑")

    current_memory = read_memory_file()
    current_report = load_report(target_sku)

    if 'ai_chat_history' not in st.session_state:
        st.session_state['ai_chat_history'] = []
    if 'tasks_dict' not in st.session_state:
        st.session_state['tasks_dict'] = {}
    if target_sku not in st.session_state['tasks_dict']:
        st.session_state['tasks_dict'][target_sku] = []

    col_ai_left, col_ai_right = st.columns([2, 1])

    with col_ai_right:
        st.markdown("### 🧠 专家大脑配置与对话")

        with st.expander("⚙️ 专家规约管理器", expanded=False):
            st.text_area("当前修正指令", value=current_memory, height=100, disabled=True)
            new_instruction = st.text_area("输入新指令", height=60, placeholder="例如：SKU-A 必须维持至少 50 天库存")
            if st.button("💾 保存规约"):
                if new_instruction:
                    updated_memory = current_memory + f"\n- {new_instruction} ({datetime.now().strftime('%Y-%m-%d')})"
                    save_memory(updated_memory)
                    st.success("规约已更新！")
                    st.rerun()

        st.markdown("---")
        st.markdown("### 💬 专家连续对话")
        chat_container = st.container(height=300)
        for chat in st.session_state['ai_chat_history']:
            with chat_container.chat_message(chat["role"]):
                st.markdown(chat["content"])

        if prompt := st.chat_input("针对刚才的分析提问..."):
            st.session_state['ai_chat_history'].append({"role": "user", "content": prompt})
            with chat_container.chat_message("user"):
                st.markdown(prompt)

            with st.spinner("🤖 专家思考中..."):
                try:
                    import google.generativeai as genai
                    genai.configure(api_key=GEMINI_API_KEY)
                    model = genai.GenerativeModel("gemini-3-flash-preview")

                    context = (
                        f"【当前日期】{datetime.now().strftime('%Y年%m月%d日')}\n"
                        f"【历史修正指令】{current_memory}\n"
                        f"【{target_sku} 当前最新数据(CSV)】\n{sim_df.to_csv(index=False)}"
                    )
                    final_prompt = f"上下文参考：{context}\n\n用户提问：{prompt}\n\n请严格基于上方最新数据和当前日期回答，不要引用任何过去的分析结论。如果用户要求生成任务清单，请用精炼的Markdown复选框形式列出。"
                    response = model.generate_content(final_prompt)

                    st.session_state['ai_chat_history'].append({"role": "assistant", "content": response.text})
                    with chat_container.chat_message("assistant"):
                        st.markdown(response.text)
                except Exception as e:
                    logger.exception(f"AI 对话调用失败: {e}")
                    st.error(f"❌ 对话失败: {e}")

    with col_ai_left:
        st.info(f"✅ 内置配置。当前分析 SKU: **{target_sku}**")
        model_name = st.selectbox("选择模型", ["gemini-3-flash-preview", "gemini-3.1-pro-preview"])

        if st.button("✨ 召唤专家诊断", type="primary"):
            with st.spinner(f"🧠 Gemini 正在进行 {target_sku} 的深度推理..."):
                try:
                    import google.generativeai as genai
                    genai.configure(api_key=GEMINI_API_KEY)
                    model = genai.GenerativeModel(model_name)

                    df_text = sim_df.to_csv(index=False)
                    current_date_str = datetime.now().strftime('%Y年%m月%d日')
                    system_prompt = (
                        f"你是一位资深电商供应链专家。当前日期是 {current_date_str}。"
                        f"请严格且仅基于下方提供的最新数据表进行分析，不要引用或参考任何历史分析结论。"
                        f"已过去的月份（月份 < {today_str}）关注实际销量与计划的偏差，"
                        f"未来月份关注库存风险与补货节奏。"
                        f"请严格遵守以下指令：{current_memory}。"
                    )
                    user_prompt = (
                        f"分析 SKU: {target_sku} 的最新供需数据（CSV格式）：\n{df_text}\n"
                        f"注意：以上数据是截至 {current_date_str} 的最新模拟结果，请据此给出：\n"
                        f"1.风险诊断 2.逻辑推理 3.可执行建议。重点在于当前时间节点下最紧迫的行动项。"
                    )

                    response = model.generate_content([system_prompt, user_prompt])

                    report_content = f"--- 分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n\n{response.text}"
                    save_report(target_sku, report_content)

                    st.session_state['ai_chat_history'] = []
                    st.rerun()
                except Exception as e:
                    logger.exception(f"AI 诊断调用失败: {e}")
                    st.error(f"❌ 调用失败: {e}")

        st.markdown("---")
        st.markdown(f"### 📋 {target_sku} 全局执行任务清单")

        shared_tasks = load_tasks(target_sku)

        with st.expander("➕ 追加任务 (所有人可见)"):
            new_task = st.text_input("新任务描述")
            if st.button("添加"):
                if new_task:
                    shared_tasks.append({"task": new_task, "done": False})
                    save_tasks(target_sku, shared_tasks)
                    st.rerun()

        st.markdown("#### 待办事项")
        if not shared_tasks:
            st.info("暂无任务")
        else:
            for i, task in enumerate(shared_tasks):
                col1, col2 = st.columns([0.8, 0.2])
                with col1:
                    new_done_status = st.checkbox(task["task"], value=task["done"], key=f"task_{target_sku}_{i}")
                    if new_done_status != task["done"]:
                        shared_tasks[i]["done"] = new_done_status
                        save_tasks(target_sku, shared_tasks)
                        st.rerun()
                with col2:
                    if st.button("删除", key=f"del_{target_sku}_{i}"):
                        shared_tasks.pop(i)
                        save_tasks(target_sku, shared_tasks)
                        st.rerun()

        if st.button("🧹 清除已完成任务"):
            shared_tasks = [t for t in shared_tasks if not t["done"]]
            save_tasks(target_sku, shared_tasks)
            st.rerun()

        st.markdown("---")
        st.markdown(f"### 💡 {target_sku} 最新诊断报告")
        if current_report:
            st.markdown(current_report)
            if st.button("🗑️ 清除诊断记录"):
                delete_report(target_sku)
                st.success("已清除")
                st.rerun()
        else:
            st.info(f"点击上方按钮开始诊断 {target_sku}。")
