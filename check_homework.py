import streamlit as st
import pandas as pd
import re
import io
import os
import datetime
import hashlib

# --- 页面配置 ---
st.set_page_config(page_title="作业多维度分析系统", layout="wide")
st.title("🎓 作业提交多维度分析系统")

# --- 核心处理函数 ---
def extract_id(filename):
    """从文件名提取9位学号"""
    match = re.search(r'\d{9}', filename)
    return match.group() if match else None

def calculate_bytes_md5(file_bytes):
    """计算上传文件流的MD5哈希值"""
    hash_md5 = hashlib.md5()
    hash_md5.update(file_bytes)
    return hash_md5.hexdigest()

def get_roster_from_upload(uploaded_file):
    """从上传的Excel中自动识别学号和姓名列"""
    try:
        df = pd.read_excel(uploaded_file)
        # 寻找学号列索引
        sid_idx = next((i for i, col in enumerate(df.columns) if '学号' in str(col)), None)
        if sid_idx is None:
            for i, col in enumerate(df.columns):
                if any(re.search(r'\d{9}', str(v)) for v in df[col].dropna().head(5)):
                    sid_idx = i
                    break
        if sid_idx is None: return None, "Excel中未找到学号列"
        
        # 姓名列为学号后一列
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

# --- 侧边栏：手动上传区 ---
with st.sidebar:
    st.header("📁 数据上传")
    uploaded_roster = st.file_uploader("1. 上传花名册 (Excel)", type=['xlsx'])
    
    # 允许上传多个文件，甚至可以直接把整个文件夹里的文件拖进来
    uploaded_homeworks = st.file_uploader("2. 上传作业文件 (可多选/全选拖入)", 
                                         type=['py', 'zip', 'txt', 'docx', 'pdf'], 
                                         accept_multiple_files=True)
    
    st.divider()
    st.header("⚙️ 任务设置")
    deadline_date = st.date_input("截止日期", datetime.date.today())
    deadline_time = st.time_input("截止时间", datetime.time(23, 59))
    deadline = datetime.datetime.combine(deadline_date, deadline_time)

# --- 主界面逻辑 ---
if uploaded_roster and uploaded_homeworks:
    roster_dict, err = get_roster_from_upload(uploaded_roster)
    
    if err:
        st.error(f"花名册读取失败: {err}")
    else:
        all_roster_ids = set(roster_dict.keys())
        
        # 初始化分析容器
        analysis = {
            "valid": {},    # 合规提交 {学号: [文件信息]}
            "unknown": [],  # 无法匹配的文件
            "similarity": {} # MD5: [文件信息]
        }

        # 处理每一个上传的文件
        for uploaded_file in uploaded_homeworks:
            sid = extract_id(uploaded_file.name)
            # 获取上传文件流的MD5
            file_bytes = uploaded_file.getvalue()
            md5_hash = calculate_bytes_md5(file_bytes)
            
            # Streamlit上传文件的最后修改时间通常是上传时间，
            # 这里的“迟交分析”更适合本地环境，但我们可以通过界面设置来模拟。
            # 注意：Web环境下无法直接获取原文件的本地修改时间，通常以当前时间为准
            now = datetime.datetime.now()
            is_late = now > deadline

            file_info = {
                "name": uploaded_file.name,
                "time": now,
                "is_late": is_late,
                "md5": md5_hash,
                "size": uploaded_file.size
            }

            if not sid or sid not in all_roster_ids:
                analysis["unknown"].append(file_info)
            else:
                if sid not in analysis["valid"]:
                    analysis["valid"][sid] = []
                analysis["valid"][sid].append(file_info)
            
            # 记录相似度
            if md5_hash not in analysis["similarity"]:
                analysis["similarity"][md5_hash] = []
            analysis["similarity"][md5_hash].append(file_info)

        # --- 数据展示 ---
        st.divider()
        submitted_count = len(analysis["valid"])
        total_count = len(all_roster_ids)
        percent = int(submitted_count / total_count * 100) if total_count > 0 else 0
        
        c1, c2, c3 = st.columns([1, 1, 2])
        c1.metric("匹配花名册人数", f"{submitted_count} / {total_count}")
        c2.metric("完成率", f"{percent}%")
        with c3:
            st.write("班级提交进度")
            st.progress(percent / 100)

        # 页签布局
        t1, t2, t3, t4 = st.tabs(["❌ 未交名单", "✅ 已交分析", "⚠️ 异常/重复", "👥 相似度初筛"])

        with t1:
            missing_ids = sorted(list(all_roster_ids - set(analysis["valid"].keys())))
            if missing_ids:
                df_missing = pd.DataFrame([{"学号": i, "姓名": roster_dict[i]} for i in missing_ids])
                st.dataframe(df_missing, use_container_width=True)
                
                # 下载未交名单
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_missing.to_excel(writer, index=False)
                st.download_button("📥 下载未交名单Excel", output.getvalue(), "未交名单.xlsx")
            else:
                st.success("🎉 全员交齐！")

        with t2:
            st.markdown("### 已交情况")
            done_data = []
            for sid, f_list in analysis["valid"].items():
                # 若有多文件，显示最新上传的一个
                f = f_list[-1]
                done_data.append({
                    "学号": sid,
                    "姓名": roster_dict[sid],
                    "文件名": f["name"],
                    "大小(KB)": round(f["size"]/1024, 2),
                    "版本数": len(f_list)
                })
            st.dataframe(pd.DataFrame(done_data).sort_values("学号"), use_container_width=True, hide_index=True)

        with t3:
            col_a, col_b = st.columns(2)
            with col_a:
                st.subheader("❓ 无法识别/不在名册")
                if analysis["unknown"]:
                    for f in analysis["unknown"]:
                        st.write(f"- {f['name']}")
                else:
                    st.write("无异常")
            with col_b:
                st.subheader("👯 重复提交")
                dups = {sid: flist for sid, flist in analysis["valid"].items() if len(flist) > 1}
                for sid, flist in dups.items():
                    st.warning(f"{sid} ({roster_dict[sid]}) 提交了 {len(flist)} 个文件")

        with t4:
            st.subheader("👥 内容完全一致检测 (MD5)")
            found_sim = False
            for md5, flist in analysis["similarity"].items():
                if len(flist) > 1:
                    found_sim = True
                    st.error(f"内容指纹 [{md5[:8]}] 完全一致的文件：")
                    for f in flist:
                        st.write(f"  - {f['name']}")
            if not found_sim:
                st.info("未发现完全相同的文件内容。")

else:
    st.info("👈 请先在左侧侧边栏上传【花名册】和【作业文件】。你可以一次性框选所有作业文件拖入。")