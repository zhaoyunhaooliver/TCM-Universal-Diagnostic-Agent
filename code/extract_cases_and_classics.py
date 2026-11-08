"""
========================================================================================
模块名称: extract_cases_and_classics.py
功能描述: 临床实战医案、古籍专著文献与经方推荐证候知识抽取引擎
数据来源: tcm_knowledge.db (包含 clinical_cases, case_formulas, case_herbs, classics, books)
输出资产:
    1. 经方代表证候实体库与【证候 ──RECOMMENDED_FORMULA──> 方剂】关系网络
    2. 1737 例临床四诊真实医案实体库与【医案 ──PRESCRIBED_FORMULA / USED_HERB──> 方药】关系网络
    3. 古籍经典专著与篇章全文实体库
========================================================================================
"""

import os
import re
import csv
import json
import sqlite3
import logging
from pathlib import Path
from typing import Dict, List, Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("CasesClassicsExtractor")


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


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parents[1] if (script_dir.parents[1] / "原数据").exists() else Path(r"D:\中医系统")

    db_candidates = list((project_root / "原数据" / "药").glob("*.db")) + list(project_root.rglob("tcm_knowledge.db"))
    if not db_candidates:
        logger.error("未在原数据目录下定位到 tcm_knowledge.db 数据库文件。")
        return

    db_path = str(db_candidates[0])
    logger.info(f"正在建立底层数据库连接: {Path(db_path).name}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    output_root = project_root / "生成出来的数据"
    syndrome_out_dir = output_root / "证"
    case_out_dir = output_root / "医案"
    classic_out_dir = output_root / "古籍"

    for d in [syndrome_out_dir, case_out_dir, classic_out_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # 建立方剂名称至 CURIE ID 的映射字典
    cursor.execute("SELECT id, name, alias FROM formulas;")
    formula_map: Dict[str, str] = {}
    for r in cursor.fetchall():
        f_id = f"FOR_{r['id']}"
        formula_map[clean_val(r["name"])] = f_id
        alias_str = clean_val(r["alias"])
        for a in re.split(r"[,，;；、|\s]", alias_str):
            if a.strip():
                formula_map[a.strip()] = f_id

    # -------------------------------------------------------------------------
    # 任务 1: 抽取经方证候与【证候 ──RECOMMENDED_FORMULA──> 方剂】关系三元组
    # -------------------------------------------------------------------------
    logger.info("正在抽取经方证候并建立推荐方剂关联拓扑...")
    cursor.execute("SELECT * FROM syndromes;")
    syndrome_rows = cursor.fetchall()

    syndrome_jf_entities: List[Dict[str, Any]] = []
    syndrome_formula_triples: List[Dict[str, str]] = []

    for r in syndrome_rows:
        s_id = f"SYN_JF_{r['id']}"
        name = clean_val(r["name"])
        rep_formulas = clean_val(r["representative_formulas"])

        syndrome_jf_entities.append({
            "id": s_id,
            "name": name,
            "six_channel": clean_val(r["six_channel"]),
            "eight_principles": clean_val(r["eight_principles"]),
            "location": clean_val(r["location"]),
            "core_symptoms": clean_val(r["core_symptoms"]),
            "key_differentiation": clean_val(r["key_differentiation"]),
            "representative_formulas": rep_formulas,
            "contraindication": clean_val(r["contraindication"])
        })

        if rep_formulas:
            for f_name in re.split(r"[,，;；、|\s/]\s*", rep_formulas):
                f_name_clean = f_name.strip()
                if f_name_clean in formula_map:
                    syndrome_formula_triples.append({
                        "head": s_id,
                        "relation": "RECOMMENDED_FORMULA",
                        "tail": formula_map[f_name_clean],
                        "formula_name": f_name_clean
                    })

    # -------------------------------------------------------------------------
    # 任务 2: 抽取临床实战医案库及处方用药网络
    # -------------------------------------------------------------------------
    logger.info("正在抽取临床真实医案及处方用药连线...")
    cursor.execute("SELECT * FROM clinical_cases;")
    cases_rows = cursor.fetchall()

    case_entities: List[Dict[str, Any]] = []
    for r in cases_rows:
        case_id = f"CASE_{r['id']}"
        case_entities.append({
            "id": case_id,
            "patient_tag": clean_val(r["patient_id"]),
            "case_date": clean_val(r["case_date"]),
            "gender": clean_val(r["gender"]),
            "age": clean_val(r["age"]),
            "chief_complaint": clean_val(r["chief_complaint"]),
            "inquiry": clean_val(r["inquiry"]),
            "pulse_diagnosis": clean_val(r["pulse_diagnosis"]),
            "tongue_diagnosis": clean_val(r["tongue_diagnosis"]),
            "eye_diagnosis": clean_val(r["eye_diagnosis"])
        })

    cursor.execute("SELECT * FROM case_formulas;")
    case_formula_triples = [
        {
            "head": f"CASE_{r['case_id']}",
            "relation": "PRESCRIBED_FORMULA",
            "tail": f"FOR_{r['formula_id']}",
            "is_acupuncture": clean_val(r["is_acupuncture"])
        }
        for r in cursor.fetchall()
    ]

    cursor.execute("SELECT * FROM case_herbs;")
    case_herb_triples = [
        {
            "head": f"CASE_{r['case_id']}",
            "relation": "USED_HERB",
            "tail": f"HRB_{r['herb_id']}",
            "dosage": clean_val(r["dosage"]),
            "note": clean_val(r["note"])
        }
        for r in cursor.fetchall()
    ]

    # -------------------------------------------------------------------------
    # 任务 3: 抽取古籍专著及篇章文献
    # -------------------------------------------------------------------------
    logger.info("正在构建经典文献专著实体库...")
    cursor.execute("SELECT * FROM classics;")
    classics_entities: List[Dict[str, Any]] = [
        {
            "id": f"CLS_{r['id']}",
            "book_name": clean_val(r["book_name"]),
            "chapter_name": clean_val(r["chapter_name"]),
            "chapter_num": clean_val(r["chapter_num"]),
            "content": clean_val(r["content"]),
            "annotation": clean_val(r["annotation"]),
            "word_count": clean_val(r["word_count"])
        }
        for r in cursor.fetchall()
    ]

    cursor.execute("SELECT * FROM books;")
    for r in cursor.fetchall():
        classics_entities.append({
            "id": f"BOOK_{r['id']}",
            "book_name": clean_val(r["title"]),
            "chapter_name": "全本",
            "chapter_num": "全本",
            "content": clean_val(r["content"]),
            "annotation": f"作者:{clean_val(r['author'])} | 分类:{clean_val(r['category'])}",
            "word_count": clean_val(r["word_count"])
        })

    conn.close()

    # -------------------------------------------------------------------------
    # 资产持久化
    # -------------------------------------------------------------------------
    write_jsonl(syndrome_out_dir / "entities_syndromes_jingfang.jsonl", syndrome_jf_entities)
    write_csv(
        syndrome_out_dir / "triples_syndrome_recommended_formulas.csv",
        ["head", "relation", "tail", "formula_name"],
        [[t["head"], t["relation"], t["tail"], t["formula_name"]] for t in syndrome_formula_triples]
    )

    write_jsonl(case_out_dir / "entities_clinical_cases.jsonl", case_entities)
    write_csv(
        case_out_dir / "entities_clinical_cases.csv",
        ["id", "patient_tag", "case_date", "gender", "age", "chief_complaint", "inquiry", "pulse_diagnosis", "tongue_diagnosis"],
        [[c["id"], c["patient_tag"], c["case_date"], c["gender"], c["age"], c["chief_complaint"], c["inquiry"][:100], c["pulse_diagnosis"], c["tongue_diagnosis"]] for c in case_entities]
    )
    write_csv(
        case_out_dir / "triples_case_prescribed_formulas.csv",
        ["head", "relation", "tail", "is_acupuncture"],
        [[t["head"], t["relation"], t["tail"], t["is_acupuncture"]] for t in case_formula_triples]
    )
    write_csv(
        case_out_dir / "triples_case_used_herbs.csv",
        ["head", "relation", "tail", "dosage", "note"],
        [[t["head"], t["relation"], t["tail"], t["dosage"], t["note"]] for t in case_herb_triples]
    )

    write_jsonl(classic_out_dir / "entities_ancient_classics.jsonl", classics_entities)

    logger.info(
        f"提取任务完成: 证候推荐方连线 {len(syndrome_formula_triples)} 条，"
        f"医案实体 {len(case_entities)} 例（处方连线 {len(case_formula_triples)} 条，用药连线 {len(case_herb_triples)} 条），"
        f"古籍篇章 {len(classics_entities)} 篇。"
    )


if __name__ == "__main__":
    main()