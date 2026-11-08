"""
========================================================================================
模块名称: merge_excel_mapping.py
功能描述: 国家中医药标准代码 (A01/B01/C01) 与权威词汇别名融合引擎
依据标准: 国家卫生健康委与国家中医药管理局官方《中医病证分类与代码新旧映射表》
核心功能:
    1. 自动对齐 Excel 中的编号、国家新代码、原代码及规范可选用词。
    2. 无损注入现存的病、证、治三张实体表（JSONL 与 CSV）。
    3. 保留原有实体层次与定义，同时完成权威规范别名的去重合并。
========================================================================================
"""

import os
import re
import csv
import json
import logging
from pathlib import Path
from typing import Dict, List, Any
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("NationalCodeMapper")


def clean_code(val: Any) -> str:
    """清洗编号字符串，去除空白及浮点数末尾多余的 .0 符号。"""
    if pd.isna(val):
        return ""
    val_str = str(val).strip()
    return val_str[:-2] if val_str.endswith(".0") else val_str


def parse_aliases(alias_str: Any) -> List[str]:
    """解析包含多种标点分隔的别名词串，提取去重词汇列表。"""
    if pd.isna(alias_str) or not str(alias_str).strip():
        return []
    items = re.split(r"[;；,，、|]\s*", str(alias_str).strip())
    return [i.strip() for i in items if i.strip()]


def load_excel_sheet_mapping(excel_path: Path, sheet_name: str) -> Dict[str, Dict[str, Any]]:
    """
    解析 Excel 指定工作表并建立 {标准编号: 扩展属性映射} 索引。
    """
    logger.info(f"正在读取映射表 Sheet: [{sheet_name}]...")
    df = pd.read_excel(excel_path, sheet_name=sheet_name, dtype=str)

    col_code = None
    col_nat_code = None
    col_aliases = None
    col_old_code = None
    col_old_name = None

    for col in df.columns:
        c = str(col).strip()
        if "编号" in c:
            col_code = col
        elif "代码（修订版）" in c or "名代码（修订版）" in c:
            col_nat_code = col
        elif "可选用词" in c:
            col_aliases = col
        elif "代码（原）" in c:
            col_old_code = col
        elif "名（原）" in c:
            col_old_name = col

    mapping: Dict[str, Dict[str, Any]] = {}
    for _, row in df.iterrows():
        code_val = clean_code(row.get(col_code, ""))
        if not code_val:
            continue

        nat_code = str(row.get(col_nat_code, "")).strip() if col_nat_code and pd.notna(row.get(col_nat_code)) else ""
        alias_list = parse_aliases(row.get(col_aliases, "")) if col_aliases else []
        old_code = str(row.get(col_old_code, "")).strip() if col_old_code and pd.notna(row.get(col_old_code)) else ""
        old_name = str(row.get(col_old_name, "")).strip() if col_old_name and pd.notna(row.get(col_old_name)) else ""

        if old_name and old_name not in alias_list:
            alias_list.append(old_name)

        mapping[code_val] = {
            "national_code": nat_code,
            "excel_aliases": alias_list,
            "old_code": old_code
        }

    return mapping


def enrich_and_save(
    jsonl_in: Path,
    csv_out: Path,
    jsonl_out: Path,
    excel_mapping: Dict[str, Dict[str, Any]],
    id_prefix: str
) -> int:
    """将国家标准扩展属性注入现有实体文件并安全持久化。"""
    if not jsonl_in.exists():
        logger.warning(f"输入文件不存在，跳过本次融合: {jsonl_in}")
        return 0

    enriched_entities: List[Dict[str, Any]] = []

    with open(jsonl_in, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line.strip())

            raw_code = item["id"].replace(f"{id_prefix}_", "")
            extra = excel_mapping.get(raw_code, {})

            item["national_code"] = extra.get("national_code", "")
            item["old_code"] = extra.get("old_code", "")

            existing_aliases = set(item.get("aliases", []))
            excel_aliases = set(extra.get("excel_aliases", []))
            all_aliases = list(existing_aliases | excel_aliases)

            if item.get("name") in all_aliases:
                all_aliases.remove(item["name"])

            item["aliases"] = all_aliases
            enriched_entities.append(item)

    # 回写 JSONL
    with open(jsonl_out, "w", encoding="utf-8") as f:
        for ent in enriched_entities:
            f.write(json.dumps(ent, ensure_ascii=False) + "\n")

    # 回写 CSV
    with open(csv_out, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "id", "national_code", "name", "en_name", "is_category",
            "parent_id", "aliases", "old_code", "definition"
        ])
        for ent in enriched_entities:
            writer.writerow([
                ent["id"],
                ent.get("national_code", ""),
                ent.get("name", ""),
                ent.get("en_name", ""),
                ent.get("is_category", False),
                ent.get("parent_id", "") or "",
                "|".join(ent.get("aliases", [])),
                ent.get("old_code", ""),
                ent.get("definition", "")
            ])

    return len(enriched_entities)


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parents[1] if (script_dir.parents[1] / "原数据").exists() else Path(r"D:\中医系统")

    raw_dir = project_root / "原数据"
    excel_files = list(raw_dir.rglob("*.xlsx")) + list(raw_dir.rglob("*.xls"))
    if not excel_files:
        logger.error(f"未在 {raw_dir} 目录下找到国家代码映射表 (.xlsx)。")
        return

    excel_path = excel_files[0]
    logger.info(f"定位到国家映射表文件: {excel_path.name}")
    output_root = project_root / "生成出来的数据"

    tasks = [
        ("中医疾病映射表", "病", "DIS"),
        ("中医证候映射表", "证", "SYN"),
        ("中医治法映射表", "治", "PRN")
    ]

    for sheet_name, folder_name, prefix in tasks:
        try:
            excel_mapping = load_excel_sheet_mapping(excel_path, sheet_name)
            target_dir = output_root / folder_name
            file_key = "diseases" if folder_name == "病" else ("syndromes" if folder_name == "证" else "principles")

            jsonl_file = target_dir / f"entities_{file_key}.jsonl"
            csv_file = target_dir / f"entities_{file_key}.csv"

            count = enrich_and_save(jsonl_file, csv_file, jsonl_file, excel_mapping, prefix)
            logger.info(f"模块 [{folder_name}] 融合完成，更新实体记录 {count} 条。")
        except Exception as e:
            logger.error(f"处理工作表 [{sheet_name}] 时出现异常: {e}")


if __name__ == "__main__":
    main()