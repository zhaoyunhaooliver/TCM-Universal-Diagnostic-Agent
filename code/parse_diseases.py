"""
========================================================================================
模块名称: parse_diseases.py
功能描述: 国家标准《中医疾病分类与代码》(GB/T) 层级知识抽取引擎
核心机制:
    1. 状态机解析 docx/txt 格式的标准条文文本。
    2. 基于数字编码（如 2, 2.1, 2.1.1）推算树状继承体系，构建 IS_SUBCLASS_OF 关系。
    3. 自动分离中英文术语、可选用词，并将定义中含“泛指”的术语判定为类目词。
========================================================================================
"""

import os
import re
import csv
import json
import logging
from pathlib import Path
from typing import List, Tuple, Dict, Any

try:
    import docx
except ImportError:
    docx = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("DiseaseStandardParser")


def get_paragraphs_from_docx(file_path: Path) -> List[str]:
    """读取 Word (.docx) 文件中的全部有效段落文本。"""
    if docx is None:
        raise ImportError("缺少 python-docx 依赖，请先执行: pip install python-docx")
    doc = docx.Document(str(file_path))
    return [p.text.strip() for p in doc.paragraphs if p.text.strip()]


def get_paragraphs_from_txt(file_path: Path) -> List[str]:
    """读取纯文本 (.txt) 文件中的全部有效行。"""
    with open(file_path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def split_zh_en(text: str) -> Tuple[str, str]:
    """依据首个英文字符位置准确切分中英文术语名称。"""
    match = re.search(r"[a-zA-Z]", text)
    if match:
        idx = match.start()
        return text[:idx].strip(), text[idx:].strip()
    return text.strip(), ""


def finalize_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """终结待处理行缓冲区，萃取术语名称、别名与定义内容。"""
    lines = item["pending_lines"]
    idx = 0

    if not item["name"] and len(lines) > 0:
        zh_name, en_name = split_zh_en(lines[0])
        item["name"] = zh_name
        item["en_name"] = en_name
        idx = 1

    definition_parts = []
    while idx < len(lines):
        line = lines[idx]
        if line.startswith(("因", "泛指", "与", "由", "素体", "指")) or any(k in line for k in ["所致", "特征的一类", "的疾病", "的病"]):
            definition_parts.extend(lines[idx:])
            break
        elif line.startswith(("注：", "注:")):
            definition_parts.append(line)
        else:
            if line not in item["aliases"] and line != item["name"]:
                item["aliases"].append(line)
        idx += 1

    full_def = "".join(definition_parts).strip()
    item["definition"] = full_def
    item["is_category"] = "泛指" in full_def
    del item["pending_lines"]
    return item


def parse_disease_document(paragraphs: List[str]) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """解析疾病标准段落列表，构建实体与层级关系三元组。"""
    entities: List[Dict[str, Any]] = []
    triples: List[Dict[str, str]] = []

    code_pattern = re.compile(r"^(\d+(?:\.\d+)*)\s*(.*)$")
    stop_headers = ("参考文献", "汉语拼音索引", "汉语笔画索引", "英文对应词索引")

    current_item: Dict[str, Any] = None
    started = False

    for line in paragraphs:
        cleaned_line = line.strip().replace("　", " ")
        if not cleaned_line:
            continue

        if any(cleaned_line.startswith(sh) for sh in stop_headers):
            break

        if any(k in cleaned_line for k in ["目 次", "目  次", "前 言"]):
            continue

        match = code_pattern.match(cleaned_line)
        is_new_header = False

        if match:
            code_candidate = match.group(1)
            rest = match.group(2).strip()

            if code_candidate == "1" and ("范围" in rest or not rest):
                continue

            if not rest or not rest.startswith(("因", "泛指", "与", "注", "临床以", "本文件", "本标准")):
                is_new_header = True

        if is_new_header:
            started = True
            if current_item:
                entities.append(finalize_item(current_item))

            code = match.group(1)
            rest = match.group(2).strip()

            current_item = {
                "raw_code": code,
                "id": f"DIS_{code}",
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

    if current_item:
        entities.append(finalize_item(current_item))

    # 计算层级继承关系并构建三元组
    for ent in entities:
        code = ent["raw_code"]
        parts = code.split(".")
        if len(parts) > 1:
            parent_code = ".".join(parts[:-1])
            ent["parent_id"] = f"DIS_{parent_code}"
            triples.append({
                "head": ent["id"],
                "relation": "IS_SUBCLASS_OF",
                "tail": ent["parent_id"]
            })
        else:
            ent["parent_id"] = None
        del ent["raw_code"]

    return entities, triples


def save_outputs(entities: List[Dict[str, Any]], triples: List[Dict[str, str]], output_dir: Path) -> None:
    """持久化保存实体表与三元组层级表。"""
    output_dir.mkdir(parents=True, exist_ok=True)

    ent_jsonl_path = output_dir / "entities_diseases.jsonl"
    with open(ent_jsonl_path, "w", encoding="utf-8") as f:
        for ent in entities:
            f.write(json.dumps(ent, ensure_ascii=False) + "\n")

    ent_csv_path = output_dir / "entities_diseases.csv"
    with open(ent_csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "en_name", "is_category", "parent_id", "aliases", "definition"])
        for ent in entities:
            writer.writerow([
                ent["id"], ent["name"], ent["en_name"], ent["is_category"],
                ent["parent_id"] or "", "|".join(ent["aliases"]), ent["definition"]
            ])

    trip_jsonl_path = output_dir / "triples_diseases_hierarchy.jsonl"
    with open(trip_jsonl_path, "w", encoding="utf-8") as f:
        for trip in triples:
            f.write(json.dumps(trip, ensure_ascii=False) + "\n")

    trip_csv_path = output_dir / "triples_diseases_hierarchy.csv"
    with open(trip_csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["head", "relation", "tail"])
        for trip in triples:
            writer.writerow([trip["head"], trip["relation"], trip["tail"]])

    logger.info(f"疾病数据解析完成: 实体 {len(entities)} 个，层级关系 {len(triples)} 条。")


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parents[1] if (script_dir.parents[1] / "原数据").exists() else Path(r"D:\中医系统")

    possible_input_dirs = [project_root / "原数据" / "病", project_root / "原数据" / "疾病"]
    input_file = None
    for p_dir in possible_input_dirs:
        if p_dir.exists():
            files = list(p_dir.glob("*.docx")) + list(p_dir.glob("*.txt"))
            if files:
                input_file = files[0]
                break

    if not input_file:
        logger.error("未在原数据目录下定位到疾病标准文档 (.docx 或 .txt)。")
        return

    output_dir = project_root / "生成出来的数据" / "病"
    logger.info(f"开始解析国家疾病标准文件: {input_file.name}")

    paragraphs = get_paragraphs_from_docx(input_file) if input_file.suffix == ".docx" else get_paragraphs_from_txt(input_file)
    entities, triples = parse_disease_document(paragraphs)
    save_outputs(entities, triples, output_dir)


if __name__ == "__main__":
    main()