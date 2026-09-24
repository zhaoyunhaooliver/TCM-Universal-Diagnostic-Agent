import os
import re
import json
import csv
from pathlib import Path

# 尝试导入 python-docx
try:
    import docx
except ImportError:
    docx = None

def get_paragraphs_from_docx(file_path):
    """读取 docx 文件段落"""
    if docx is None:
        raise ImportError("请先安装 python-docx 库：pip install python-docx")
    doc = docx.Document(file_path)
    return [p.text.strip() for p in doc.paragraphs if p.text.strip()]

def get_paragraphs_from_txt(file_path):
    """读取 txt 文件段落（备用支持）"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def split_zh_en(text):
    """分离中文名称和英文名称"""
    match = re.search(r'[a-zA-Z]', text)
    if match:
        idx = match.start()
        zh_part = text[:idx].strip()
        en_part = text[idx:].strip()
        return zh_part, en_part
    return text.strip(), ""

def finalize_item(item):
    """整理待定行，分离名字、别名、定义"""
    lines = item["pending_lines"]
    
    idx = 0
    # 提取名称与英文
    if not item["name"] and len(lines) > 0:
        zh_name, en_name = split_zh_en(lines[0])
        item["name"] = zh_name
        item["en_name"] = en_name
        idx = 1
    
    definition_parts = []
    
    while idx < len(lines):
        line = lines[idx]
        # 判断治法定义的特征句式（因……治以…… / 泛指…… / 指通过……）
        if line.startswith(('因', '泛指', '与', '由', '指', '素体')) or '所致' in line or '治法' in line or '的方法' in line or '治以' in line:
            definition_parts.extend(lines[idx:])
            break
        elif line.startswith(('注：', '注:')):
            definition_parts.append(line)
        else:
            # 属于别名 / 可选用词（如“辛温解表”）
            if line not in item["aliases"] and line != item["name"]:
                item["aliases"].append(line)
        idx += 1
        
    full_def = "".join(definition_parts).strip()
    item["definition"] = full_def
    
    # 定义中包含“泛指”即为类目词
    if "泛指" in full_def:
        item["is_category"] = True
    else:
        item["is_category"] = False
        
    del item["pending_lines"]
    return item

def parse_principles_document(paragraphs):
    """解析中医治法标准文件"""
    entities = []
    triples = []
    
    # 匹配序号（如 "2", "2.1", "2.1.1" 等）
    code_pattern = re.compile(r'^(\d+(?:\.\d+)*)\s*(.*)$')
    stop_headers = ('参考文献', '汉语拼音索引', '汉语笔画索引', '英文对应词索引')
    
    current_item = None
    started = False

    for line in paragraphs:
        cleaned_line = line.strip().replace('　', ' ')
        if not cleaned_line:
            continue
            
        # 遇到文末索引或参考文献停止解析
        if any(cleaned_line.startswith(sh) for sh in stop_headers):
            break
        
        # 过滤目录部分
        if '目 次' in cleaned_line or '目  次' in cleaned_line or '前 言' in cleaned_line:
            continue
            
        match = code_pattern.match(cleaned_line)
        is_new_header = False
        
        if match:
            code_candidate = match.group(1)
            rest = match.group(2).strip()
            
            # 过滤掉第1章“1 范围”
            if code_candidate == "1" and ("范围" in rest or not rest):
                continue
                
            # 判断是否是有效条目标题
            if not rest or (rest and not rest.startswith(('因', '泛指', '与', '注', '临床以', '本文件', '本标准', '治以'))):
                is_new_header = True
                
        if is_new_header:
            started = True
            if current_item:
                entities.append(finalize_item(current_item))
            
            code = match.group(1)
            rest = match.group(2).strip()
            
            current_item = {
                "raw_code": code,
                "id": f"PRN_{code}",
                "name": "",
                "en_name": "",
                "aliases": [],
                "is_category": False,
                "parent_id": None,
                "definition": "",
                "pending_lines": []
            }
            
            if rest:
                name, en = split_zh_en(rest)
                current_item["name"] = name
                current_item["en_name"] = en
        else:
            if started and current_item is not None:
                current_item["pending_lines"].append(cleaned_line)

    # 结算最后一个
    if current_item:
        entities.append(finalize_item(current_item))

    # 计算 parent_id 并构建三元组（子属于父）
    for ent in entities:
        code = ent["raw_code"]
        parts = code.split('.')
        if len(parts) > 1:
            parent_code = '.'.join(parts[:-1])
            ent["parent_id"] = f"PRN_{parent_code}"
            
            triples.append({
                "head": ent["id"],
                "relation": "IS_SUBCLASS_OF",
                "tail": ent["parent_id"]
            })
        else:
            ent["parent_id"] = None
            
        del ent["raw_code"]

    return entities, triples

def save_outputs(entities, triples, output_dir):
    """保存为 JSONL 和 CSV 文件"""
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. 实体表 - JSONL
    ent_jsonl_path = os.path.join(output_dir, "entities_principles.jsonl")
    with open(ent_jsonl_path, 'w', encoding='utf-8') as f:
        for ent in entities:
            f.write(json.dumps(ent, ensure_ascii=False) + '\n')
            
    # 2. 实体表 - CSV
    ent_csv_path = os.path.join(output_dir, "entities_principles.csv")
    with open(ent_csv_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "en_name", "is_category", "parent_id", "aliases", "definition"])
        for ent in entities:
            writer.writerow([
                ent["id"],
                ent["name"],
                ent["en_name"],
                ent["is_category"],
                ent["parent_id"] or "",
                "|".join(ent["aliases"]),
                ent["definition"]
            ])

    # 3. 三元组表 - JSONL
    trip_jsonl_path = os.path.join(output_dir, "triples_principles_hierarchy.jsonl")
    with open(trip_jsonl_path, 'w', encoding='utf-8') as f:
        for trip in triples:
            f.write(json.dumps(trip, ensure_ascii=False) + '\n')

    # 4. 三元组表 - CSV
    trip_csv_path = os.path.join(output_dir, "triples_principles_hierarchy.csv")
    with open(trip_csv_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["head", "relation", "tail"])
        for trip in triples:
            writer.writerow([trip["head"], trip["relation"], trip["tail"]])

    print("=" * 55)
    print(" 🌿 治法数据解析完成！")
    print(f" 1. 实体表 (JSONL): {ent_jsonl_path}")
    print(f" 2. 实体表 (CSV)  : {ent_csv_path}")
    print(f" 3. 关系表 (JSONL): {trip_jsonl_path}")
    print(f" 4. 关系表 (CSV)  : {trip_csv_path}")
    print(f" 📊 共解析治法实体: {len(entities)} 个，层级关系: {len(triples)} 条")
    print("=" * 55)

def main():
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent.parent
    
    # 智能定位治法原数据文件夹（支持 '法' 或 '治法'）
    possible_input_dirs = [
        project_root / "原数据" / "治",
        project_root / "原数据" / "治法"
    ]
    
    input_file = None
    for p_dir in possible_input_dirs:
        if p_dir.exists():
            files = list(p_dir.glob("*.docx")) + list(p_dir.glob("*.txt"))
            if files:
                input_file = files[0]
                break
                
    if not input_file:
        print("❌ 未在 '原数据/法/' 目录下找到任何 .docx 或 .txt 文件！")
        return

    output_dir = project_root / "生成出来的数据" / "治"
    print(f"📖 正在读取治法原数据: {input_file.name}")
    
    if input_file.suffix == '.docx':
        paragraphs = get_paragraphs_from_docx(str(input_file))
    else:
        paragraphs = get_paragraphs_from_txt(str(input_file))
        
    entities, triples = parse_principles_document(paragraphs)
    save_outputs(entities, triples, str(output_dir))

if __name__ == "__main__":
    main()
