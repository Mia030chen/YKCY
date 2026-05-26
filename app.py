import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# 初始化数据库
def init_db():
    conn = sqlite3.connect('air_freight.db')
    cursor = conn.cursor()
    # 航线成本表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS routes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            route_name TEXT UNIQUE,
            unit_cost REAL,
            origin_fee REAL,
            transit_fee REAL
        )
    ''')
    # 订单表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            awb_no TEXT,
            route_name TEXT,
            customer_name TEXT,
            length REAL, width REAL, height REAL,
            pieces INTEGER,
            gross_weight REAL,
            chargeable_weight REAL,
            customs_type TEXT,
            freight_cost REAL,
            handling_cost REAL,
            total_cost REAL,
            payment_status TEXT,
            file_name TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# 数据库辅助函数
def run_query(sql, params=()):
    with sqlite3.connect('air_freight.db') as conn:
        return pd.read_sql_query(sql, conn, params=params)

def run_cmd(sql, params=()):
    with sqlite3.connect('air_freight.db') as conn:
        conn.execute(sql, params)
        conn.commit()

# --- 页面配置 ---
st.set_page_config(page_title="空运报价及订单查询系统", layout="wide")
st.title("✈️ 空运报价及订单协同系统")

# 模拟登录/角色切换（实际项目可扩展为密码登录）
role = st.sidebar.selectbox("切换当前操作角色", ["操作员 (Operator)", "管理员 (Admin)"])
st.sidebar.markdown("---")

# ==========================================
# 1. 管理员界面
# ==========================================
if "Admin" in role:
    st.header("⚙️ 管理员控制台")
    tab1, tab2 = st.tabs(["航线与操作费管理", "账单模板与账号"])

    with tab1:
        st.subheader("新增/修改每周航线及成本")
        with st.form("route_form", clear_on_submit=True):
            route_name = st.text_input("航线名称 (例如: CAN-PTY-CCS)")
            unit_cost = st.number_input("单位运费成本 (元/kg)", min_value=0.0, step=0.1)
            origin_fee = st.number_input("起始站操作费明细 (元)", min_value=0.0, step=10.0)
            transit_fee = st.number_input("中转站操作费明细 (元)", min_value=0.0, step=10.0)
            submit_route = st.form_submit_button("保存航线信息")
            
            if submit_route and route_name:
                try:
                    run_cmd("""
                        INSERT INTO routes (route_name, unit_cost, origin_fee, transit_fee) 
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(route_name) DO UPDATE SET 
                        unit_cost=excluded.unit_cost, origin_fee=excluded.origin_fee, transit_fee=excluded.transit_fee
                    """, (route_name, unit_cost, origin_fee, transit_fee))
                    st.success(f"航线 {route_name} 配置成功！")
                except Exception as e:
                    st.error(f"保存失败: {e}")

        st.subheader("当前航线成本一览")
        df_routes = run_query("SELECT * FROM routes")
        st.dataframe(df_routes, use_container_width=True)
        
        # 删除航线功能
        if not df_routes.empty:
            delete_route_id = st.selectbox("选择要删除的航线ID", df_routes['id'])
            if st.button("❌ 删除选中航线"):
                run_cmd("DELETE FROM routes WHERE id = ?", (int(delete_route_id),))
                st.warning("航线已删除")
                st.rerun()

    with tab2:
        st.subheader("📂 账单模板与操作员管理")
        st.file_uploader("上传各类账单模板 (Excel/Word)", type=['xlsx', 'docx'])
        st.info("提示：此处的模板可供操作员端一键输出账单时引用。")
        
        st.subheader("👥 操作员账号管理")
        st.text_input("新建操作员账号")
        st.button("创建账号")

# ==========================================
# 2. 操作员界面
# ==========================================
else:
    st.header("📋 操作员工作台")
    tab_input, tab_query = st.tabs(["📊 新单录入与报价", "🔍 订单查询、修改与明细"])

    with tab_input:
        st.subheader("新货物订单录入")
        
        # 获取最新的航线信息供给操作员选择
        df_active_routes = run_query("SELECT route_name FROM routes")
        if df_active_routes.empty:
            st.error("请联系管理员先在后台录入航线成本数据信息！")
        else:
            with st.form("order_form"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    order_date = st.date_input("录入时间", datetime.now())
                    awb_no = st.text_input("提单号/入仓号")
                    selected_route = st.selectbox("选择航线段", df_active_routes['route_name'])
                    customer_name = st.text_input("客户名称")
                with col2:
                    length = st.number_input("长 (cm)", min_value=0.0, value=100.0)
                    width = st.number_input("宽 (cm)", min_value=0.0, value=100.0)
                    height = st.number_input("高 (cm)", min_value=0.0, value=100.0)
                    pieces = st.number_input("件数 (pcs)", min_value=1, value=1)
                with col3:
                    gross_weight = st.number_input("毛重 (kg)", min_value=0.0, value=50.0)
                    customs_type = st.radio("报关方式", ["买单报关", "独立报关", "双清包税"])
                    payment_status = st.selectbox("付款状态", ["未收款", "部分收款", "已收齐款项"])
                    uploaded_file = st.file_uploader("上传提单及其他相关文件", type=['pdf', 'jpg', 'png', 'xlsx'])

                submit_order = st.form_submit_button("⚡ 自动计算并保存订单")

                if submit_order:
                    # 核心逻辑：自动计算计费重 (体积重 = 长*宽*高/6000)
                    # 注意：通常空运体积计算会乘以件数
                    volumetric_weight = (length * width * height / 6000.0) * pieces
                    chargeable_weight = max(gross_weight, volumetric_weight)
                    
                    # 获取对应航线的计费单价和操作费
                    route_info = run_query("SELECT * FROM routes WHERE route_name = ?", (selected_route,)).iloc[0]
                    
                    freight_cost = chargeable_weight * route_info['unit_cost']
                    handling_cost = route_info['origin_fee'] + route_info['transit_fee']
                    total_cost = freight_cost + handling_cost
                    
                    # 保存文件存根名字
                    fname = uploaded_file.name if uploaded_file else ""

                    # 插入数据库
                    run_cmd("""
                        INSERT INTO orders (date, awb_no, route_name, customer_name, length, width, height, pieces, 
                                            gross_weight, chargeable_weight, customs_type, freight_cost, handling_cost, 
                                            total_cost, payment_status, file_name)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (str(order_date), awb_no, selected_route, customer_name, length, width, height, int(pieces),
                          gross_weight, chargeable_weight, customs_type, freight_cost, handling_cost, total_cost, payment_status, fname))
                    
                    st.success(f"🎉 订单保存成功！自动计算结果：计费重 {chargeable_weight:.2s} kg，总运费明细：{total_cost:.2f} 元。")

    with tab_query:
        st.subheader("🔍 运单综合筛选与修改 (支持保存、删除、导出)")
        
        # 筛选器
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            search_awb = st.text_input("按提单号/入仓号筛选")
        with col_f2:
            search_cust = st.text_input("按客户名筛选")
        with col_f3:
            search_pay = st.selectbox("收款状态筛选", ["全部", "未收款", "部分收款", "已收齐款项"])

        # 构建动态SQL
        query_sql = "SELECT * FROM orders WHERE 1=1"
        params = []
        if search_awb:
            query_sql += " AND awb_no LIKE ?"
            params.append(f"%{search_awb}%")
        if search_cust:
            query_sql += " AND customer_name LIKE ?"
            params.append(f"%{search_cust}%")
        if search_pay != "全部":
            query_sql += " AND payment_status = ?"
            params.append(search_pay)

        df_orders = run_query(query_sql, params)
        
        if not df_orders.empty:
            # 允许用户在界面直接修改和删除
            st.dataframe(df_orders, use_container_width=True)
            
            # 操作单项订单
            st.markdown("---")
            col_op1, col_op2 = st.columns(2)
            with col_op1:
                selected_id = st.selectbox("选择需要操作的订单ID", df_orders['id'])
                current_order = df_orders[df_orders['id'] == selected_id].iloc[0]
                
                # 一键输出账单模拟
                st.download_button(
                    label="📥 一键输出该单账单 (CSV格式)",
                    data=df_orders[df_orders['id'] == selected_id].to_csv(index=False).encode('utf-8'),
                    file_name=f"Invoice_{current_order['awb_no']}.csv",
                    mime='text/csv',
                )
            with col_op2:
                new_status = st.selectbox("快速修改收款状态", ["未收款", "部分收款", "已收齐款项"], key="status_update")
                if st.button("💾 保存状态修改"):
                    run_cmd("UPDATE orders SET payment_status = ? WHERE id = ?", (new_status, int(selected_id)))
                    st.success("状态已更新！")
                    st.rerun()
                    
                if st.button("🗑️ 删除该笔订单"):
                    run_cmd("DELETE FROM orders WHERE id = ?", (int(selected_id),))
                    st.warning("订单已成功删除！")
                    st.rerun()
        else:
            st.info("暂无符合条件的订单。")