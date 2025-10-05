#!/bin/bash
# convert_nsys_csv.sh
# 將 nsys_reports 下所有 .nsys-rep 轉成 csv 輸出到 nsys_csv/

set -e  # 有錯誤就停止執行

INPUT_DIR="nsys_reports"
OUTPUT_DIR="nsys_csv"

mkdir -p "$OUTPUT_DIR"

for file in "$INPUT_DIR"/*.nsys-rep; do
    # 取出不含副檔名的檔名
    base=$(basename "$file" .nsys-rep)
    output="$OUTPUT_DIR/$base.csv"
    
    echo "Converting $file → $output"
    nsys stats -r mpi_event_trace --format csv "$file" > "$output"
done

echo "✅ All reports converted to CSV in '$OUTPUT_DIR/'"
