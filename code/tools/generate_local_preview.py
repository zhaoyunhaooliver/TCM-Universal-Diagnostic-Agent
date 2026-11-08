"""
========================================================================================
模块名称: generate_local_preview.py
功能描述: 本地脱机经方配伍与临床证据可视化预览引擎
工程定位: 本地调试与质量核验工具 (Local Graph Visualizer)
核心机制:
    1. 脱离 Neo4j 服务器环境，直接读取本地 CSV 实体表与三元组关系表。
    2. 基于 Vis.js 动态构建方剂-中药-经文-医案多维放射状知识图谱。
    3. 全面适配最新实体规范: usage_info (完整方后注) 与 clause_text (宋本两书条文全览)。
    4. 自动生成单页独立 HTML 报告并唤起本地浏览器供临床质检。
========================================================================================
"""

import sys
import csv
import json
import logging
import argparse
import webbrowser
from pathlib import Path
from typing import Dict, List, Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("LocalPreviewGenerator")


def load_target_formula(formula_csv: Path, formula_name: str) -> Optional[Dict[str, str]]:
    """从 entities_formulas.csv 中检索目标方剂主记录。"""
    if not formula_csv.exists():
        logger.error(f"方剂实体表不存在: {formula_csv}")
        return None

    with open(formula_csv, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("name", "").strip() == formula_name:
                return row
    return None


def generate_preview_html(
    formula: Dict[str, str],
    matched_herbs: List[Dict[str, Any]],
    matched_clauses: List[Dict[str, Any]],
    matched_cases: List[Dict[str, Any]],
    output_html_path: Path
) -> None:
    """组装 Vis.js 网络与 Markdown 风格双栏独立 HTML 报告。"""
    f_id = formula["id"]
    f_name = formula["name"]

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []

    # 1. 中心方剂节点 (绿色)
    nodes.append({
        "id": f_id,
        "label": f_name,
        "color": "#4CAF50",
        "size": 36,
        "title": f"经方: {f_name}\n出处: {formula.get('source_book', '')}"
    })

    # 2. 中药配伍节点 (橙色)
    for h in matched_herbs:
        nodes.append({
            "id": h["id"],
            "label": h["name"],
            "color": "#FFA726",
            "size": 22,
            "title": f"中药: {h['name']}\n剂量: {h['dosage']}"
        })
        edges.append({
            "from": f_id,
            "to": h["id"],
            "label": h["dosage"] if h["dosage"] else "配伍",
            "color": {"color": "#64B5F6"}
        })

    # 3. 经文条文节点 (棕色)
    for idx, c in enumerate(matched_clauses[:6], 1):
        c_label = f"经文 {idx}"
        nodes.append({
            "id": c.get("id", f"CLS_{idx}"),
            "label": c_label,
            "color": "#8D6E63",
            "size": 20,
            "title": f"{c.get('name', '条文依据')}\n{c.get('clause_text', '')}"
        })
        edges.append({
            "from": f_id,
            "to": c.get("id", f"CLS_{idx}"),
            "label": "经典载记",
            "color": {"color": "#64B5F6"}
        })

    # 4. 实战医案节点 (青色)
    for idx, cs in enumerate(matched_cases[:6], 1):
        cs_label = f"医案 {idx}"
        nodes.append({
            "id": cs.get("id", f"CASE_{idx}"),
            "label": cs_label,
            "color": "#26A69A",
            "size": 20,
            "title": f"医案\n主诉: {cs.get('chief_complaint', '')}\n舌脉: {cs.get('tongue_diagnosis', '')} {cs.get('pulse_diagnosis', '')}"
        })
        edges.append({
            "from": f_id,
            "to": cs.get("id", f"CASE_{idx}"),
            "label": "临床运用",
            "color": {"color": "#64B5F6"}
        })

    # 解析多条经文卡片
    clause_text_raw = formula.get("clause_text", "")
    clause_blocks = [cb.strip() for cb in clause_text_raw.split("\n\n") if cb.strip()]

    html_template = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>【脱机质检】{f_name} 知识网络与临床档案</title>
    <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <style>
        body {{
            margin: 0;
            padding: 20px;
            background-color: #121212;
            color: #E0E0E0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif;
            display: flex;
            height: 95vh;
            box-sizing: border-box;
            gap: 20px;
        }}
        #left-panel {{
            flex: 1.1;
            background: #1E1E1E;
            border-radius: 8px;
            padding: 24px;
            overflow-y: auto;
            border: 1px solid #333333;
        }}
        #right-panel {{
            flex: 1;
            background: #181818;
            border-radius: 8px;
            border: 1px solid #333333;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }}
        #network {{
            flex: 1;
            width: 100%;
            height: 100%;
        }}
        h1, h2, h3 {{ color: #E0E0E0; margin-top: 0; font-weight: 500; }}
        h1 {{ font-size: 24px; border-bottom: 1px solid #333; padding-bottom: 12px; }}
        h3 {{ font-size: 16px; margin-top: 20px; color: #90CAF9; }}
        .badge {{ background: #2E7D32; color: #FFF; padding: 2px 6px; border-radius: 4px; font-size: 12px; }}
        .info-card {{ background: #252525; border-left: 4px solid #4CAF50; padding: 12px 16px; margin: 12px 0; border-radius: 0 4px 4px 0; font-size: 14px; line-height: 1.6; }}
        .usage-card {{ background: #1A237E; border-left: 4px solid #3F51B5; padding: 12px 16px; margin: 12px 0; border-radius: 0 4px 4px 0; font-size: 14px; line-height: 1.6; }}
        .clause-card {{ background: #1B2E1E; border-left: 4px solid #4CAF50; padding: 12px 16px; margin: 8px 0; border-radius: 0 4px 4px 0; font-size: 14px; line-height: 1.6; }}
        .legend {{ padding: 10px 15px; background: #212121; font-size: 12px; border-top: 1px solid #333; display: flex; gap: 15px; justify-content: center; }}
        .dot {{ height: 10px; width: 10px; border-radius: 50%; display: inline-block; margin-right: 5px; }}
    </style>
</head>
<body>
    <div id="left-panel">
        <h1>{f_name} <span class="badge">{formula.get('id', '')}</span></h1>
        
        <div class="info-card">
            <div><b>出处经典：</b> {formula.get('source_book', '《伤寒杂病论》')}</div>
            <div><b>涵盖条目：</b> {formula.get('chapter', '正文')}</div>
            <div><b>配伍组成：</b> {formula.get('composition', '详见右侧关联网络')}</div>
        </div>

        <h3>古法煎服与方后注 (usage_info)</h3>
        <div class="usage-card">
            {formula.get('usage_info', '以水煎煮，温服。') or '以水煎煮，温服。'}
        </div>

        <h3>宋本两书条辨全览 ({len(clause_blocks)}条)</h3>
        {"".join([f'<div class="clause-card">{cb}</div>' for cb in clause_blocks]) if clause_blocks else '<div class="clause-card">暂无直接条文记录</div>'}

        <h3>配伍中药明细 ({len(matched_herbs)}味)</h3>
        <p style="font-size: 14px; line-height: 1.8;">
            {'、'.join([f"<b>{h['name']}</b>({h['dosage']})" if h['dosage'] else f"<b>{h['name']}</b>" for h in matched_herbs])}
        </p>
    </div>

    <div id="right-panel">
        <div style="padding: 12px 16px; font-size: 14px; background: #212121; border-bottom: 1px solid #333;">
            知识拓扑网络: {f_name}
        </div>
        <div id="network"></div>
        <div class="legend">
            <span><span class="dot" style="background:#4CAF50;"></span>方剂 (Center)</span>
            <span><span class="dot" style="background:#FFA726;"></span>中药配伍 (Herb)</span>
            <span><span class="dot" style="background:#8D6E63;"></span>伤寒经文 (Clause)</span>
            <span><span class="dot" style="background:#26A69A;"></span>实战医案 (Case)</span>
        </div>
    </div>

    <script type="text/javascript">
        var nodes = new vis.DataSet({json.dumps(nodes, ensure_ascii=False)});
        var edges = new vis.DataSet({json.dumps(edges, ensure_ascii=False)});
        var container = document.getElementById('network');
        var data = {{ nodes: nodes, edges: edges }};
        var options = {{
            nodes: {{
                font: {{ color: '#FFFFFF', size: 12, face: 'Microsoft YaHei' }},
                borderWidth: 1.5
            }},
            edges: {{
                font: {{ color: '#90CAF9', size: 11, align: 'middle', background: '#181818' }},
                arrows: {{ to: {{ enabled: true, scaleFactor: 0.5 }} }},
                smooth: {{ type: 'continuous' }}
            }},
            physics: {{
                forceAtlas2Based: {{
                    gravitationalConstant: -100,
                    centralGravity: 0.02,
                    springLength: 120,
                    springConstant: 0.08
                }},
                solver: 'forceAtlas2Based'
            }}
        }};
        new vis.Network(container, data, options);
    </script>
</body>
</html>"""

    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(html_template)
    logger.info(f"脱机质检报告已生成: {output_html_path.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="本地脱机经方配伍与临床证据可视化预览引擎")
    parser.add_argument(
        "--formula",
        type=str,
        default=None,
        help="待检索与质检的经方名称 (例如: 小建中汤、四逆散)。"
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent.parent if (script_dir.parent.parent / "生成出来的数据").exists() else script_dir.parent
    data_dir = project_root / "生成出来的数据"

    target_name = args.formula
    if not target_name:
        try:
            target_name = input("请输入待质检的经方名称 [默认: 四逆散]: ").strip()
        except EOFError:
            target_name = ""
        if not target_name:
            target_name = "四逆散"

    logger.info(f"正在检索目标经方实体: {target_name}")

    formula_csv = data_dir / "方剂" / "entities_formulas.csv"
    formula = load_target_formula(formula_csv, target_name)
    if not formula:
        logger.error(f"在 {formula_csv} 中未检索到经方: {target_name}")
        sys.exit(1)

    f_id = formula["id"]

    # 读取中药配伍关联
    herb_triple_csv = data_dir / "方剂" / "triples_formula_contains_herb.csv"
    herb_entity_csv = data_dir / "中药" / "entities_herbs.csv"
    herb_info_map: Dict[str, Dict[str, str]] = {}
    if herb_entity_csv.exists():
        with open(herb_entity_csv, "r", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                herb_info_map[r["id"]] = r

    matched_herbs: List[Dict[str, Any]] = []
    if herb_triple_csv.exists():
        with open(herb_triple_csv, "r", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if r["head"] == f_id:
                    h_id = r["tail"]
                    h_name = r.get("herb_name") or herb_info_map.get(h_id, {}).get("name", h_id)
                    matched_herbs.append({
                        "id": h_id,
                        "name": h_name,
                        "dosage": r.get("dosage", "")
                    })

    # 读取古籍经文条文关联
    clause_triple_csv = data_dir / "古籍" / "伤寒杂病论" / "triples_clause_prescribes_formula.csv"
    clause_entity_csv = data_dir / "古籍" / "伤寒杂病论" / "entities_shanghan_clauses.csv"
    clause_info_map: Dict[str, Dict[str, str]] = {}
    if clause_entity_csv.exists():
        with open(clause_entity_csv, "r", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                clause_info_map[r["id"]] = r

    matched_clauses: List[Dict[str, Any]] = []
    if clause_triple_csv.exists():
        with open(clause_triple_csv, "r", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if r["tail"] == f_id and r["head"] in clause_info_map:
                    matched_clauses.append(clause_info_map[r["head"]])

    # 读取真实医案关联
    case_triple_csv = data_dir / "医案" / "triples_case_prescribed_formulas.csv"
    case_entity_csv = data_dir / "医案" / "entities_clinical_cases.csv"
    case_info_map: Dict[str, Dict[str, str]] = {}
    if case_entity_csv.exists():
        with open(case_entity_csv, "r", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                case_info_map[r["id"]] = r

    matched_cases: List[Dict[str, Any]] = []
    if case_triple_csv.exists():
        with open(case_triple_csv, "r", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if r["tail"] == f_id and r["head"] in case_info_map:
                    matched_cases.append(case_info_map[r["head"]])

    output_html = project_root / "tcm_preview.html"
    generate_preview_html(formula, matched_herbs, matched_clauses, matched_cases, output_html)

    # 自动唤起浏览器
    webbrowser.open(f"file:///{output_html.resolve()}")


if __name__ == "__main__":
    main()