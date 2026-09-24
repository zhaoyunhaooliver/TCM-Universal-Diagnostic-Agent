import os
import re
import json
import csv
import pandas as pd
from pathlib import Path

def clean_code(val):
    """清洗编号字符串，去除空白和浮点数多余的.0"""
    if pd.isna(val):
        return ""
    val_str = str(val).strip()
    if val_str.endswith('.0'):
        val_str = val_str[:-2]
    return val_str

def parse_aliases(alias_str):
    """解析以分号、逗号隔开的别名字符串"""
    if pd.isna(alias_str) or not str(alias_str).strip():
        return []
    # 支持中英文分号、逗号切分
    items = re.split(r'[;；,，、|]\s*', str(alias_str).strip())
    return [i.strip() for i in items if i.strip()]

def load_excel_sheet_mapping(excel_path, sheet_name):
    """
    读取 Excel 对应 Sheet，建立 {编号: 扩展信息} 映射字典
    """
    print(f"  📊 正在读取 Sheet: [{sheet_name}] ...")
    df = pd.read_excel(excel_path, sheet_name=sheet_name, dtype=str)
    
    # 自动识别列名（模糊匹配）
    col_code = None        # 编号（如 2.1.1）
    col_nat_code = None    # 国家新代码（如 A01.01.01 / B01...）
    col_aliases = None     # 可选用词
    col_old_code = None    # 原代码
    col_old_name = None    # 原名称
    
    for col in df.columns:
        c = str(col).strip()
        if '编号' in c:
            col_code = col
        elif '代码（修订版）' in c or '名代码（修订版）' in c:
            col_nat_code = col
        elif '可选用词' in c:
            col_aliases = col
        elif '代码（原）' in c:
            col_old_code = col
        elif '名（原）' in c:
            col_old_name = col
            
    mapping = {}
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

def enrich_and_save(jsonl_in, csv_out, jsonl_out, excel_mapping, id_prefix):
    """将 Excel 字段合并到现有的实体表中"""
    if not os.path.exists(jsonl_in):
        print(f"⚠️ 未找到输入文件: {jsonl_in}，跳过此项。")
        return 0
        
    enriched_entities = []
    
    with open(jsonl_in, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line.strip())
            
            # 从 ID 中反推章节编号（如 "SYN_2.10.1.1" -> "2.10.1.1"）
            raw_code = item["id"].replace(f"{id_prefix}_", "")
            
            # 在 Excel 中查找补充属性
            extra = excel_mapping.get(raw_code, {})
            
            item["national_code"] = extra.get("national_code", "")
            item["old_code"] = extra.get("old_code", "")
            
            # 合并别名并去重
            existing_aliases = set(item.get("aliases", []))
            excel_aliases = set(extra.get("excel_aliases", []))
            all_aliases = list(existing_aliases | excel_aliases)
            
            # 去除与名称重复的别名
            if item.get("name") in all_aliases:
                all_aliases.remove(item["name"])
                
            item["aliases"] = all_aliases
            enriched_entities.append(item)
            
    # 覆盖写回 JSONL
    with open(jsonl_out, 'w', encoding='utf-8') as f:
        for ent in enriched_entities:
            f.write(json.dumps(ent, ensure_ascii=False) + '\n')
            
    # 覆盖写回 CSV
    with open(csv_out, 'w', encoding='utf-8-sig', newline='') as f:
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

def main():
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent.parent  # 中医系统/
    
    # 查找 Excel 文件（优先查找 原数据/ 下的所有 .xlsx 文件）
    raw_dir = project_root / "原数据"
    excel_files = list(raw_dir.rglob("*.xlsx")) + list(raw_dir.rglob("*.xls"))
    
    if not excel_files:
        print(f"❌ 未在 {raw_dir} 及其子目录下找到任何 Excel 映射表文件 (.xlsx)！")
        return
        
    excel_path = str(excel_files[0])
    print(f"📖 发现 Excel 映射表文件: {excel_path}")
    
    output_root = project_root / "生成出来的数据"
    
    # 任务配置表：(Sheet名称, 对应文件夹, ID前缀)
    tasks = [
        ("中医疾病映射表", "病", "DIS"),
        ("中医证候映射表", "证", "SYN"),
        ("中医治法映射表", "治", "PRN")
    ]
    
    print("\n🚀 开始全量融合 Excel 国家代码与别名数据...")
    
    for sheet_name, folder_name, prefix in tasks:
        try:
            excel_mapping = load_excel_sheet_mapping(excel_path, sheet_name)
            
            target_dir = output_root / folder_name
            # 文件名匹配
            file_key = "diseases" if folder_name == "病" else ("syndromes" if folder_name == "证" else "principles")
            
            jsonl_file = target_dir / f"entities_{file_key}.jsonl"
            csv_file = target_dir / f"entities_{file_key}.csv"
            
            count = enrich_and_save(
                str(jsonl_file), 
                str(csv_file), 
                str(jsonl_file), 
                excel_mapping, 
                prefix
            )
            print(f"  ✅ [{folder_name}] 融合完成，更新了 {count} 条实体数据！")
        except Exception as e:
            print(f"  ⚠️ 处理 [{sheet_name}] 出错: {e}")
            
    print("\n" + "=" * 55)
    print(" 🎉 恭喜！病、证、治三张表已全部注入国家标准代码与权威别名！")
    print("=" * 55)

if __name__ == "__main__":
    main()
