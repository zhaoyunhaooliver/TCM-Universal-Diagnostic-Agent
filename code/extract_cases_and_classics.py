import os
import re
import json
import csv
import sqlite3
from pathlib import Path

def clean_val(val):
    if val is None or str(val).strip().upper() in ['NONE', 'NULL', 'NA', '']:
        return ""
    return str(val).strip()

def main():
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent.parent
    
    # 定位数据库
    db_candidates = list((project_root / "原数据" / "药").glob("*.db")) + list(project_root.rglob("tcm_knowledge.db"))
    if not db_candidates:
        print("❌ 未在 原数据/药/ 找到 .db 数据库文件！")
        return
        
    db_path = str(db_candidates[0])
    print(f"📖 正在最后深度榨取数据库: {Path(db_path).name}")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    output_root = project_root / "生成出来的数据"
    syndrome_out_dir = output_root / "证"
    case_out_dir = output_root / "医案"
    classic_out_dir = output_root / "古籍"
    
    for d in [syndrome_out_dir, case_out_dir, classic_out_dir]:
        d.mkdir(parents=True, exist_ok=True)
        
    # 读取已有的 593 首方剂字典（用于代表方精准匹配）
    cursor.execute("SELECT id, name, alias FROM formulas;")
    formula_map = {}
    for r in cursor.fetchall():
        f_id = f"FOR_{r['id']}"
        formula_map[clean_val(r['name'])] = f_id
        alias_str = clean_val(r['alias'])
        for a in re.split(r'[,，;；、|\s]', alias_str):
            if a.strip():
                formula_map[a.strip()] = f_id

    # =========================================================================
    # 任务 1：提取经方证候与【证候 ──推荐代表方──> 方剂】核心三元组 (表 4)
    # =========================================================================
    print("🎯 [1/3] 正在构建【证候 ──推荐代表方──> 方剂】核心桥梁三元组...")
    cursor.execute("SELECT * FROM syndromes;")
    syndrome_rows = cursor.fetchall()
    
    syndrome_jf_entities = []
    syndrome_formula_triples = []
    
    for r in syndrome_rows:
        s_id = f"SYN_JF_{r['id']}"
        name = clean_val(r['name'])
        rep_formulas = clean_val(r['representative_formulas'])
        
        syndrome_jf_entities.append({
            "id": s_id,
            "name": name,
            "six_channel": clean_val(r['six_channel']),
            "eight_principles": clean_val(r['eight_principles']),
            "location": clean_val(r['location']),
            "core_symptoms": clean_val(r['core_symptoms']),
            "key_differentiation": clean_val(r['key_differentiation']),
            "representative_formulas": rep_formulas,
            "contraindication": clean_val(r['contraindication'])
        })
        
        # 匹配代表方并建立三元组
        if rep_formulas:
            # 兼容各种分隔符
            for f_name in re.split(r'[,，;；、|\s/]\s*', rep_formulas):
                f_name = f_name.strip()
                if f_name in formula_map:
                    syndrome_formula_triples.append({
                        "head": s_id,
                        "relation": "RECOMMENDED_FORMULA",
                        "tail": formula_map[f_name],
                        "formula_name": f_name
                    })
                    
    # =========================================================================
    # 任务 2：提取 1737 例真实经典医案库 (表 7, 19, 20)
    # =========================================================================
    print("📋 [2/3] 正在提取 1737 例真实经典实战医案...")
    cursor.execute("SELECT * FROM clinical_cases;")
    cases_rows = cursor.fetchall()
    
    case_entities = []
    for r in cases_rows:
        case_id = f"CASE_{r['id']}"
        case_entities.append({
            "id": case_id,
            "patient_tag": clean_val(r['patient_id']),
            "case_date": clean_val(r['case_date']),
            "gender": clean_val(r['gender']),
            "age": clean_val(r['age']),
            "chief_complaint": clean_val(r['chief_complaint']),
            "inquiry": clean_val(r['inquiry']),
            "pulse_diagnosis": clean_val(r['pulse_diagnosis']),
            "tongue_diagnosis": clean_val(r['tongue_diagnosis']),
            "eye_diagnosis": clean_val(r['eye_diagnosis'])
        })
        
    # 提取医案与处方的连线 (表 19)
    cursor.execute("SELECT * FROM case_formulas;")
    case_formula_triples = []
    for r in cursor.fetchall():
        case_formula_triples.append({
            "head": f"CASE_{r['case_id']}",
            "relation": "PRESCRIBED_FORMULA",
            "tail": f"FOR_{r['formula_id']}",
            "is_acupuncture": clean_val(r['is_acupuncture'])
        })
        
    # 提取医案与用药的连线 (表 20)
    cursor.execute("SELECT * FROM case_herbs;")
    case_herb_triples = []
    for r in cursor.fetchall():
        case_herb_triples.append({
            "head": f"CASE_{r['case_id']}",
            "relation": "USED_HERB",
            "tail": f"HRB_{r['herb_id']}",
            "dosage": clean_val(r['dosage']),
            "note": clean_val(r['note'])
        })

    # =========================================================================
    # 任务 3：提取古籍经典章节与历代专著 (表 10, 12)
    # =========================================================================
    print("📚 [3/3] 正在整理古籍经典全文库（黄帝内经/伤寒论/石室秘录等）...")
    cursor.execute("SELECT * FROM classics;")
    classics_rows = cursor.fetchall()
    
    classics_entities = []
    for r in classics_rows:
        classics_entities.append({
            "id": f"CLS_{r['id']}",
            "book_name": clean_val(r['book_name']),
            "chapter_name": clean_val(r['chapter_name']),
            "chapter_num": clean_val(r['chapter_num']),
            "content": clean_val(r['content']),
            "annotation": clean_val(r['annotation']),
            "word_count": clean_val(r['word_count'])
        })
        
    cursor.execute("SELECT * FROM books;")
    for r in cursor.fetchall():
        classics_entities.append({
            "id": f"BOOK_{r['id']}",
            "book_name": clean_val(r['title']),
            "chapter_name": "全本",
            "chapter_num": "全本",
            "content": clean_val(r['content']),
            "annotation": f"作者:{clean_val(r['author'])} | 分类:{clean_val(r['category'])}",
            "word_count": clean_val(r['word_count'])
        })

    conn.close()

    # =========================================================================
    # 保存所有文件
    # =========================================================================
    # 1. 经方证候与代表方三元组
    write_jsonl(syndrome_out_dir / "entities_syndromes_jingfang.jsonl", syndrome_jf_entities)
    write_csv(syndrome_out_dir / "triples_syndrome_recommended_formulas.csv", 
              ["head", "relation", "tail", "formula_name"],
              [[t["head"], t["relation"], t["tail"], t["formula_name"]] for t in syndrome_formula_triples])
    
    # 2. 医案实体与用药用方关系
    write_jsonl(case_out_dir / "entities_clinical_cases.jsonl", case_entities)
    write_csv(case_out_dir / "entities_clinical_cases.csv",
              ["id", "patient_tag", "case_date", "gender", "age", "chief_complaint", "inquiry", "pulse_diagnosis", "tongue_diagnosis"],
              [[c["id"], c["patient_tag"], c["case_date"], c["gender"], c["age"], c["chief_complaint"], c["inquiry"][:100], c["pulse_diagnosis"], c["tongue_diagnosis"]] for c in case_entities])
    write_csv(case_out_dir / "triples_case_prescribed_formulas.csv",
              ["head", "relation", "tail", "is_acupuncture"],
              [[t["head"], t["relation"], t["tail"], t["is_acupuncture"]] for t in case_formula_triples])
    write_csv(case_out_dir / "triples_case_used_herbs.csv",
              ["head", "relation", "tail", "dosage", "note"],
              [[t["head"], t["relation"], t["tail"], t["dosage"], t["note"]] for t in case_herb_triples])
              
    # 3. 古籍经典
    write_jsonl(classic_out_dir / "entities_ancient_classics.jsonl", classics_entities)

    print("\n" + "=" * 65)
    print(" 🏆 数据库最终深度榨取全部搞定！生成资产概览：")
    print(f" 🎯 【证候 ──推荐首选方──> 方剂】连线: {len(syndrome_formula_triples)} 条！")
    print(f" 📋 真实门诊实战医案 (clinical_cases): {len(case_entities)} 例！")
    print(f"    ├─ 医案 ──处方连线: {len(case_formula_triples)} 条")
    print(f"    └─ 医案 ──实战用药连线: {len(case_herb_triples)} 条")
    print(f" 📚 经典古籍章节与专著 (classics): {len(classics_entities)} 篇！")
    print("=" * 65)

def write_jsonl(path, data_list):
    with open(path, 'w', encoding='utf-8') as f:
        for item in data_list:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')

def write_csv(path, headers, rows):
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

if __name__ == "__main__":
    main()
