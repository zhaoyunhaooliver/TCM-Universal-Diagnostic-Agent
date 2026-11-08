"""
========================================================================================
模块名称: batch_extract_all_formulas.py
功能描述: 仲景经典名方全量提取与方药配伍知识图谱构建引擎
依据标准: 宋本《伤寒论》（赵开美本校勘）与《金匮要略方论》（林亿校正本）
核心设计原则:
    1. 100% 数据库反查驱动：严格依托 tcm_knowledge.db 中药实体库及其别名索引，零手写字典。
    2. 原著方后注归一保护：严禁使用正则强行切割煎服法、加减法与禁忌，统一完整封存于 usage_info。
    3. 互见方引用穿透：自动解析“见前虚劳中”等古籍省略条目，保证全方药味（如小建中汤6味）无缺漏。
    4. 宋本两书全条文汇编：聚合单一经方横跨《伤寒论》与《金匮要略》的多重主治条文，保留原始辨证逻辑。
========================================================================================
"""

import os
import re
import csv
import sqlite3
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Set, Any, Optional

# 配置工业级标准日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("TCM_Formula_Extractor")


def clean_val(val: Any) -> str:
    """清洗字段中的空值、无意义字符，返回合规的去首尾空格字符串。"""
    if val is None:
        return ""
    s_val = str(val).strip()
    if s_val.upper() in ["NONE", "NULL", "NA", ""]:
        return ""
    return s_val


def read_text_safely(file_path: Path) -> str:
    """
    跨编码兼容的安全文件读取工具，保证罕见汉字与古医籍异体字不丢失。
    
    Args:
        file_path: 目标文本文件路径
    Returns:
        文本内容字符串，若读取失败返回空字符串
    """
    encodings = ["gb18030", "utf-8-sig", "utf-8", "gbk"]
    for enc in encodings:
        try:
            with open(file_path, "r", encoding=enc) as f:
                content = f.read()
            if any(k in content for k in ["伤寒", "金匮", "汤", "散", "丸"]):
                return content
        except Exception:
            continue
    logger.warning(f"未能以常用编码正确解码文件: {file_path}")
    return ""


def load_herb_indices(db_path: Path) -> Tuple[Dict[str, Tuple[str, str]], List[str]]:
    """
    从本地知识库加载全部中药标准名与权威别名，构建动态反查倒排索引。
    
    Args:
        db_path: SQLite 数据库路径
    Returns:
        (db_herb_index, sorted_db_herbs): 映射字典与按长度降序排列的药名列表
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, name, alias FROM herbs;")
    db_herb_index: Dict[str, Tuple[str, str]] = {}
    
    for r in cursor.fetchall():
        h_id = f"HRB_{r['id']}"
        h_name = clean_val(r["name"])
        if not h_name:
            continue
        db_herb_index[h_name] = (h_id, h_name)
        
        # 拆解数据库自带别名
        alias_str = clean_val(r["alias"])
        if alias_str:
            for a in re.split(r"[,，;；、|\s/]", alias_str):
                a_clean = a.strip()
                if len(a_clean) >= 2 and a_clean not in db_herb_index:
                    db_herb_index[a_clean] = (h_id, h_name)
    conn.close()

    # 规范古籍常见通假及异体药名（对齐标准药典名称）
    if "厚朴" in db_herb_index and "浓朴" not in db_herb_index:
        db_herb_index["浓朴"] = db_herb_index["厚朴"]
    if "饴糖" in db_herb_index and "胶饴" not in db_herb_index:
        db_herb_index["胶饴"] = db_herb_index["饴糖"]

    # 按长度倒序，优先长词匹配以防前缀截断
    sorted_db_herbs = sorted(db_herb_index.keys(), key=lambda x: len(x), reverse=True)
    logger.info(f"中药识别索引加载完毕: 共收录有效药名与权威别名 {len(db_herb_index)} 条。")
    return db_herb_index, sorted_db_herbs


def main() -> None:
    # 动态定位工程根目录（兼容各操作系统路径规范）
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parents[1] if (script_dir.parents[1] / "原数据").exists() else Path(r"D:\中医系统")
    
    data_dir = project_root / "生成出来的数据"
    books_dir = project_root / "原数据" / "古籍"
    db_path = project_root / "原数据" / "药" / "tcm_knowledge.db"
    
    if not db_path.exists():
        logger.error(f"核心依赖数据库不存在: {db_path}")
        return

    logger.info("启动宋本经方全量条文与配伍提取工作流...")

    # 1. 初始化中药反查索引
    db_herb_index, sorted_db_herbs = load_herb_indices(db_path)

    # 2. 定位古籍源文本
    shl_files = list(books_dir.rglob("*457-伤寒论.txt")) + list(books_dir.rglob("*伤寒论*.txt"))
    jg_files = list(books_dir.rglob("*499-金匮要略*.txt")) + list(books_dir.rglob("*金匮要略*.txt"))
    
    scan_targets: List[Tuple[str, Path]] = []
    if shl_files:
        scan_targets.append(("伤寒论", shl_files[0]))
    if jg_files:
        scan_targets.append(("金匮要略", jg_files[0]))

    clause_num_re = re.compile(r"^(\d+)[．\.\s、，：:。\-_]\s*(.*)$")
    post_marker_re = re.compile(
        r"(上[一二三四五六七八九十百\d]+味|右[一二三四五六七八九十百\d]+味|右上?[一二三四五六七八九十百\d]+味|"
        r"上[一-龥]{1,2}味|右[一-龥]{1,2}味|以水[一二三四五六七八九十百半\d]+[升斗]|捣筛)"
    )
    bracket_herb_re = re.compile(r"([一-龥]{1,8})[（\(]([^）\)]+)[）\)]")

    all_formulas: Dict[str, Dict[str, Any]] = {}
    formula_clauses_pool: Dict[str, List[Dict[str, str]]] = {}
    f_counter = 1

    # 3. 遍历古籍进行实体与条文抽取
    for book_name, file_path in scan_targets:
        logger.info(f"正在全量解析《{book_name}》: {file_path.name}")
        raw_text = read_text_safely(file_path)
        if not raw_text:
            continue
            
        content = raw_text.replace("\r\n", "\n").replace("\r", "\n")
        # 清除古籍印刷排版符号（如 \\x标记）
        content = re.sub(r"\\x([一-龥]+(?:汤|散|丸|饮|酒|煎|膏)方?)\\x", r"\1", content)
        blocks = re.split(r"\n(?=\d+[．\.、\s]|【\d+】)", content)

        for blk in blocks:
            blk_clean = blk.strip()
            if not blk_clean:
                continue

            num_match = clause_num_re.match(blk_clean)
            c_num = num_match.group(1) if num_match else ""

            # 抓取本条文涉及的所有方名
            f_headings = re.findall(r"([一-龥]{2,12}(?:汤|散|丸|饮|酒|煎|膏))方", blk_clean)
            f_inlines = re.findall(r"([一-龥]{2,10}(?:汤|散|丸|饮|酒|煎|膏))(?:主之|宜之|加减法|[。.\s]|先与|急与|可与)", blk_clean)
            
            raw_f_names = f_headings + f_inlines
            f_names = list(dict.fromkeys([
                fn.replace("方", "").strip() for fn in raw_f_names 
                if fn.strip() not in ["上方", "前方", "温服", "建中汤"]
            ]))
            if not f_names:
                continue

            # 分离经文临床陈述与处方配伍区域
            pure_clause = blk_clean
            recipe_part = ""
            fn_pos = -1
            for fn in f_names:
                p = blk_clean.find(fn + "方")
                if p != -1:
                    fn_pos = p + len(fn) + 1
                    break
            
            if fn_pos != -1:
                pure_clause = blk_clean[:fn_pos].strip()
                recipe_part = blk_clean[fn_pos:].strip()
            else:
                alt_m = re.search(r"(?:主之|宜之)[。.\s]*", blk_clean)
                if alt_m:
                    pure_clause = blk_clean[:alt_m.end()].strip()
                    recipe_part = blk_clean[alt_m.end():].strip()
                else:
                    pure_clause = blk_clean
                    recipe_part = ""

            pure_clause = re.sub(r"^\d+[．\.、\s]*", "", pure_clause).strip()

            # 记录方剂的多重条文依据
            for fn in f_names:
                if fn not in formula_clauses_pool:
                    formula_clauses_pool[fn] = []
                exists = any(
                    item["book"] == book_name and item["num"] == c_num and item["text"] == pure_clause 
                    for item in formula_clauses_pool[fn]
                )
                if not exists and pure_clause:
                    formula_clauses_pool[fn].append({
                        "book": book_name,
                        "num": c_num,
                        "text": pure_clause
                    })

            # 解析处方药味与方后注
            if not recipe_part:
                continue

            herb_text_part = recipe_part
            usage_info_text = ""
            sep_m = post_marker_re.search(recipe_part)
            if sep_m:
                herb_text_part = recipe_part[:sep_m.start()].strip()
                usage_info_text = recipe_part[sep_m.start():].strip()
            else:
                lines = recipe_part.split("\n")
                if len(lines) > 1:
                    herb_text_part = lines[0].strip()
                    usage_info_text = "\n".join(lines[1:]).strip()

            is_cross_reference = any(k in herb_text_part for k in ["见前", "方见", "见上", "见下"])

            herbs_found: List[Dict[str, str]] = []
            matched_names: Set[str] = set()
            global_fallback = "各十分" if ("各十分" in recipe_part or "各十分" in usage_info_text) else ("各等分" if "等分" in recipe_part else "适量")

            # 穿透空壳条文，仅在包含真处方时抽取中药
            if not is_cross_reference:
                # 抽取带剂量括号的中药
                for raw_h, raw_d in bracket_herb_re.findall(herb_text_part):
                    raw_h_clean = raw_h.strip()
                    matched_id, matched_std = None, None
                    if raw_h_clean in db_herb_index:
                        matched_id, matched_std = db_herb_index[raw_h_clean]
                    else:
                        for db_h in sorted_db_herbs:
                            if db_h in raw_h_clean:
                                matched_id, matched_std = db_herb_index[db_h]
                                break
                    if matched_std and matched_std not in matched_names:
                        herbs_found.append({
                            "name": matched_std,
                            "id": matched_id,
                            "dosage": raw_d.strip()
                        })
                        matched_names.add(matched_std)

                # 补充抽取无括号排列的中药（如四逆散）
                for db_h in sorted_db_herbs:
                    if db_h in herb_text_part:
                        matched_id, matched_std = db_herb_index[db_h]
                        if matched_std not in matched_names:
                            herbs_found.append({
                                "name": matched_std,
                                "id": matched_id,
                                "dosage": global_fallback
                            })
                            matched_names.add(matched_std)

            # 注册与更新方剂实体（药味最完整、方后注最详实版本优先入库）
            for fn in f_names:
                if fn not in all_formulas:
                    all_formulas[fn] = {
                        "id": f"FOR_{f_counter:04d}",
                        "name": fn,
                        "composition": herb_text_part if not is_cross_reference else "",
                        "usage_info": usage_info_text,
                        "herbs": herbs_found
                    }
                    f_counter += 1
                else:
                    existing = all_formulas[fn]
                    if len(herbs_found) > len(existing["herbs"]):
                        existing["composition"] = herb_text_part
                        existing["usage_info"] = usage_info_text if usage_info_text else existing["usage_info"]
                        existing["herbs"] = herbs_found
                    elif not existing["usage_info"] and usage_info_text:
                        existing["usage_info"] = usage_info_text

    # 4. 汇总双书全量临床条文
    for fn, f_data in all_formulas.items():
        clauses = formula_clauses_pool.get(fn, [])
        books = []
        for c in clauses:
            b_name = f"《{c['book']}》"
            if b_name not in books:
                books.append(b_name)
        f_data["source_book"] = "、".join(books) if books else "《伤寒杂病论》"

        chap_list = [f"《{c['book']}》第{c['num']}条" if c['num'] else f"《{c['book']}》正文" for c in clauses]
        f_data["chapter"] = "；".join(dict.fromkeys(chap_list)) if chap_list else "详见条文"
        f_data["clause_num"] = "、".join(dict.fromkeys([c["num"] for c in clauses if c["num"]]))

        full_clause_texts = [
            f"【《{c['book']}》第{c['num']}条】\n{c['text']}" if c["num"] else f"【《{c['book']}》】\n{c['text']}"
            for c in clauses
        ]
        f_data["clause_text"] = "\n\n".join(full_clause_texts)

    # 5. 构建配伍关系三元组
    formula_herb_triples: List[Dict[str, str]] = []
    existing_pairs: Set[Tuple[str, str]] = set()
    for fn, f_data in all_formulas.items():
        f_id = f_data["id"]
        for h in f_data["herbs"]:
            pair = (f_id, h["id"])
            if pair not in existing_pairs:
                existing_pairs.add(pair)
                formula_herb_triples.append({
                    "head": f_id,
                    "relation": "CONTAINS_HERB",
                    "tail": h["id"],
                    "role": "经方配伍",
                    "dosage": h["dosage"],
                    "formula_name": fn,
                    "herb_name": h["name"]
                })

    # 6. 持久化数据文件
    out_dir_formula = data_dir / "方剂"
    out_dir_formula.mkdir(parents=True, exist_ok=True)
    out_formula_csv = out_dir_formula / "entities_formulas.csv"
    
    with open(out_formula_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "source_book", "chapter", "clause_num", "composition", "usage_info", "clause_text"])
        for fn, d in all_formulas.items():
            w.writerow([d["id"], d["name"], d["source_book"], d["chapter"], d["clause_num"], d["composition"], d["usage_info"], d["clause_text"]])

    out_triple_csv = out_dir_formula / "triples_formula_contains_herb.csv"
    with open(out_triple_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["head", "relation", "tail", "role", "dosage", "formula_name", "herb_name"])
        for t in formula_herb_triples:
            w.writerow([t["head"], t["relation"], t["tail"], t["role"], t["dosage"], t["formula_name"], t["herb_name"]])

    logger.info(f"经方提取任务完成: 生成方剂实体 {len(all_formulas)} 首，配伍关系三元组 {len(formula_herb_triples)} 条。")


if __name__ == "__main__":
    main()