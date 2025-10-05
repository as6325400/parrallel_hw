# plot_from_txt.py  (speedup 使用 Total job wall-time；B/C x 軸只顯示整數)
import re, os, glob
import matplotlib.pyplot as plt

# 解析 analyze.py 的輸出行
LINE_PATTERNS = {
    "pre_mean":   re.compile(r"Preprocessing time\s*\(mean\)\s*:\s*([0-9.]+)"),
    "input_mean":  re.compile(r"Input time\s*\(mean over ranks\)\s*:\s*([0-9.]+)"),
    "output_mean": re.compile(r"Output time\s*\(mean over ranks\)\s*:\s*([0-9.]+)"),
    "comm_mean":   re.compile(r"Communication\s*\(mean over ranks\)\s*:\s*([0-9.]+)"),
    "comp_mean":  re.compile(r"Computation\s*\(mean/max/min\)\s*:\s*([0-9.]+)\s*/"),
    # 新增：Total job wall-time（若 analyze.py 有印）
    "total_wall": re.compile(r"Total job wall-time\s*:\s*([0-9.]+)"),
}
FNAME_PAT = re.compile(r"(?P<nodes>\d+)_(?P<procs>\d+)\.txt$")

def parse_txt(path):
    m = FNAME_PAT.search(os.path.basename(path))
    if not m:
        return None
    nodes = int(m.group("nodes")); procs = int(m.group("procs"))

    vals = {}
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            for key, pat in LINE_PATTERNS.items():
                mo = pat.search(line)
                if mo:
                    vals[key] = float(mo.group(1))

    required = {"pre_mean", "input_mean", "output_mean", "comm_mean", "comp_mean"}
    missing = required - set(vals.keys())
    if missing:
        print(f"[WARN] {path} 缺少欄位: {missing}，跳過。")
        return None

    # 用 total_wall (如果有)；否則退回分項相加
    total = vals.get("total_wall",
                     vals["pre_mean"] + vals["input_mean"] + vals["output_mean"] +
                     vals["comm_mean"] + vals["comp_mean"])

    return {
        "nodes": nodes,
        "procs": procs,
        "ppn": procs // nodes if nodes > 0 else procs,
        "pre": vals["pre_mean"],
        "io": vals["input_mean"] + vals["output_mean"],
        "comm": vals["comm_mean"],
        "comp": vals["comp_mean"],
        "total": total,              # Speedup 用這個（優先使用 Total job wall-time）
        "fname": os.path.basename(path),
    }

# 收集 <nodes>_<procs>.txt
records = []
for path in glob.glob("./inform/*.txt"):
    rec = parse_txt(path)
    if rec: records.append(rec)
if not records:
    raise SystemExit("找不到任何 <nodes>_<procs>.txt")

# 分組
group_A = sorted([r for r in records if r["nodes"] == 1], key=lambda x: x["procs"])   # 1 node, p=1..12
group_B = sorted([r for r in records if r["ppn"] == 4], key=lambda x: x["nodes"])     # 4 ppn, nodes=1..4
group_C = sorted([r for r in records if r["procs"] == 12], key=lambda x: x["nodes"])  # total p=12, nodes=1..4

def ok(name, grp):
    if not grp: print(f"[WARN] 族群 {name} 為空，略過對應圖。")
    return bool(grp)

def _safe_legend(ax):
    handles, labels = ax.get_legend_handles_labels()
    if labels:
        ax.legend()

def stacked_time_plot(grp, x_vals, x_label, title, outfile, tick_vals=None):
    pre  = [r["pre"] for r in grp]
    io   = [r["io"] for r in grp]
    comm = [r["comm"] for r in grp]
    comp = [r["comp"] for r in grp]

    fig, ax = plt.subplots(figsize=(8,5.2))
    ax.bar(x_vals, pre, label="Preprocessing Time")
    btm = pre[:]
    ax.bar(x_vals, io, bottom=btm, label="MPIIO Time")
    btm = [btm[i]+io[i] for i in range(len(btm))]
    ax.bar(x_vals, comm, bottom=btm, label="Communication Time")
    btm = [btm[i]+comm[i] for i in range(len(btm))]
    ax.bar(x_vals, comp, bottom=btm, label="Single Node Computation Time")

    ax.set_xlabel(x_label); ax.set_ylabel("Time (sec)")
    ax.set_title(title)
    if tick_vals is not None:
        ax.set_xticks(tick_vals)
        ax.set_xticklabels([str(v) for v in tick_vals])
    _safe_legend(ax)
    fig.tight_layout()
    fig.savefig(outfile, dpi=160)
    plt.close(fig)
    print(f"[OK] {outfile}")

def speedup_plot(grp, x_vals, x_label, title, outfile, tick_vals=None):
    if not grp: return
    T0 = grp[0]["total"]
    if T0 <= 0:
        print(f"[WARN] baseline total 為 0，略過 {outfile}"); return
    speedup = [T0 / r["total"] if r["total"]>0 else 0.0 for r in grp]
    ideal   = [x_vals[i] / x_vals[0] for i in range(len(x_vals))]

    fig, ax = plt.subplots(figsize=(7.8,4.8))
    ax.plot(x_vals, speedup, marker="o", linewidth=2, label="Experiment Data")
    ax.plot(x_vals, ideal, "--", linewidth=2, label="Ideal Speedup Factor")
    ax.set_xlabel(x_label); ax.set_ylabel("Speedup Factor")
    ax.set_title(title); ax.grid(True, alpha=0.3)
    if tick_vals is not None:
        ax.set_xticks(tick_vals)
        ax.set_xticklabels([str(v) for v in tick_vals])
    _safe_legend(ax)
    fig.tight_layout()
    fig.savefig(outfile, dpi=160)
    plt.close(fig)
    print(f"[OK] {outfile}")

# A) 1 node, p=1..12（保持原樣）
if ok("A", group_A):
    xA = [r["procs"] for r in group_A]
    stacked_time_plot(group_A, xA, "Processes Number",
                      "1 Node — Time Breakdown vs Processes",
                      "./img/A_single_node_times.png")
    speedup_plot(group_A, xA, "Processes Number",
                 "1 Node — Strong Scaling (Speedup vs Processes)",
                 "./img/A_single_node_speedup.png")

# B) 每 node 4 個 process, nodes=1..4（x 軸只顯示整數節點）
if ok("B", group_B):
    xB = [r["nodes"] for r in group_B]
    stacked_time_plot(group_B, xB, "Node Count (4 Processes / Node)",
                      "Per-Node 4 Processes — Time Breakdown",
                      "./img/B_4ppn_times.png",
                      tick_vals=xB)
    speedup_plot(group_B, xB, "Node Count (4 Processes / Node)",
                 "Per-Node 4 Processes — Speedup vs Nodes",
                 "./img/B_4ppn_speedup.png",
                 tick_vals=xB)

# C) total p=12, nodes=1..4（x 軸只顯示整數節點）
if ok("C", group_C):
    xC = [r["nodes"] for r in group_C]
    stacked_time_plot(group_C, xC, "Node Count (Total 12 Processes)",
                      "Total 12 Processes — Time Breakdown by Node Split",
                      "./img/C_12total_times.png",
                      tick_vals=xC)
    speedup_plot(group_C, xC, "Node Count (Total 12 Processes)",
                 "Total 12 Processes — Speedup vs Nodes",
                 "./img/C_12total_speedup.png",
                 tick_vals=xC)

print("\n完成：已輸出 0~6 張圖（依檔案齊全度）。")
