"""
SKU 总览模块 - 显示所有SKU的摘要信息和AI诊断结果
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
    """计算单个SKU的关键指标"""
    config = sku_data.get("config", {})
    dept_plans = sku_data.get("dept_plans", {})
    shipments = sku_data.get("shipments", {})
    actual_sales = sku_data.get("actual_sales", {})

    # 获取当前月份
    today = datetime.now()
    current_month = today.strftime('%Y-%m')

    # 计算当前库存（简化版：期初 + 累计到货 - 累计销量）
    init_inv = config.get("init_inv", 0)
    target_doh = config.get("target_doh", 30)

    # 计算累计发货和销量
    total_shipments = sum(shipments.values())
    total_plans = sum(dept_plans.get(m, {}).get(d, 0)
                      for m in dept_plans
                      for d in dept_plans[m])
    total_actual = sum(actual_sales.get(m, {}).get(d, 0)
                       for m in actual_sales
                       for d in actual_sales[m])

    # 当前库存（简化计算）
    current_inv = init_inv + total_shipments - total_plans

    # 计算DOH（简化版）
    next_month = (today + timedelta(days=32)).strftime('%Y-%m')
    next_month_plan = sum(dept_plans.get(next_month, {}).values())
    if next_month_plan > 0:
        doh = round(current_inv / (next_month_plan / 30), 1)
    else:
        doh = 999.0 if current_inv > 0 else 0.0

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
        'target_doh': target_doh,
        'doh': doh,
        'risk_level': risk_level,
        'total_shipments': total_shipments,
        'total_plans': total_plans,
        'total_actual': total_actual,
        'price': config.get('price', 0),
        'inventory_value': current_inv * config.get('price', 0)
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
        st.error(f"AI诊断失败: {e}")
        return {
            'risk_level': 'normal',
            'risk_summary': f'诊断异常: {str(e)[:50]}',
            'action_items': []
        }


def render_overview_tab(full_db: dict, supabase_client, api_key: str, current_user: str, is_admin: bool):
    """渲染SKU总览Tab"""
    st.subheader("📊 SKU 总览与风险诊断")

    # 顶部操作栏
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        st.info(f"👤 当前用户: **{current_user}** | {'管理员模式' if is_admin else '部门模式'}")
    with col2:
        if st.button("🔍 一键诊断所有SKU", type="primary"):
            run_batch_diagnosis(full_db, supabase_client, api_key, current_user)
    with col3:
        if st.button("🔄 刷新数据"):
            st.rerun()

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
            'target_doh': metrics['target_doh'],
            'doh': metrics['doh'],
            'risk_level': final_risk,
            'risk_summary': risk_summary,
            'last_diagnosis': last_diagnosis_time,
            'inventory_value': metrics['inventory_value']
        })

    if not overview_data:
        st.info("暂无SKU数据，请先创建SKU。")
        return

    # 转换为DataFrame
    df = pd.DataFrame(overview_data)

    # 显示统计卡片
    st.markdown("---")
    metric_cols = st.columns(4)
    with metric_cols[0]:
        st.metric("📦 SKU总数", len(df))
    with metric_cols[1]:
        high_risk = len(df[df['risk_level'] == 'high'])
        st.metric("🔴 高风险", high_risk, delta=None if high_risk == 0 else f"{high_risk}个需关注")
    with metric_cols[2]:
        medium_risk = len(df[df['risk_level'] == 'medium'])
        st.metric("🟡 中风险", medium_risk)
    with metric_cols[3]:
        total_value = df['inventory_value'].sum()
        st.metric("💰 库存总值", f"${total_value:,.0f}")

    st.markdown("---")

    # 渲染总表
    st.markdown("### 📋 SKU 风险总表")

    # 样式化显示
    for idx, row in df.iterrows():
        risk_color = get_risk_color(row['risk_level'])
        risk_label = get_risk_label(row['risk_level'])

        with st.container():
            col_a, col_b, col_c, col_d, col_e = st.columns([2, 1, 1, 1, 1])

            with col_a:
                st.markdown(f"**{row['sku_name']}**")

            with col_b:
                inv_color = "normal" if row['current_inv'] >= 0 else "inverse"
                st.metric("库存", f"{row['current_inv']:,.0f}", delta=None)

            with col_c:
                st.metric("DOH", f"{row['doh']:.1f}", delta=None)

            with col_d:
                st.markdown(f"**{risk_label}**")

            with col_e:
                if st.button("查看详情", key=f"detail_{row['sku_name']}"):
                    st.session_state['selected_sku'] = row['sku_name']
                    st.rerun()

            # 如果有风险摘要，显示出来
            if row['risk_summary']:
                st.caption(f"📝 {row['risk_summary'][:100]}...")

            st.divider()


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
        st.warning(f"加载诊断缓存失败: {e}")
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
