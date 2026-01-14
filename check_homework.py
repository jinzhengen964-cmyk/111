import streamlit as st
import pandas as pd
import re
import io
import os
import datetime
import hashlib
from pathlib import Path

# --- 页面配置 ---
st.set_page_config(page_title="作业多维度分析系统", layout="wide")
st.title("🎓 作业提交多维度分析系统")

# --- 核心处理函数 ---
def extract_id(filename):
    """从文件名提取9位学号"""
    match = re.search(r'\d{9}', filename)
    return match.group() if match else None

def calculate_file_md5(file_path):
    """读取本地文件并计算MD5"""
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except:
        return None

def get_roster_from_path(file_path):
    """读取本地Excel花名册"""
    try:
        # 指定引擎以防云端或部分环境缺失
        df = pd.read_excel(file_path, engine='openpyxl')
        sid_idx = next((i for i, col in enumerate(df.columns) if '学号' in str(col)), None)
        if sid_idx is None:
            for i, col in enumerate(df.columns):
                if any(re.search(r'\d{9}', str(v)) for v in df[col].dropna().head(5)):
                    sid_idx = i
                    break
        if sid_idx is None: return None, "Excel中未找到学号列"
        
        name_idx = sid_idx + 1
        roster = {}
        for _, row in df.iterrows():
            sid_match = re.search(r'\d{9}', str(row[df.columns[sid_idx]]))
            if sid_match:
                s_id = sid_match.group()
                s_name = str(row[df.columns[name_idx]]) if name_idx < len(df.columns) else "未知"
                roster[s_id] = s_name
        return roster, None
    except Exception as e:
        return None, str(e)

# --- 侧边栏：路径输入区 ---
with st.sidebar:
    st.image('https://tse3.mm.bing.net/th/id/OIP.eVdPo2CI6WY3vDM14PsTYQHaFy?rs=1&pid=ImgDetMain&o=7&rm=3')
    st.header("📁 本地路径设置")
    st.info("请在下方输入电脑里的文件夹路径")
    
    # 手动输入路径
    roster_path = st.text_input("1. 花名册文件路径", value=r"C:\Users\Documents\花名册.xlsx")
    hw_folder_path = st.text_input("2. 作业文件夹路径", value=r"C:\Users\Documents\学生作业")
    
    st.divider()
    st.header("⚙️ 任务设置")
    deadline_date = st.date_input("截止日期", datetime.date.today())
    deadline_time = st.time_input("截止时间", datetime.time(23, 59))
    deadline = datetime.datetime.combine(deadline_date, deadline_time)

# --- 主界面逻辑 ---
if os.path.exists(roster_path) and os.path.exists(hw_folder_path):
    roster_dict, err = get_roster_from_path(roster_path)
    
    if err:
        st.error(f"花名册读取失败: {err}")
    else:
        all_roster_ids = set(roster_dict.keys())
        analysis = {"valid": {}, "unknown": [], "similarity": {}}

        # 遍历文件夹下的所有文件
        files = [f for f in os.listdir(hw_folder_path) if os.path.isfile(os.path.join(hw_folder_path, f))]
        
        for fname in files:
            full_path = os.path.join(hw_folder_path, fname)
            sid = extract_id(fname)
            
            # --- 关键：读取本地文件的修改时间 ---
            mtime_ts = os.path.getmtime(full_path)
            mtime = datetime.datetime.fromtimestamp(mtime_ts)
            is_late = mtime > deadline
            
            md5_hash = calculate_file_md5(full_path)
            
            file_info = {
                "name": fname,
                "time": mtime,
                "is_late": is_late,
                "md5": md5_hash,
                "size": os.path.getsize(full_path)
            }

            if not sid or sid not in all_roster_ids:
                analysis["unknown"].append(file_info)
            else:
                analysis["valid"].setdefault(sid, []).append(file_info)
            
            if md5_hash:
                analysis["similarity"].setdefault(md5_hash, []).append(file_info)

        # --- 数据展示 ---
        st.divider()
        sub_count = len(analysis["valid"])
        total_count = len(all_roster_ids)
        
        c1, c2, c3 = st.columns(3)
        c1.metric("应交人数", total_count)
        c2.metric("已交人数", sub_count)
        c3.metric("完成率", f"{int(sub_count/total_count*100) if total_count else 0}%")
        st.progress(sub_count/total_count if total_count else 0)

        t1, t2, t3, t4 = st.tabs(["❌ 未交名单", "✅ 已交详情", "❓ 异常/重复", "‼ 相似度初筛"])

        with t1:
            missing_ids = sorted(list(all_roster_ids - set(analysis["valid"].keys())))
            if missing_ids:
                df_m = pd.DataFrame([{"学号": i, "姓名": roster_dict[i]} for i in missing_ids])
                st.dataframe(df_m, use_container_width=True)
            else:
                st.success("🎉 全员交齐！")

        with t2:
            done_data = []
            for sid, f_list in analysis["valid"].items():
                f = max(f_list, key=lambda x: x["time"]) # 自动取最后修改的版本
                done_data.append({
                    "学号": sid, "姓名": roster_dict[sid],
                    "最后修改时间": f["time"].strftime('%Y-%m-%d %H:%M'),
                    "状态": "⏰ 迟交" if f["is_late"] else "正常",
                    "文件名": f["name"]
                })
            st.dataframe(pd.DataFrame(done_data).sort_values("学号"), use_container_width=True)

        with t3:
            col_a, col_b = st.columns(2)
            with col_a:
                st.subheader("😅 异常文件")
                for f in analysis["unknown"]: st.write(f"- {f['name']}")
            with col_b:
                st.subheader("👥👥 重复提交")
                for sid, flist in analysis["valid"].items():
                    if len(flist) > 1: st.warning(f"{sid} ({roster_dict[sid]}) 有 {len(flist)} 个版本")

        with t4:
            st.subheader("🤫🤫🤫 内容完全一致检测")
            for md5, flist in analysis["similarity"].items():
                if len(flist) > 1:
                    st.error(f"发现重复内容：")
                    for f in flist: st.write(f"  - {f['name']}")

else:
    st.info("🔍 请在左侧侧边栏输入正确的【花名册路径】和【作业文件夹路径】。")
