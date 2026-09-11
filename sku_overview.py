"""
SKU 仪表板模块 - 独立首页，显示所有SKU的摘要信息和AI诊断结果
"""
import streamlit as st
import pandas as pd
import json
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
                demand_to_use = plan_total
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

    # 判断风险等级和风险说明
    risk_reason = ""
    risk_suggestion = ""

    # 计算下月预测销量（用于建议补货量）
    next_month_idx = min(today.month, 11)  # 下个月的索引
    next_month_str = f_dates[next_month_idx].strftime('%Y-%m')
    next_month_demand = sum(dept_plans.get(next_month_str, {}).values())

    # 目标库存 = 目标DOH * 月均销量 / 30
    if next_month_demand > 0:
        target_inventory = int(target_doh * next_month_demand / 30)
    else:
        target_inventory = current_inv + in_transit  # 无销量时保持当前库存

    # 全口径库存（在仓 + 在途）
    total_inv = current_inv + in_transit

    if current_inv < 0:
        risk_level = 'high'
        risk_reason = "库存已为负数，严重缺货"
        risk_suggestion = f"⚠️ 立即补货！建议补货量：{target_inventory - total_inv}个"
    elif doh < target_doh * 0.5:
        risk_level = 'high'
        risk_reason = f"库存天数({doh}天)严重不足，低于目标的50%"
        shortage = target_inventory - total_inv
        risk_suggestion = f"⚠️ 紧急补货！建议补货量：{shortage}个，达到目标DOH {target_doh}天"
    elif doh < target_doh:
        risk_level = 'medium'
        risk_reason = f"库存天数({doh}天)偏低，未达到目标"
        shortage = target_inventory - total_inv
        risk_suggestion = f"💡 建议补货：{shortage}个，达到目标DOH {target_doh}天"
    elif doh > target_doh * 2:
        risk_level = 'medium'
        risk_reason = f"库存天数({doh}天)过高，超过目标的2倍"
        excess = total_inv - target_inventory
        risk_suggestion = f"📉 库存过剩，建议减少采购或促销清理，过剩量：{excess}个"
    else:
        risk_level = 'low'
        risk_reason = f"库存天数({doh}天)处于合理范围"
        risk_suggestion = "✅ 库存健康，保持当前采购节奏"

    return {
        'sku_name': sku_name,
        'current_inv': current_inv,
        'in_transit': in_transit,
        'total_inventory': total_inv,
        'target_doh': target_doh,
        'doh': doh,
        'risk_level': risk_level,
        'risk_reason': risk_reason,
        'risk_suggestion': risk_suggestion,
        'price': config.get('price', 0),
        'inventory_value': total_inv * config.get('price', 0)
    }


def update_sku_target_doh(supabase_client, full_db: dict, sku_name: str, new_target_doh: int):
    """更新SKU的目标DOH"""
    if sku_name in full_db:
        # 更新内存中的数据
        full_db[sku_name]['config']['target_doh'] = new_target_doh

        # 保存到数据库
        try:
            supabase_client.table("sku_data").update({
                "data": json.dumps(full_db[sku_name], ensure_ascii=False),
                "updated_at": datetime.now().isoformat()
            }).eq("sku_name", sku_name).execute()
            # 清除缓存，确保下次加载时重新计算
            if 'full_db' in st.session_state:
                del st.session_state['full_db']
        except Exception as e:
            st.error(f"保存失败: {e}")


def run_ai_diagnosis(sku_name: str, sku_data: dict, api_key: str, model_name: str = "mimo-v2.5") -> dict:
    """对单个SKU运行AI诊断 - 使用MiMo v2.5模型"""
    import requests

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

    print(f"[AI DEBUG] {sku_name} 开始调用API, api_key长度: {len(api_key) if api_key else 0}")

    try:
        # 使用MiMo v2.5 API (OpenAI兼容格式)
        response = requests.post(
            "https://token-plan-sgp.xiaomimimo.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": model_name,
                "messages": [
                    {"role": "system", "content": "你是供应链专家，擅长分析库存风险。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 500
            },
            timeout=60
        )

        print(f"[AI DEBUG] {sku_name} API响应状态: {response.status_code}")

        if response.status_code != 200:
            print(f"[AI DEBUG] {sku_name} API错误: {response.text[:300]}")
            return {
                'risk_level': 'medium',
                'risk_summary': f'API错误: {response.status_code} - {response.text[:100]}',
                'action_items': []
            }

        result_json = response.json()
        print(f"[AI DEBUG] {sku_name} API返回: {str(result_json)[:300]}")

        if 'choices' not in result_json or not result_json['choices']:
            print(f"[AI DEBUG] {sku_name} API返回无choices字段")
            return {
                'risk_level': 'medium',
                'risk_summary': 'API返回格式错误',
                'action_items': []
            }

        result = result_json['choices'][0]['message']['content']
        print(f"[AI DEBUG] {sku_name} 原始返回: {result[:300]}")

        # 尝试解析JSON
        import json
        try:
            # 移除可能的markdown代码块标记
            clean_result = result.replace('```json', '').replace('```', '').strip()
            parsed = json.loads(clean_result)
            risk_level = parsed.get('risk_level', '').lower()
            # 确保返回有效的风险等级
            if risk_level not in ['high', 'medium', 'low']:
                risk_level = 'medium'
            return {
                'risk_level': risk_level,
                'risk_summary': parsed.get('risk_summary', ''),
                'action_items': parsed.get('action_items', [])
            }
        except json.JSONDecodeError as je:
            print(f"[AI DEBUG] {sku_name} JSON解析失败: {je}")
            # 尝试从文本中提取风险等级
            result_lower = result.lower()
            if 'high' in result_lower or '高风险' in result:
                risk_level = 'high'
            elif 'medium' in result_lower or '中风险' in result:
                risk_level = 'medium'
            elif 'low' in result_lower or '低风险' in result:
                risk_level = 'low'
            else:
                risk_level = 'medium'
            return {
                'risk_level': risk_level,
                'risk_summary': result[:200] if result else '诊断完成',
                'action_items': []
            }

    except Exception as e:
        print(f"[AI DEBUG] {sku_name} 诊断异常: {e}")
        return {
            'risk_level': 'medium',
            'risk_summary': f'诊断异常: {str(e)[:100]}',
            'action_items': []
        }


def clean_html_tags(text):
    """清理HTML标签"""
    import re
    # 移除HTML标签
    clean = re.sub(r'<[^>]+>', '', text)
    # 移除多余空格
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip()


def load_diagnosis_cache(supabase_client) -> dict:
    """从 ai_reports 表加载各SKU详情页的AI分析结果"""
    try:
        result = supabase_client.table("ai_reports").select("*").execute()
        cache = {}
        for row in result.data:
            sku_name = row.get('sku_name', '')
            content = row.get('content', '')

            # 先清理HTML标签
            content = clean_html_tags(content)

            # 检查内容是否有效（不是空的或默认的"诊断完成"）
            if not content or content.strip() == '' or '诊断完成' in content[:50]:
                continue

            # 清理markdown格式，提取有意义的内容
            summary = content.replace('#', '').replace('**', '').replace('---', '').strip()
            # 找到有意义的内容开始位置
            lines = summary.split('\n')
            meaningful_lines = []
            skip_keywords = ['AI风险分析报告', '行动建议:', '暂无', '</div>', '</div>', '分析时间:']
            for line in lines:
                line = line.strip()
                if line and not any(kw in line for kw in skip_keywords):
                    meaningful_lines.append(line)
                if len(meaningful_lines) >= 5:  # 取前5行有意义的内容
                    break
            summary = ' '.join(meaningful_lines)[:300] + '...' if len(' '.join(meaningful_lines)) > 300 else ' '.join(meaningful_lines)

            if summary:  # 只有有内容时才加入缓存
                cache[sku_name] = {
                    'risk_summary': summary,
                    'updated_at': row.get('updated_at', '')
                }
        return cache
    except Exception as e:
        return {}


def run_batch_diagnosis(full_db: dict, supabase_client, api_key: str, current_user: str):
    """批量AI诊断所有SKU，保存到ai_reports表"""
    print(f"[AI DEBUG] API Key 长度: {len(api_key) if api_key else 0}")
    if not api_key:
        st.error("❌ 未配置 AI API Key (请在 Secrets 中添加 MIMO_API_KEY)")
        return

    progress_bar = st.progress(0)
    status_text = st.empty()
    success_count = 0
    fail_count = 0

    total = len(full_db)
    for idx, (sku_name, sku_data) in enumerate(full_db.items()):
        status_text.text(f"正在分析: {sku_name} ({idx + 1}/{total})")
        progress_bar.progress((idx + 1) / total)

        # 运行AI诊断
        result = run_ai_diagnosis(sku_name, sku_data, api_key)
        print(f"[AI DEBUG] {sku_name} 诊断结果: {result}")

        # 检查结果是否有效
        if result.get('risk_summary') and result['risk_summary'] != '诊断完成':
            success_count += 1
        else:
            fail_count += 1

        # 构建报告内容
        report_content = f"""## AI风险分析报告

**风险等级:** {result.get('risk_level', 'unknown')}

**风险摘要:** {result.get('risk_summary', '暂无')}

**行动建议:**
{chr(10).join('- ' + item for item in result.get('action_items', [])) if result.get('action_items') else '- 暂无'}
"""
        try:
            supabase_client.table("ai_reports").upsert({
                "sku_name": sku_name,
                "content": report_content,
                "updated_at": datetime.now().isoformat()
            }).execute()
            print(f"[AI DEBUG] {sku_name} 保存成功")
        except Exception as e:
            print(f"[AI DEBUG] {sku_name} 保存失败: {e}")
            st.warning(f"保存 {sku_name} 分析结果失败: {e}")

    status_text.text(f"✅ 批量AI分析完成！成功: {success_count}, 失败: {fail_count}")
    st.rerun()


def render_dashboard(full_db: dict, supabase_client, api_key: str, current_user: str, is_admin: bool):
    """渲染独立的仪表板首页"""
    # 初始化session_state
    if 'show_batch_edit' not in st.session_state:
        st.session_state.show_batch_edit = False

    # 重新加载数据，确保风险等级是最新的
    try:
        result = supabase_client.table("sku_data").select("*").execute()
        full_db.clear()
        for row in result.data:
            full_db[row["sku_name"]] = json.loads(row["data"])
    except Exception as e:
        st.warning(f"重新加载数据失败: {e}")

    # 页面标题
    st.markdown("""
    <style>
    .stApp {
        background-color: #f5f6fa;
    }
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
    col1, col2, col3 = st.columns([3, 2, 1])
    with col1:
        st.info(f"👤 **{current_user}** | {'管理员' if is_admin else '部门用户'}")
    with col2:
        if st.button("🔄 刷新数据", use_container_width=True):
            st.rerun()
    with col3:
        if st.button("➕ 新建SKU", use_container_width=True):
            st.session_state.page = 'sku_detail'
            st.rerun()

    st.markdown("---")

    # 加载各SKU详情页的AI分析结果
    diagnosis_cache = load_diagnosis_cache(supabase_client)

    # 构建总表数据
    overview_data = []
    for sku_name, sku_data in full_db.items():
        metrics = calculate_sku_metrics(sku_name, sku_data)

        # 获取该SKU的AI分析摘要
        diagnosis = diagnosis_cache.get(sku_name, {})
        risk_summary = diagnosis.get('risk_summary', '')
        last_diagnosis_time = diagnosis.get('updated_at', '')

        overview_data.append({
            'sku_name': sku_name,
            'current_inv': metrics['current_inv'],
            'in_transit': metrics['in_transit'],
            'total_inventory': metrics['total_inventory'],
            'target_doh': metrics['target_doh'],
            'doh': metrics['doh'],
            'risk_level': metrics['risk_level'],  # 使用计算的风险等级
            'risk_reason': metrics['risk_reason'],
            'risk_suggestion': metrics['risk_suggestion'],
            'risk_summary': risk_summary,  # 显示详情页的AI分析摘要
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

    # 批量设置按钮
    col_header1, col_header2 = st.columns([3, 1])
    with col_header2:
        if st.button("⚙️ 批量设置目标DOH", use_container_width=True):
            st.session_state.show_batch_edit = True

    # 批量设置弹窗
    if st.session_state.get('show_batch_edit', False):
        with st.expander("⚙️ 批量设置目标DOH", expanded=True):
            st.info("修改后点击保存，所有变更将立即生效。")

            # 构建编辑表格
            edit_data = []
            for _, row in df.iterrows():
                edit_data.append({
                    'sku_name': row['sku_name'],
                    '当前目标DOH': row['target_doh'],
                    '新目标DOH': row['target_doh']
                })

            edit_df = pd.DataFrame(edit_data)

            # 使用data_editor编辑
            edited_df = st.data_editor(
                edit_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "sku_name": st.column_config.TextColumn("SKU名称", disabled=True),
                    "当前目标DOH": st.column_config.NumberColumn("当前目标DOH", disabled=True),
                    "新目标DOH": st.column_config.NumberColumn("新目标DOH", min_value=1, max_value=365)
                },
                key="batch_target_doh_editor"
            )

            col_save, col_cancel = st.columns(2)
            with col_save:
                if st.button("💾 保存所有修改", type="primary", use_container_width=True):
                    # 获取编辑器中的修改
                    if 'batch_target_doh_editor' in st.session_state:
                        edited_rows = st.session_state['batch_target_doh_editor'].get('edited_rows', {})
                        for row_idx, changes in edited_rows.items():
                            if '新目标DOH' in changes:
                                sku_name = edit_df.iloc[int(row_idx)]['sku_name']
                                new_target_doh = int(changes['新目标DOH'])
                                update_sku_target_doh(supabase_client, full_db, sku_name, new_target_doh)
                    st.session_state.show_batch_edit = False
                    st.success("✅ 批量设置已保存！")
                    st.rerun()

            with col_cancel:
                if st.button("❌ 取消", use_container_width=True):
                    st.session_state.show_batch_edit = False
                    st.rerun()

    # 按库存值从高到低排序
    df = df.sort_values('inventory_value', ascending=False)

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
                    <div style="border-left: 4px solid {risk_color}; background: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.08);">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <h3 style="margin: 0; font-size: 16px;">{row['sku_name']}</h3>
                            <span style="font-size: 13px; font-weight: 600;">{risk_label}</span>
                        </div>
                        <div style="margin-top: 10px;">
                            <div style="display: flex; justify-content: space-between; font-size: 14px; color: #333;">
                                <span>在仓: <b>{row['current_inv']:,.0f}</b></span>
                                <span>在途: <b>{row['in_transit']:,.0f}</b></span>
                            </div>
                            <div style="display: flex; justify-content: space-between; font-size: 14px; color: #333; margin-top: 5px;">
                                <span>全口径: <b>{row['total_inventory']:,.0f}</b></span>
                                <span>DOH: <b>{row['doh']:.1f}</b></span>
                            </div>
                            <div style="margin-top: 10px; padding: 10px; background: white; border-radius: 6px; border: 1px solid #e9ecef;">
                                <div style="font-size: 13px; color: #495057; margin-bottom: 6px;">{row['risk_reason']}</div>
                                <div style="font-size: 14px; color: #c0392b; font-weight: 600;">{row['risk_suggestion']}</div>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    # AI分析摘要（如果有）- 使用expander显示完整内容
                    if row['risk_summary']:
                        with st.expander("📋 AI分析摘要", expanded=False):
                            st.write(row['risk_summary'])

                    # 目标DOH编辑区
                    target_doh_key = f"target_doh_{row['sku_name']}"
                    if target_doh_key not in st.session_state:
                        st.session_state[target_doh_key] = row['target_doh']

                    target_doh_col1, target_doh_col2 = st.columns([3, 1])
                    with target_doh_col1:
                        new_target_doh = st.number_input(
                            "目标DOH",
                            value=max(1, int(row['target_doh'])),
                            min_value=1,
                            max_value=365,
                            key=f"input_{target_doh_key}",
                            label_visibility="collapsed"
                        )
                    with target_doh_col2:
                        if st.button("✏️", key=f"edit_{target_doh_key}", help="保存修改"):
                            if new_target_doh != int(row['target_doh']):
                                update_sku_target_doh(supabase_client, full_db, row['sku_name'], int(new_target_doh))
                                st.success(f"✅ {row['sku_name']} 目标DOH已更新为 {new_target_doh}")
                                st.rerun()

                    # 库存值
                    st.caption(f"库存值: ${row['inventory_value']:,.0f}")

                    # 详情按钮
                    if st.button("查看详情 →", key=f"goto_{row['sku_name']}", use_container_width=True):
                        st.session_state.selected_sku = row['sku_name']
                        st.session_state.page = 'sku_detail'
                        st.rerun()
