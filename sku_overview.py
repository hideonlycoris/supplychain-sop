"""
SKU 仪表板模块 - 独立首页，显示所有SKU的摘要信息和AI诊断结果
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import google.generativeai as genai


def get_risk_color(risk_level: str) -> str:
    """根据风险等级返回颜色"""
    colors = {
        'high': '#f8d7da',   # 红色
        'medium': '#fff3cd', # 黄色
        'low': '#d4edda',    # 绿色
        'normal': '#ffffff'  # 白色
    }
    return colors.get(risk_level, '#ffffff')


def get_risk_label(risk_level: str) -> str:
    """根据风险等级返回标签"""
    labels = {
        'high': '🔴 高风险',
        'medium': '🟡 中风险',
        'low': '🟢 低风险',
        'normal': '⚪ 正常'
    }
    return labels.get(risk_level, '⚪ 未知')


def calculate_sku_metrics(sku_name: str, sku_data: dict) -> dict:
    """
    计算单个SKU的关键指标 - 使用与app.py相同的模拟逻辑
    """
    import pandas as pd
    from datetime import datetime, timedelta

    config = sku_data.get("config", {})
    dept_plans = sku_data.get("dept_plans", {})
    shipments = sku_data.get("shipments", {})
    actual_sales = sku_data.get("actual_sales", {})

    # 关键参数
    init_inv = config.get("init_inv", 0)
    target_doh = config.get("target_doh", 30)
    lt_months = config.get("lt", 2)

    # 当前月份
    today = datetime.now()
    today_str = today.strftime('%Y-%m')

    # 模拟计算（与app.py相同的逻辑）
    start_date = datetime(today.year, 1, 1)
    f_dates = pd.date_range(start=start_date, periods=12, freq='MS')

    sim_res = []
    curr_inv = float(init_inv)
    cumulative_plan = 0
    cumulative_actual = 0

    for i, d in enumerate(f_dates):
        ds = d.strftime('%Y-%m')
        actual_total = sum(actual_sales.get(ds, {}).values())
        plan_total = sum(dept_plans.get(ds, {}).values())

        if i >= lt_months:
            ship_month = f_dates[i - lt_months].strftime('%Y-%m')
            arr = shipments.get(ship_month, 0)
        else:
            arr = 0

        if ds < today_str:
            # 过去月份：使用实际销量
            demand_to_use = actual_total
            cumulative_plan += plan_total
            cumulative_actual += actual_total
        elif ds == today_str:
            # 当前月份：如果有实际销量用实际，否则用计划
            if actual_total > 0:
                demand_to_use = actual_total
            else:
                shortfall = max(0, cumulative_plan - cumulative_actual)
                demand_to_use = plan_total + shortfall
            cumulative_plan = 0
            cumulative_actual = 0
        else:
            # 未来月份：直接使用计划预测
            demand_to_use = plan_total

        curr_inv = curr_inv + arr - demand_to_use

        in_transit = sum([
            shipments.get(f_dates[i - j].strftime('%Y-%m'), 0)
            for j in range(lt_months) if i - j >= 0
        ])

        next_dem = sum(dept_plans.get(f_dates[min(i + 1, 11)].strftime('%Y-%m'), {}).values())
        if next_dem > 0:
            effective_inv = max(0, curr_inv)
            doh = round(effective_inv / (next_dem / 30), 1)
        else:
            doh = 999.0 if curr_inv > 0 else 0.0

        sim_res.append({
            "月份": ds,
            "期末在仓": int(curr_inv),
            "期末在途": int(in_transit),
            "全口径库存": int(curr_inv + in_transit),
            "DOH": doh
        })

        curr_inv = max(0, curr_inv)

    # 获取当前月份的模拟结果
    current_month_idx = today.month - 1
    if current_month_idx < len(sim_res):
        current_sim = sim_res[current_month_idx]
        current_inv = current_sim["期末在仓"]
        doh = current_sim["DOH"]
    else:
        current_inv = init_inv
        doh = 0.0

    # 计算在途库存
    in_transit = current_sim.get("期末在途", 0) if current_month_idx < len(sim_res) else 0

    # 判断风险等级
    if current_inv < 0:
        risk_level = 'high'
    elif doh < target_doh * 0.5:
        risk_level = 'high'
    elif doh < target_doh:
        risk_level = 'medium'
    elif doh > target_doh * 2:
        risk_level = 'medium'  # 库存过高也是风险
    else:
        risk_level = 'low'

    return {
        'sku_name': sku_name,
        'current_inv': current_inv,
        'in_transit': in_transit,
        'total_inventory': current_inv + in_transit,
        'target_doh': target_doh,
        'doh': doh,
        'risk_level': risk_level,
        'price': config.get('price', 0),
        'inventory_value': (current_inv + in_transit) * config.get('price', 0)
    }


def run_ai_diagnosis(sku_name: str, sku_data: dict, api_key: str, model_name: str = "gemini-3-flash-preview") -> dict:
    """对单个SKU运行AI诊断"""
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)

        # 构建数据摘要
        config = sku_data.get("config", {})
        dept_plans = sku_data.get("dept_plans", {})
        shipments = sku_data.get("shipments", {})

        data_summary = f"""
SKU: {sku_name}
期初库存: {config.get('init_inv', 0)}
目标DOH: {config.get('target_doh', 30)}
物流时效: {config.get('lt', 2)} 月
发货计划: {shipments}
部门计划: {dept_plans}
"""

        prompt = f"""你是供应链专家，请分析以下SKU数据并给出风险诊断。

{data_summary}

请按以下格式返回JSON:
{{
    "risk_level": "high/medium/low",
    "risk_summary": "一句话风险摘要",
    "action_items": ["建议1", "建议2"]
}}"""

        response = model.generate_content(prompt)
        result = response.text

        # 尝试解析JSON
        import json
        try:
            # 移除可能的markdown代码块标记
            clean_result = result.replace('```json', '').replace('```', '').strip()
            parsed = json.loads(clean_result)
            return {
                'risk_level': parsed.get('risk_level', 'normal'),
                'risk_summary': parsed.get('risk_summary', ''),
                'action_items': parsed.get('action_items', [])
            }
        except json.JSONDecodeError:
            # 如果解析失败，返回默认值
            return {
                'risk_level': 'normal',
                'risk_summary': result[:100] if result else '诊断完成',
                'action_items': []
            }

    except Exception as e:
        return {
            'risk_level': 'normal',
            'risk_summary': f'诊断异常: {str(e)[:50]}',
            'action_items': []
        }


def load_diagnosis_cache(supabase_client) -> dict:
    """从数据库加载诊断结果缓存"""
    try:
        result = supabase_client.table("sku_reports").select("*").execute()
        cache = {}
        for row in result.data:
            cache[row['sku_name']] = {
                'risk_level': row.get('risk_level', ''),
                'risk_summary': row.get('content', '')[:200] if row.get('content') else '',
                'updated_at': row.get('updated_at', '')
            }
        return cache
    except Exception as e:
        return {}


def run_batch_diagnosis(full_db: dict, supabase_client, api_key: str, current_user: str):
    """批量AI诊断所有SKU"""
    if not api_key:
        st.error("❌ 未配置 Gemini API Key")
        return

    progress_bar = st.progress(0)
    status_text = st.empty()

    total = len(full_db)
    for idx, (sku_name, sku_data) in enumerate(full_db.items()):
        status_text.text(f"正在诊断: {sku_name} ({idx + 1}/{total})")
        progress_bar.progress((idx + 1) / total)

        # 运行AI诊断
        result = run_ai_diagnosis(sku_name, sku_data, api_key)

        # 保存到数据库
        try:
            supabase_client.table("sku_reports").upsert({
                "sku_name": sku_name,
                "department": current_user,
                "report_type": "ai_diagnosis",
                "content": result.get('risk_summary', ''),
                "risk_level": result.get('risk_level', 'normal'),
                "updated_at": datetime.now().isoformat()
            }).execute()
        except Exception as e:
            st.warning(f"保存 {sku_name} 诊断结果失败: {e}")

    status_text.text("✅ 批量诊断完成！")
    st.rerun()


def render_dashboard(full_db: dict, supabase_client, api_key: str, current_user: str, is_admin: bool):
    """渲染独立的仪表板首页"""
    # 页面标题
    st.markdown("""
    <style>
    .dashboard-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 10px;
        color: white;
        margin-bottom: 20px;
    }
    .metric-card {
        background: white;
        padding: 15px;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        text-align: center;
    }
    .risk-high { border-left: 4px solid #dc3545; }
    .risk-medium { border-left: 4px solid #ffc107; }
    .risk-low { border-left: 4px solid #28a745; }
    </style>
    """, unsafe_allow_html=True)

    # 顶部标题栏
    st.markdown("""
    <div class="dashboard-header">
        <h1 style="margin:0; color:white;">🚢 供应链 S&OP 仪表板</h1>
        <p style="margin:5px 0 0 0; color:rgba(255,255,255,0.8);">实时监控所有SKU的库存风险与供需状态</p>
    </div>
    """, unsafe_allow_html=True)

    # 操作栏
    col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
    with col1:
        st.info(f"👤 **{current_user}** | {'管理员' if is_admin else '部门用户'}")
    with col2:
        if st.button("🔍 一键诊断所有SKU", type="primary", use_container_width=True):
            run_batch_diagnosis(full_db, supabase_client, api_key, current_user)
    with col3:
        if st.button("🔄 刷新数据", use_container_width=True):
            st.rerun()
    with col4:
        if st.button("➕ 新建SKU", use_container_width=True):
            st.session_state.page = 'sku_detail'
            st.rerun()

    st.markdown("---")

    # 加载诊断结果
    diagnosis_cache = load_diagnosis_cache(supabase_client)

    # 构建总表数据
    overview_data = []
    for sku_name, sku_data in full_db.items():
        metrics = calculate_sku_metrics(sku_name, sku_data)

        # 获取诊断结果
        diagnosis = diagnosis_cache.get(sku_name, {})
        last_diagnosis_time = diagnosis.get('updated_at', '')
        risk_from_ai = diagnosis.get('risk_level', '')
        risk_summary = diagnosis.get('risk_summary', '')

        # 如果有新的AI诊断结果，使用它；否则使用计算的风险
        final_risk = risk_from_ai if risk_from_ai else metrics['risk_level']

        overview_data.append({
            'sku_name': sku_name,
            'current_inv': metrics['current_inv'],
            'in_transit': metrics['in_transit'],
            'total_inventory': metrics['total_inventory'],
            'target_doh': metrics['target_doh'],
            'doh': metrics['doh'],
            'risk_level': final_risk,
            'risk_summary': risk_summary,
            'last_diagnosis': last_diagnosis_time,
            'inventory_value': metrics['inventory_value']
        })

    if not overview_data:
        st.info("📦 暂无SKU数据，请点击「➕ 新建SKU」创建。")
        return

    # 转换为DataFrame
    df = pd.DataFrame(overview_data)

    # 核心指标卡片
    st.markdown("### 📊 核心指标")
    metric_cols = st.columns(5)
    with metric_cols[0]:
        st.metric("📦 SKU总数", len(df))
    with metric_cols[1]:
        high_risk = len(df[df['risk_level'] == 'high'])
        st.metric("🔴 高风险", high_risk, delta=f"需立即处理" if high_risk > 0 else None, delta_color="inverse" if high_risk > 0 else "off")
    with metric_cols[2]:
        medium_risk = len(df[df['risk_level'] == 'medium'])
        st.metric("🟡 中风险", medium_risk)
    with metric_cols[3]:
        low_risk = len(df[df['risk_level'] == 'low'])
        st.metric("🟢 正常", low_risk)
    with metric_cols[4]:
        total_value = df['inventory_value'].sum()
        st.metric("💰 库存总值", f"${total_value:,.0f}")

    st.markdown("---")

    # SKU 风险卡片网格
    st.markdown("### 🎯 SKU 风险总览")

    # 按风险等级排序（高风险优先）
    risk_order = {'high': 0, 'medium': 1, 'low': 2, 'normal': 3}
    df['risk_sort'] = df['risk_level'].map(risk_order)
    df = df.sort_values('risk_sort').drop('risk_sort', axis=1)

    # 使用网格布局显示SKU卡片
    cols_per_row = 3
    for i in range(0, len(df), cols_per_row):
        cols = st.columns(cols_per_row)
        for j, col in enumerate(cols):
            if i + j < len(df):
                row = df.iloc[i + j]
                with col:
                    risk_color = get_risk_color(row['risk_level'])
                    risk_label = get_risk_label(row['risk_level'])

                    # SKU卡片
                    st.markdown(f"""
                    <div style="border-left: 4px solid {risk_color}; background: white; padding: 15px; border-radius: 8px; margin-bottom: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <h3 style="margin: 0; font-size: 16px;">{row['sku_name']}</h3>
                            <span style="font-size: 12px;">{risk_label}</span>
                        </div>
                        <div style="margin-top: 10px;">
                            <div style="display: flex; justify-content: space-between; font-size: 13px; color: #666;">
                                <span>在仓: <b>{row['current_inv']:,.0f}</b></span>
                                <span>在途: <b>{row['in_transit']:,.0f}</b></span>
                            </div>
                            <div style="display: flex; justify-content: space-between; font-size: 13px; color: #666; margin-top: 5px;">
                                <span>全口径: <b>{row['total_inventory']:,.0f}</b></span>
                                <span>DOH: <b>{row['doh']:.1f}</b></span>
                            </div>
                            <div style="font-size: 12px; color: #999; margin-top: 5px;">
                                目标DOH: {row['target_doh']} | 库存值: ${row['inventory_value']:,.0f}
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    # 详情按钮
                    if st.button("查看详情 →", key=f"goto_{row['sku_name']}", use_container_width=True):
                        st.session_state.selected_sku = row['sku_name']
                        st.session_state.page = 'sku_detail'
                        st.rerun()

    st.markdown("---")

    # 风险摘要（如果有AI诊断结果）
    risk_items = df[df['risk_level'].isin(['high', 'medium'])]
    if not risk_items.empty:
        st.markdown("### ⚠️ 需要关注的SKU")
        for _, row in risk_items.iterrows():
            risk_label = get_risk_label(row['risk_level'])
            with st.expander(f"{risk_label} {row['sku_name']} - {row['risk_summary'][:50]}..." if row['risk_summary'] else f"{risk_label} {row['sku_name']}"):
                st.write(f"**在仓库存:** {row['current_inv']:,.0f} PCS")
                st.write(f"**在途库存:** {row['in_transit']:,.0f} PCS")
                st.write(f"**全口径库存:** {row['total_inventory']:,.0f} PCS")
                st.write(f"**DOH:** {row['doh']:.1f} 天 (目标: {row['target_doh']} 天)")
                if row['risk_summary']:
                    st.write(f"**诊断摘要:** {row['risk_summary']}")
                if st.button("进入详情 →", key=f"detail_{row['sku_name']}"):
                    st.session_state.selected_sku = row['sku_name']
                    st.session_state.page = 'sku_detail'
                    st.rerun()
