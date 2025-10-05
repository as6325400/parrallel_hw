#!/usr/bin/env bash
# run_bench.sh
# 自動批次實驗與分析：
#  A) 固定總進程 12：1N×12ppn、2N×6ppn、3N×4ppn、4N×3ppn
#  B) 單節點 strong-scaling：1N×{1..12}ppn
#  C) 每節點 4 個進程：N=1..4（總進程 4,8,12,16）
#
# 流程（每回合）：
#   1) srun -N <nodes> -n <procs> -w <hostlist> --ntasks-per-node=<ppn> ./wrapper.sh ./hw1 536869888 ./testcases/40.in 40.out
#   2) ./convert_csv.sh
#   3) python analyze.py   →  輸出到 <nodes>_<procs>.txt
#   4) rm -r nsys_reports/
#
# 你可以用環境變數覆蓋以下參數（如需）：
#   HOST_RANGE="apollo[33-36]"     # 可用節點範圍
#   EXE="./hw1"                    # 可執行檔（傳給 wrapper.sh）
#   WRAPPER="./wrapper.sh"         # 包裝執行腳本（會產生 .nsys-rep 到 nsys_reports/）
#   NSYS_CONVERT="./convert_csv.sh"
#   ANALYZER="python analyze.py"
#   ARG1="536869888" ARG2="./testcases/40.in" ARG3="40.out"
#
set -euo pipefail

# ---- 可覆蓋參數（預設值） ----
HOST_RANGE="${HOST_RANGE:-apollo[47-50]}"
WRAPPER="${WRAPPER:-./wrapper.sh}"
EXE="${EXE:-./hw1}"
NSYS_CONVERT="${NSYS_CONVERT:-./convert_csv.sh}"
ANALYZER="${ANALYZER:-python analyze.py}"
ARG1="${ARG1:-536869888}"
ARG2="${ARG2:-./testcases/40.in}"
ARG3="${ARG3:-40.out}"

# 取得前 N 台主機的逗號清單，供 -w 使用
pick_hosts () {
  local nodes="$1"
  # 以 Slurm 解析 host range，取前 N 台再以逗號串接
  scontrol show hostnames "${HOST_RANGE}" | head -n "${nodes}" | paste -sd, -
}

# 執行單一回合
run_case () {
  local nodes="$1"    # -N
  local procs="$2"    # -n
  local ppn="$3"      # --ntasks-per-node
  local tag="${nodes}_${procs}"   # 輸出檔名格式

  echo "================================================================================"
  echo "[`date '+%F %T'`] Running: nodes=${nodes}, procs=${procs}, ppn=${ppn}  (tag=${tag})"
  echo "Host range: ${HOST_RANGE}"

  # 主機清單
  HOSTS="$(pick_hosts "${nodes}")"
  if [[ -z "${HOSTS}" ]]; then
    echo "ERROR: 無法從 ${HOST_RANGE} 取出 ${nodes} 台主機供 -w 使用" >&2
    exit 1
  fi
  echo "Using hosts: ${HOSTS}"

  # 確保前次報告清掉（避免殘留）
  rm -rf nsys_reports || true
  mkdir -p nsys_reports

  rm -rf nsys_csv
  mkdir -p nsys_csv

  # 1) 跑程式（由 wrapper 觸發 nsys profile 產生 nsys_reports/*.nsys-rep）
  srun -N "${nodes}" -n "${procs}" -w "${HOSTS}" --ntasks-per-node="${ppn}" \
    "${WRAPPER}" "${EXE}" "${ARG1}" "${ARG2}" "${ARG3}"

  # 2) 轉 CSV
  echo "[`date '+%F %T'`] Converting reports to CSV..."
  ${NSYS_CONVERT}

  # 3) 分析並寫入 <nodes>_<procs>.txt
  echo "[`date '+%F %T'`] Analyzing..."
  {
    echo "=== nodes=${nodes}, procs=${procs}, ppn=${ppn} ==="
    ${ANALYZER}
  } | tee "inform/${tag}.txt"

  # 4) 刪除 nsys_reports/
  echo "[`date '+%F %T'`] Cleaning nsys_reports/"
  rm -rf nsys_reports
  echo "[`date '+%F %T'`] Done: ${tag}"
}

# --------------------------
#            主程式
# --------------------------

# A) 固定總進程 12
run_case 1 12 12     # 1 node × 12 ppn
run_case 2 12 6      # 2 nodes × 6 ppn
run_case 3 12 4      # 3 nodes × 4 ppn
run_case 4 12 3      # 4 nodes × 3 ppn

# B) 單節點：1..12 個進程
for p in $(seq 1 12); do
  run_case 1 "${p}" "${p}"
done

# C) 每節點 4 個進程；節點 1..4（總進程 4, 8, 12, 16）
for n in 1 2 3 4; do
  procs=$((4 * n))
  run_case "${n}" "${procs}" 4
done

echo "================================================================================"
echo "[`date '+%F %T'`] ALL BENCHMARKS FINISHED."
