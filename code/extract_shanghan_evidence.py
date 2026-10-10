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

def extract_shanghan_knowledge():
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent.parent
    
    # 查找数据库
    db_candidates = list((project_root / "原数据" / "药").glob("*.db")) + list(project_root.rglob("tcm_knowledge.db"))
    if not db_candidates:
        print("❌ 未在 原数据/药/ 找到 .db 数据库文件！")
        return
        
    db_path = str(db_candidates[0])
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 输出目录：专门设立 古籍/伤寒杂病论/
    out_dir = project_root / "生成出来的数据" / "古籍" / "伤寒杂病论"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. 读取我们图谱现有的 593 首方剂名，作为实体对齐字典
    cursor.execute("SELECT id, name FROM formulas;")
    formula_dict = {clean_val(r['name']): f"FOR_{r['id']}" for r in cursor.fetchall()}
    
    # 2. 从表 10 (classics) 检索所有与《伤寒论》《金匮要略》相关的章节
    print("📖 正在检索《伤寒论》《金匮要略》古籍原文记录...")
    cursor.execute("""
        SELECT * FROM classics 
        WHERE book_name LIKE '%伤寒%' OR book_name LIKE '%金匮%'
        ORDER BY id;
    """)
    rows = cursor.fetchall()
    
    if not rows:
        print("⚠️ 未在 classics 表中找到伤寒相关记录，正在检查 books 表...")
        cursor.execute("SELECT * FROM books WHERE title LIKE '%伤寒%' OR title LIKE '%金匮%';")
        rows = cursor.fetchall()

    clauses = []
    triples_clause_formula = []
    
    clause_counter = 1
    
    # 正则表达式：匹配仲景经典的“...主之 / ...宜之”句式
    main_formula_pattern = re.compile(r'([一-龥]{2,12}(?:汤|散|丸|汤方|散方|丸方))(?:主之|宜之|加减法)')
    
    for raw_row in rows:
        # 转为标准 Python 字典，解决 .get() 报错
        row = dict(raw_row)
        
        book_name = clean_val(row.get('book_name') or row.get('title'))
        chapter_name = clean_val(row.get('chapter_name') or '正文')
        content = clean_val(row.get('content'))
        
        if not content:
            continue
            
        # 按段落划分条文
        raw_paragraphs = re.split(r'\n+|\r+', content)
        
        for p in raw_paragraphs:
            p_clean = p.strip().replace('#', '').strip()
            # 过滤太短的标题行
            if len(p_clean) < 15:
                continue
                
            # 搜索是否存在“某某方主之”
            match = main_formula_pattern.search(p_clean)
            if match:
                f_name = match.group(1).replace('方', '')  # 规范化：桂枝汤方 -> 桂枝汤
                
                clause_id = f"CLS_SHL_{clause_counter:04d}"
                clause_counter += 1
                
                clause_item = {
                    "id": clause_id,
                    "book": book_name,
                    "chapter": chapter_name,
                    "text": p_clean,
                    "prescribed_formula": f_name,
                    "matched_formula_id": formula_dict.get(f_name, "")
                }
                clauses.append(clause_item)
                
                # 建立三元组：【条文 ──指示方剂──> 方剂】
                if f_name in formula_dict:
                    triples_clause_formula.append({
                        "head": clause_id,
                        "relation": "PRESCRIBES_FORMULA",
                        "tail": formula_dict[f_name],
                        "rule": "仲景条文主之",
                        "formula_name": f_name
                    })

    conn.close()

    # 保存条文实体文件
    out_jsonl = out_dir / "entities_shanghan_clauses.jsonl"
    with open(out_jsonl, 'w', encoding='utf-8') as f:
        for c in clauses:
            f.write(json.dumps(c, ensure_ascii=False) + '\n')
            
    out_csv = out_dir / "entities_shanghan_clauses.csv"
    with open(out_csv, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["id", "book", "chapter", "text", "prescribed_formula", "matched_formula_id"])
        for c in clauses:
            writer.writerow([c["id"], c["book"], c["chapter"], c["text"], c["prescribed_formula"], c["matched_formula_id"]])

    # 保存三元组文件
    triple_csv = out_dir / "triples_clause_prescribes_formula.csv"
    with open(triple_csv, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["head", "relation", "tail", "rule", "formula_name"])
        for t in triples_clause_formula:
            writer.writerow([t["head"], t["relation"], t["tail"], t["rule"], t["formula_name"]])

    print("=" * 65)
    print(" 📖 《伤寒杂病论》仲景经方条文与主治关系提取完成！")
    print(f" 📄 解析得到【仲景经方条文】: {len(clauses)} 条")
    print(f" 🔗 成功构建【条文 ──主之/指示──> 方剂】硬核证据三元组: {len(triples_clause_formula)} 条！")
    print(f" 📁 结果已存入: {out_dir}")
    print("=" * 65)

if __name__ == "__main__":
    extract_shanghan_knowledge()