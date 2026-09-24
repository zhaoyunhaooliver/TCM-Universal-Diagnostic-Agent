import os
import re
import json
import csv
from pathlib import Path

# 尝试导入 python-docx，若未安装可提示安装
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

def parse_syndrome_document(paragraphs):
    """
    解析证候标准文本
    提取：ID、中文名、英文名、别名列表、是否类目词、父级ID、定义文本
    """
    entities = []
    triples = []
    
    # 状态机解析正则
    # 匹配序号：如 "2", "2.1", "2.10.1.1" 等
    code_pattern = re.compile(r'^(\d+(?:\.\d+)*)\s*(.*)$')
    
    current_item = None
    all_codes = set()

    for line in paragraphs:
        # 去除首尾空白和全角空格
        cleaned_line = line.strip().replace('　', ' ')
        if not cleaned_line:
            continue
        
        # 检查是否是新的序号行（如 "2.10.1.1" 或 "2 八纲证候类术语 category..."）
        match = code_pattern.match(cleaned_line)
        is_new_header = False
        
        if match:
            code_candidate = match.group(1)
            rest = match.group(2).strip()
            
            # 判断逻辑：纯数字编码行，或者编码后面紧跟中文/英文
            if not rest or (rest and not rest.startswith(('因', '泛指', '与', '注', '临床以'))):
                is_new_header = True
                
        if is_new_header:
            # 结算上一个 item
            if current_item:
                entities.append(finalize_item(current_item))
            
            code = match.group(1)
            all_codes.add(code)
            rest = match.group(2).strip()
            
            current_item = {
                "raw_code": code,
                "id": f"SYN_{code}",
                "name": "",
                "en_name": "",
                "aliases": [],
                "is_category": False,
                "parent_id": None,
                "definition": "",
                "pending_lines": []
            }
            
            # 如果标题和编号在同一行（如大类 "2 八纲证候类术语 category..."）
            if rest:
                name, en = split_zh_en(rest)
                current_item["name"] = name
                current_item["en_name"] = en
        else:
            if current_item is not None:
                current_item["pending_lines"].append(cleaned_line)

    # 结算最后一个 item
    if current_item:
        entities.append(finalize_item(current_item))

    # 第二轮处理：计算 parent_id 并构建三元组
    for ent in entities:
        code = ent["raw_code"]
        parts = code.split('.')
        if len(parts) > 1:
            parent_code = '.'.join(parts[:-1])
            ent["parent_id"] = f"SYN_{parent_code}"
            
            # 生成层级三元组 (Child) -[IS_SUBCLASS_OF]-> (Parent)
            triples.append({
                "head": ent["id"],
                "relation": "IS_SUBCLASS_OF",
                "tail": ent["parent_id"]
            })
        else:
            ent["parent_id"] = None
            
        # 清理内部使用的辅助字段
        del ent["raw_code"]

    return entities, triples

def split_zh_en(text):
    """分离中文名称和英文名称"""
    # 找到第一个英文字母的位置作为切分点
    match = re.search(r'[a-zA-Z]', text)
    if match:
        idx = match.start()
        zh_part = text[:idx].strip()
        en_part = text[idx:].strip()
        return zh_part, en_part
    return text.strip(), ""

def finalize_item(item):
    """整理 pending_lines，提取名称、英文名、别名、定义"""
    lines = item["pending_lines"]
    
    # 如果名字还没有（编号单独一行的情况）
    idx = 0
    if not item["name"] and len(lines) > 0:
        zh_name, en_name = split_zh_en(lines[0])
        item["name"] = zh_name
        item["en_name"] = en_name
        idx = 1
    
    definition_parts = []
    
    # 后续行中：短行（非定义句式）视为别名，长句/因.../泛指...视为定义
    while idx < len(lines):
        line = lines[idx]
        if line.startswith(('因', '泛指', '与', '由', '素体', '因秉质')) or '所致' in line or '特征的证候' in line:
            # 属于定义开始
            definition_parts.extend(lines[idx:])
            break
        elif line.startswith('注：') or line.startswith('注:'):
            definition_parts.append(line)
        else:
            # 属于可选用词/别名
            if line not in item["aliases"] and line != item["name"]:
                item["aliases"].append(line)
        idx += 1
        
    full_def = "".join(definition_parts).strip()
    item["definition"] = full_def
    
    # 标准定义规则：含“泛指……一类证候”即为类目词
    if "泛指" in full_def:
        item["is_category"] = True
    else:
        item["is_category"] = False
        
    del item["pending_lines"]
    return item

def save_outputs(entities, triples, output_dir):
    """保存为 JSONL 和 CSV 文件"""
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. 实体表 - JSONL
    ent_jsonl_path = os.path.join(output_dir, "entities_syndromes.jsonl")
    with open(ent_jsonl_path, 'w', encoding='utf-8') as f:
        for ent in entities:
            f.write(json.dumps(ent, ensure_ascii=False) + '\n')
            
    # 2. 实体表 - CSV
    ent_csv_path = os.path.join(output_dir, "entities_syndromes.csv")
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
    trip_jsonl_path = os.path.join(output_dir, "triples_syndromes_hierarchy.jsonl")
    with open(trip_jsonl_path, 'w', encoding='utf-8') as f:
        for trip in triples:
            f.write(json.dumps(trip, ensure_ascii=False) + '\n')

    # 4. 三元组表 - CSV
    trip_csv_path = os.path.join(output_dir, "triples_syndromes_hierarchy.csv")
    with open(trip_csv_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["head", "relation", "tail"])
        for trip in triples:
            writer.writerow([trip["head"], trip["relation"], trip["tail"]])

    print("=" * 50)
    print(" 提取完成！生成文件如下：")
    print(f" 1. 实体表 (JSONL): {ent_jsonl_path}")
    print(f" 2. 实体表 (CSV)  : {ent_csv_path}")
    print(f" 3. 关系表 (JSONL): {trip_jsonl_path}")
    print(f" 4. 关系表 (CSV)  : {trip_csv_path}")
    print(f" 📊 共解析证候实体: {len(entities)} 个，层级关系: {len(triples)} 条")
    print("=" * 50)

def main():
    # 自动定位项目根目录（基于当前脚本路径推算）
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent.parent  # 中医系统/
    
    input_dir = project_root / "原数据" / "证"
    output_dir = project_root / "生成出来的数据" / "证"
    
    # 自动寻找输入文件 (.docx 优先，其次 .txt)
    input_files = list(input_dir.glob("*.docx")) + list(input_dir.glob("*.txt"))
    
    if not input_files:
        print(f"❌ 未在 {input_dir} 目录下找到 .docx 或 .txt 文件！")
        return
        
    input_file = input_files[0]
    print(f"📖 正在读取原数据文件: {input_file}")
    
    if input_file.suffix == '.docx':
        paragraphs = get_paragraphs_from_docx(str(input_file))
    else:
        paragraphs = get_paragraphs_from_txt(str(input_file))
        
    entities, triples = parse_syndrome_document(paragraphs)
    save_outputs(entities, triples, str(output_dir))

if __name__ == "__main__":
    main()
