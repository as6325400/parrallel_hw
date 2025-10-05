# analyze.py
import glob
import os
import pandas as pd

CSV_DIR = "nsys_csv"

COMM_EVENTS = {
    "MPI_Waitall", "MPI_Allreduce", "MPI_Barrier",
    "MPI_Isend", "MPI_Irecv", "MPI_Send", "MPI_Recv"
}

import numpy as np

def get_wall_times_across_ranks(all_dfs):
    """回傳 overall wall-time（秒）：全檔案最早 Start 到最晚 End"""
    min_start = min(float(df["Start (ns)"].min()) for df in all_dfs)
    max_end   = max(float(df["End (ns)"].max())   for df in all_dfs)
    return (max_end - min_start) / 1e9

def get_sort_phase_per_rank(df):
    """
    以單一 rank 的 CSV，找出：
    - read_close_end_ns: 第一個 MPI_File_read_at_all 後的第一個 MPI_File_close 的 End
    - write_start_ns   : 第一個 MPI_File_write_at_all 的 Start
    回傳 (sort_phase_seconds, read_close_end_ns, write_start_ns)；若找不到則回傳 (0, None, None)
    """
    df = df.sort_values("Start (ns)").reset_index(drop=True)
    read_idxs = df.index[df["Event"] == "MPI_File_read_at_all"]
    write_idxs = df.index[df["Event"] == "MPI_File_write_at_all"]
    if not len(read_idxs) or not len(write_idxs):
        return (0.0, None, None)

    ridx = int(read_idxs[0])
    # 找 read_at_all 之後第一個 close
    close_after_read = df.loc[ridx+1:].index[df.loc[ridx+1:, "Event"] == "MPI_File_close"]
    if not len(close_after_read):
        return (0.0, None, None)

    close_idx = int(close_after_read[0])
    read_close_end_ns = float(df.loc[close_idx, "End (ns)"])

    widx = int(write_idxs[0])
    write_start_ns = float(df.loc[widx, "Start (ns)"])

    if write_start_ns <= read_close_end_ns:
        return (0.0, read_close_end_ns, write_start_ns)

    return ((write_start_ns - read_close_end_ns) / 1e9, read_close_end_ns, write_start_ns)

def comm_time_inside_window(df, win_start_ns, win_end_ns):
    """計算通訊事件在指定時間窗內的總時間（秒），粗略以事件整段落在窗內才計入。"""
    mask_evt = df["Event"].isin({
        "MPI_Waitall","MPI_Allreduce","MPI_Barrier",
        "MPI_Isend","MPI_Irecv","MPI_Send","MPI_Recv"
    })
    sub = df[mask_evt].copy()
    # 僅統計整段落在窗內的事件（簡化；如需更精確可做區段交集量）
    mask_in = (sub["Start (ns)"] >= win_start_ns) & (sub["End (ns)"] <= win_end_ns)
    return float(sub.loc[mask_in, "Duration (ns)"].sum()) / 1e9
  
def read_nsys_csv(path: str) -> pd.DataFrame:
    """
    會自動略過前面的提示行，從 'Start (ns),End (ns)...' 表頭開始讀。
    也處理 BOM / 空白等狀況。
    """
    header_key = "Start (ns),End (ns)"
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    # 找出表頭所在行
    header_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith("Start (ns),End (ns)"):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError(f"Cannot find CSV header in {path}")

    # 從表頭開始串回字串給 pandas
    from io import StringIO
    content = "".join(lines[header_idx:])
    df = pd.read_csv(StringIO(content))
    return df

def first_after(df, start_idx, event_name):
    sub = df.loc[start_idx+1:]
    hit = sub.index[sub["Event"] == event_name]
    return int(hit[0]) if len(hit) else None

def sum_duration(df, events):
    return float(df.loc[df["Event"].isin(events), "Duration (ns)"].sum())

def analyze_one(csv_path):
    df = read_nsys_csv(csv_path)
    df = df.sort_values("Start (ns)").reset_index(drop=True)

    # ---------- Preprocessing ----------
    # 定義：第一次 read_at_all 之前的所有事件時間總和（單 rank 上事件不重疊，直接加即可）
    first_read_idx = df.index[df["Event"] == "MPI_File_read_at_all"]
    if len(first_read_idx):
        first_read_start = df.loc[first_read_idx[0], "Start (ns)"]
        pre_ns = float(df.loc[df["Start (ns)"] < first_read_start, "Duration (ns)"].sum())
    else:
        # 沒有 read_at_all 的極少數情況：取 Init/Open 作為前置
        pre_ns = sum_duration(df, {"MPI_Init", "MPI_File_open"})

    # ---------- Input ----------
    input_ns = 0.0
    if len(first_read_idx):
        ridx = int(first_read_idx[0])
        input_ns += float(df.loc[ridx, "Duration (ns)"])
        close_idx = first_after(df, ridx, "MPI_File_close")
        if close_idx is not None:
            input_ns += float(df.loc[close_idx, "Duration (ns)"])

    # ---------- Output ----------
    first_write_idx = df.index[df["Event"] == "MPI_File_write_at_all"]
    output_ns = 0.0
    if len(first_write_idx):
        widx = int(first_write_idx[0])
        output_ns += float(df.loc[widx, "Duration (ns)"])
        close2_idx = first_after(df, widx, "MPI_File_close")
        if close2_idx is not None:
            output_ns += float(df.loc[close2_idx, "Duration (ns)"])

    # ---------- Communication ----------
    comm_ns = sum_duration(df, COMM_EVENTS)

    # ---------- Rank Wall-time ----------
    wall_ns = float(df["End (ns)"].max() - df["Start (ns)"].min())

    # ---------- Computation (估算) ----------
    comp_ns = max(0.0, wall_ns - (pre_ns + input_ns + output_ns + comm_ns))

    return {
        "rank_name": os.path.basename(csv_path).replace(".csv", ""),
        "pre_s": pre_ns / 1e9,
        "input_s": input_ns / 1e9,
        "output_s": output_ns / 1e9,
        "comm_s": comm_ns / 1e9,
        "comp_s": comp_ns / 1e9,
        "wall_s": wall_ns / 1e9,
    }

def main():
    files = sorted(glob.glob(os.path.join(CSV_DIR, "*.csv")))
    if not files:
        print(f"No CSV files found under {CSV_DIR}/")
        return

    # 先把所有 df 讀進來（沿用你的 robust 讀法）
    dfs = []
    rows = []
    for p in files:
        dfp = read_nsys_csv(p)
        dfs.append(dfp)
        rows.append(analyze_one(p))
    df = pd.DataFrame(rows)

    # ====== 你原有的聚合 ======
    pre_mean = df["pre_s"].mean()
    pre_max  = df["pre_s"].max()
    input_mean  = df["input_s"].mean()
    output_mean = df["output_s"].mean()
    comp_mean = df["comp_s"].mean()
    comp_max  = df["comp_s"].max()
    comp_min  = df["comp_s"].min()
    comm_mean  = df["comm_s"].mean()

    # ====== 新增：整體 job 牆鐘時間 ======
    total_wall_s = get_wall_times_across_ranks(dfs)

    # ====== 新增：Odd-even sort 牆鐘時間（取各 rank 的 sort_phase 最大值） ======
    sort_phases = []
    sort_comm   = []
    for dfp in dfs:
        sp_s, t0, t1 = get_sort_phase_per_rank(dfp)
        sort_phases.append(sp_s)
        if t0 is not None and t1 is not None and sp_s > 0:
            sort_comm.append(comm_time_inside_window(dfp, t0, t1))
    sort_wall_s = max(sort_phases) if sort_phases else 0.0
    # 也順帶給你平均通訊在 sort 階段的時間（可寫在報告）
    sort_comm_mean_s = float(np.mean(sort_comm)) if sort_comm else 0.0

    # 明細輸出
    df.to_csv("nsys_phase_by_rank.csv", index=False)

    # 摘要輸出
    print("\n=== Aggregated Metrics (seconds) ===")
    print(f"Preprocessing time  (mean) : {pre_mean:.6f}")
    print(f"Preprocessing time  (max)  : {pre_max:.6f}")
    print(f"Input time   (mean over ranks)  : {input_mean:.6f}")
    print(f"Output time  (mean over ranks)  : {output_mean:.6f}")
    print(f"Computation  (mean/max/min)    : {comp_mean:.6f} / {comp_max:.6f} / {comp_min:.6f}")
    print(f"Communication (mean over ranks) : {comm_mean:.6f}")
    print(f"Total job wall-time            : {total_wall_s:.6f}")
    print(f"Odd-even sort wall-time        : {sort_wall_s:.6f}  (read_close→write_start)")
    print(f"Odd-even sort mean COMM time   : {sort_comm_mean_s:.6f}  (inside sort window)")
    print("\nSaved per-rank breakdown to: nsys_phase_by_rank.csv")


if __name__ == "__main__":
    main()
