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

def extract_database():
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent.parent
    
    # 定位数据库路径
    db_candidates = list((project_root / "原数据" / "药").glob("*.db")) + list(project_root.rglob("tcm_knowledge.db"))
    if not db_candidates:
        print("❌ 未在 原数据/药/ 找到 .db 数据库文件！")
        return
        
    db_path = str(db_candidates[0])
    print(f"📖 正在读取数据库: {db_path}")
    
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
        
    # ==========================================
    # 1. 提取中药表 (herbs)
    # ==========================================
    print("🌿 [1/4] 正在提取中药实体数据 (herbs)...")
    cursor.execute("SELECT * FROM herbs;")
    herb_rows = cursor.fetchall()
    
    herbs_dict = {}  # {name: id} 用于后续方剂文本中药匹配
    herb_entities = []
    
    for row in herb_rows:
        h_id = f"HRB_{row['id']}"
        name = clean_val(row['name'])
        if not name:
            continue
            
        herbs_dict[name] = h_id
        alias_str = clean_val(row['alias'])
        aliases = [a.strip() for a in re.split(r'[,，;；、|\s]', alias_str) if a.strip()]
        for a in aliases:
            herbs_dict[a] = h_id
            
        entity = {
            "id": h_id,
            "name": name,
            "aliases": aliases,
            "category": clean_val(row['category']),
            "nature": clean_val(row['nature']),
            "flavor": clean_val(row['flavor']),
            "toxicity": clean_val(row['toxicity']),
            "meridian_tropism": clean_val(row['meridian_tropism']),
            "origin": clean_val(row['origin']),
            "indication": clean_val(row['indication'])
        }
        herb_entities.append(entity)
        
    # ==========================================
    # 2. 提取方剂表 (formulas)
    # ==========================================
    print("💊 [2/4] 正在提取方剂实体数据 (formulas)...")
    cursor.execute("SELECT * FROM formulas;")
    formula_rows = cursor.fetchall()
    
    formula_entities = []
    for row in formula_rows:
        f_id = f"FOR_{row['id']}"
        name = clean_val(row['name'])
        if not name:
            continue
            
        alias_str = clean_val(row['alias'])
        aliases = [a.strip() for a in re.split(r'[,，;；、|\s]', alias_str) if a.strip()]
        
        entity = {
            "id": f_id,
            "name": name,
            "aliases": aliases,
            "source_book": clean_val(row['source_book']),
            "chapter": clean_val(row['chapter']),
            "six_channel": clean_val(row['six_channel']),
            "syndrome": clean_val(row['syndrome']),
            "indication": clean_val(row['indication']),
            "composition": clean_val(row['composition']),
            "dosage": clean_val(row['dosage'])
        }
        formula_entities.append(entity)
        
    # ==========================================
    # 3. 构建【方剂 ──包含──> 中药】核心三元组 (核心步骤)
    # ==========================================
    print("🔗 [3/4] 正在构建【方剂 ──包含──> 中药】配伍三元组...")
    formula_herb_triples = []
    existing_pairs = set()
    
    # 3.1 从数据库现存关系表提取 (优先保留已有角色/剂量信息)
    cursor.execute("SELECT * FROM formula_herbs;")
    for row in cursor.fetchall():
        f_id = f"FOR_{row['formula_id']}"
        h_id = f"HRB_{row['herb_id']}"
        role = clean_val(row['role'])
        dose = clean_val(row['dosage_in_formula'])
        
        pair_key = (f_id, h_id)
        if pair_key not in existing_pairs:
            existing_pairs.add(pair_key)
            formula_herb_triples.append({
                "head": f_id,
                "relation": "CONTAINS_HERB",
                "tail": h_id,
                "role": role if role != "未知" else "",
                "dosage": dose
            })
            
    # 3.2 逆向扫描每首方剂的 composition 组成文本，弥补遗漏的中药
    # 按药名长度降序排列，避免“甘草”覆盖“炙甘草”
    sorted_herb_names = sorted(herbs_dict.keys(), key=lambda x: len(x), reverse=True)
    
    for f in formula_entities:
        f_id = f["id"]
        comp_text = f["composition"]
        if not comp_text:
            continue
            
        matched_herbs = []
        text_to_scan = comp_text
        for h_name in sorted_herb_names:
            if len(h_name) < 2:  # 跳过单字避免误伤
                continue
            if h_name in text_to_scan:
                h_id = herbs_dict[h_name]
                pair_key = (f_id, h_id)
                if pair_key not in existing_pairs:
                    existing_pairs.add(pair_key)
                    formula_herb_triples.append({
                        "head": f_id,
                        "relation": "CONTAINS_HERB",
                        "tail": h_id,
                        "role": "",
                        "dosage": ""
                    })
                # 扫描后临时遮盖，避免子词重复触发
                text_to_scan = text_to_scan.replace(h_name, " ")

    # ==========================================
    # 4. 提取【症状】与【证候 ──具备主症──> 症状】三元组
    # ==========================================
    print("🩺 [4/4] 正在提取高价值证症关系 (syndrome_symptoms)...")
    cursor.execute("SELECT * FROM symptoms;")
    symptom_entities = []
    for row in cursor.fetchall():
        s_id = f"SYM_{row['id']}"
        name = clean_val(row['name'])
        if not name:
            continue
        symptom_entities.append({
            "id": s_id,
            "name": name,
            "category": clean_val(row['category']),
            "description": clean_val(row['description']),
            "first_gateway": clean_val(row['first_gateway']),
            "differential": clean_val(row['differential'])
        })
        
    cursor.execute("SELECT * FROM syndrome_symptoms;")
    syndrome_symptom_triples = []
    for row in cursor.fetchall():
        syn_id = f"SYN_DB_{row['syndrome_id']}"
        sym_id = f"SYM_{row['symptom_id']}"
        is_key = clean_val(row['is_key']) == '1'
        
        syndrome_symptom_triples.append({
            "head": syn_id,
            "relation": "HAS_CORE_SYMPTOM" if is_key else "HAS_SECONDARY_SYMPTOM",
            "tail": sym_id
        })

    conn.close()

    # ==========================================
    # 写入文件
    # ==========================================
    # 1. 中药实体
    write_jsonl(herb_out_dir / "entities_herbs.jsonl", herb_entities)
    write_csv(herb_out_dir / "entities_herbs.csv", [
        "id", "name", "aliases", "category", "nature", "flavor", "toxicity", "meridian_tropism", "origin", "indication"
    ], [[e["id"], e["name"], "|".join(e["aliases"]), e["category"], e["nature"], e["flavor"], e["toxicity"], e["meridian_tropism"], e["origin"], e["indication"]] for e in herb_entities])
    
    # 2. 方剂实体
    write_jsonl(formula_out_dir / "entities_formulas.jsonl", formula_entities)
    write_csv(formula_out_dir / "entities_formulas.csv", [
        "id", "name", "aliases", "source_book", "chapter", "six_channel", "syndrome", "indication", "composition", "dosage"
    ], [[e["id"], e["name"], "|".join(e["aliases"]), e["source_book"], e["chapter"], e["six_channel"], e["syndrome"], e["indication"], e["composition"], e["dosage"]] for e in formula_entities])
    
    # 3. 方药组成三元组
    write_jsonl(formula_out_dir / "triples_formula_contains_herb.jsonl", formula_herb_triples)
    write_csv(formula_out_dir / "triples_formula_contains_herb.csv", [
        "head", "relation", "tail", "role", "dosage"
    ], [[t["head"], t["relation"], t["tail"], t.get("role", ""), t.get("dosage", "")] for t in formula_herb_triples])
    
    # 4. 症状实体
    write_jsonl(symptom_out_dir / "entities_symptoms.jsonl", symptom_entities)
    write_csv(symptom_out_dir / "entities_symptoms.csv", [
        "id", "name", "category", "first_gateway", "differential"
    ], [[e["id"], e["name"], e["category"], e["first_gateway"], e["differential"]] for e in symptom_entities])

    # 5. 证症三元组
    write_jsonl(syndrome_out_dir / "triples_syndrome_symptoms.jsonl", syndrome_symptom_triples)
    write_csv(syndrome_out_dir / "triples_syndrome_symptoms.csv", [
        "head", "relation", "tail"
    ], [[t["head"], t["relation"], t["tail"]] for t in syndrome_symptom_triples])

    print("\n" + "=" * 60)
    print(" 🎉 恭喜！数据库核心资产已全面提取与贯通：")
    print(f" 🌿 中药实体 (herbs): {len(herb_entities)} 味 (保存在 生成出来的数据/中药/)")
    print(f" 💊 方剂实体 (formulas): {len(formula_entities)} 首 (保存在 生成出来的数据/方剂/)")
    print(f" 🔗 【方剂 ──包含──> 中药】配伍连线: {len(formula_herb_triples)} 条！")
    print(f" 🩺 症状实体 (symptoms): {len(symptom_entities)} 个 (保存在 生成出来的数据/症状/)")
    print(f" 🎯 【证候 ──具备主症──> 症状】实战连线: {len(syndrome_symptom_triples)} 条！")
    print("=" * 60)

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
    extract_database()
