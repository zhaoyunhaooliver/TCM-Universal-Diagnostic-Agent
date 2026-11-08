"""
========================================================================================
模块名称: extract_tcm_db.py
功能描述: 基础中药实体库、临床症状库及证候主症拓扑网络构建引擎
核心安全机制:
    防冲突保护 (Schema Guard): 检查已存在的 entities_formulas.csv 是否为宋本经方
    高精度版本。若已由 batch_extract_all_formulas.py 生成，则保留其成果，
    避免被数据库旧格式覆写。
输出资产:
    1. 中药实体库 (entities_herbs.csv / jsonl)
    2. 临床症状实体库 (entities_symptoms.csv / jsonl)
    3. 证候主症关系网络 (triples_syndrome_symptoms.csv / jsonl)
========================================================================================
"""

import os
import re
import csv
import json
import sqlite3
import logging
from pathlib import Path
from typing import Dict, List, Set, Any, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("TCM_BaseData_Extractor")


def clean_val(val: Any) -> str:
    """清洗字段中的空值与异常字符，返回标准去首尾空格字符串。"""
    if val is None:
        return ""
    s = str(val).strip()
    return "" if s.upper() in ["NONE", "NULL", "NA", ""] else s


def write_jsonl(path: Path, data_list: List[Dict[str, Any]]) -> None:
    """持久化保存为标准 JSONL 格式。"""
    with open(path, "w", encoding="utf-8") as f:
        for item in data_list:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def write_csv(path: Path, headers: List[str], rows: List[List[Any]]) -> None:
    """持久化保存为标准带 BOM UTF-8 CSV 格式。"""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def extract_database() -> None:
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parents[1] if (script_dir.parents[1] / "原数据").exists() else Path(r"D:\中医系统")

    db_candidates = list((project_root / "原数据" / "药").glob("*.db")) + list(project_root.rglob("tcm_knowledge.db"))
    if not db_candidates:
        logger.error("未在原数据目录下定位到 tcm_knowledge.db 数据库文件。")
        return

    db_path = str(db_candidates[0])
    logger.info(f"正在读取底层知识库: {Path(db_path).name}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    output_root = project_root / "生成出来的数据"
    herb_out_dir = output_root / "中药"
    formula_out_dir = output_root / "方剂"
    symptom_out_dir = output_root / "症状"
    syndrome_out_dir = output_root / "证"

    for d in [herb_out_dir, formula_out_dir, symptom_out_dir, syndrome_out_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # 1. 抽取基础中药实体库 (herbs)
    # -------------------------------------------------------------------------
    logger.info("正在抽取中药标准实体数据 (herbs)...")
    cursor.execute("SELECT * FROM herbs;")
    herb_rows = cursor.fetchall()

    herbs_dict: Dict[str, str] = {}
    herb_entities: List[Dict[str, Any]] = []

    for row in herb_rows:
        h_id = f"HRB_{row['id']}"
        name = clean_val(row["name"])
        if not name:
            continue

        herbs_dict[name] = h_id
        alias_str = clean_val(row["alias"])
        aliases = [a.strip() for a in re.split(r"[,，;；、|\s]", alias_str) if a.strip()]
        for a in aliases:
            herbs_dict[a] = h_id

        herb_entities.append({
            "id": h_id,
            "name": name,
            "aliases": aliases,
            "category": clean_val(row["category"]),
            "nature": clean_val(row["nature"]),
            "flavor": clean_val(row["flavor"]),
            "toxicity": clean_val(row["toxicity"]),
            "meridian_tropism": clean_val(row["meridian_tropism"]),
            "origin": clean_val(row["origin"]),
            "indication": clean_val(row["indication"])
        })

    # -------------------------------------------------------------------------
    # 2. 方剂实体与配伍防冲安全判定 (Schema Guard)
    # -------------------------------------------------------------------------
    target_formula_csv = formula_out_dir / "entities_formulas.csv"
    is_song_edition_present = False
    if target_formula_csv.exists():
        with open(target_formula_csv, "r", encoding="utf-8-sig") as f:
            header = f.readline()
            if "usage_info" in header and "clause_text" in header:
                is_song_edition_present = True

    if is_song_edition_present:
        logger.info(
            "检测到已存在宋本高精度经方库 (含 usage_info 与 clause_text)，"
            "为确保经方原旨纯正性，本模块跳过对方剂主表的覆写。"
        )
    else:
        logger.info("正在初始化基础方剂实体库 (formulas)...")
        cursor.execute("SELECT * FROM formulas;")
        formula_entities = [
            {
                "id": f"FOR_{row['id']}",
                "name": clean_val(row["name"]),
                "aliases": [a.strip() for a in re.split(r"[,，;；、|\s]", clean_val(row["alias"])) if a.strip()],
                "source_book": clean_val(row["source_book"]),
                "chapter": clean_val(row["chapter"]),
                "six_channel": clean_val(row["six_channel"]),
                "syndrome": clean_val(row["syndrome"]),
                "indication": clean_val(row["indication"]),
                "composition": clean_val(row["composition"]),
                "dosage": clean_val(row["dosage"])
            }
            for row in cursor.fetchall() if clean_val(row["name"])
        ]
        write_jsonl(formula_out_dir / "entities_formulas.jsonl", formula_entities)
        write_csv(
            formula_out_dir / "entities_formulas.csv",
            ["id", "name", "aliases", "source_book", "chapter", "six_channel", "syndrome", "indication", "composition", "dosage"],
            [[e["id"], e["name"], "|".join(e["aliases"]), e["source_book"], e["chapter"], e["six_channel"], e["syndrome"], e["indication"], e["composition"], e["dosage"]] for e in formula_entities]
        )

    # -------------------------------------------------------------------------
    # 3. 抽取临床症状库与证症三元组 (syndrome_symptoms)
    # -------------------------------------------------------------------------
    logger.info("正在抽取临床症状库及证候主症拓扑关系...")
    cursor.execute("SELECT * FROM symptoms;")
    symptom_entities = [
        {
            "id": f"SYM_{row['id']}",
            "name": clean_val(row["name"]),
            "category": clean_val(row["category"]),
            "description": clean_val(row["description"]),
            "first_gateway": clean_val(row["first_gateway"]),
            "differential": clean_val(row["differential"])
        }
        for row in cursor.fetchall() if clean_val(row["name"])
    ]

    cursor.execute("SELECT * FROM syndrome_symptoms;")
    syndrome_symptom_triples = [
        {
            "head": f"SYN_DB_{row['syndrome_id']}",
            "relation": "HAS_CORE_SYMPTOM" if clean_val(row["is_key"]) == "1" else "HAS_SECONDARY_SYMPTOM",
            "tail": f"SYM_{row['symptom_id']}"
        }
        for row in cursor.fetchall()
    ]

    conn.close()

    # -------------------------------------------------------------------------
    # 资产持久化
    # -------------------------------------------------------------------------
    write_jsonl(herb_out_dir / "entities_herbs.jsonl", herb_entities)
    write_csv(
        herb_out_dir / "entities_herbs.csv",
        ["id", "name", "aliases", "category", "nature", "flavor", "toxicity", "meridian_tropism", "origin", "indication"],
        [[e["id"], e["name"], "|".join(e["aliases"]), e["category"], e["nature"], e["flavor"], e["toxicity"], e["meridian_tropism"], e["origin"], e["indication"]] for e in herb_entities]
    )

    write_jsonl(symptom_out_dir / "entities_symptoms.jsonl", symptom_entities)
    write_csv(
        symptom_out_dir / "entities_symptoms.csv",
        ["id", "name", "category", "first_gateway", "differential"],
        [[e["id"], e["name"], e["category"], e["first_gateway"], e["differential"]] for e in symptom_entities]
    )

    write_jsonl(syndrome_out_dir / "triples_syndrome_symptoms.jsonl", syndrome_symptom_triples)
    write_csv(
        syndrome_out_dir / "triples_syndrome_symptoms.csv",
        ["head", "relation", "tail"],
        [[t["head"], t["relation"], t["tail"]] for t in syndrome_symptom_triples]
    )

    logger.info(
        f"底层基础资产抽取完毕: 中药实体 {len(herb_entities)} 味，"
        f"临床症状 {len(symptom_entities)} 个，证症关联连线 {len(syndrome_symptom_triples)} 条。"
    )


if __name__ == "__main__":
    extract_database()