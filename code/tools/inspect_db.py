"""
========================================================================================
模块名称: inspect_db.py
功能描述: SQLite 知识库结构探测与数据完整性质检工具
工程定位: 数据管道辅助验证脚本 (Audit Tool)
核心功能:
    1. 自动定位工程内原始中医药 SQLite 数据库文件 (tcm_knowledge.db)。
    2. 提取数据库内所有表的架构元数据 (Schema)，包括字段名、类型、非空约束及主键。
    3. 输出各表记录总数与前序样例数据，用于入库前的数据合规性核验。
========================================================================================
"""

import sys
import sqlite3
import logging
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional

# 配置标准日志格式
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("DatabaseInspector")


def resolve_default_db_path() -> Optional[Path]:
    """
    根据工程标准目录架构自动推导数据库文件路径。

    Returns:
        Optional[Path]: 探测到的有效数据库路径，未找到时返回 None
    """
    script_dir = Path(__file__).resolve().parent
    # 向上寻找包含 "原数据" 的项目根目录
    project_root = script_dir.parent.parent if (script_dir.parent.parent / "原数据").exists() else script_dir.parent

    search_dirs = [
        project_root / "原数据" / "药",
        project_root / "原数据" / "中药",
        project_root / "原数据"
    ]

    for directory in search_dirs:
        if directory.exists():
            candidates = (
                list(directory.rglob("*.db"))
                + list(directory.rglob("*.sqlite"))
                + list(directory.rglob("*.sqlite3"))
            )
            if candidates:
                return candidates[0]
    return None


def inspect_sqlite(db_path: Path) -> bool:
    """
    连接并质检指定 SQLite 数据库的元数据与表内容。

    Args:
        db_path: 目标 SQLite 数据库路径
    Returns:
        bool: 检查是否成功执行
    """
    if not db_path.exists():
        logger.error(f"指定的数据库文件不存在: {db_path}")
        return False

    db_size_mb = db_path.stat().st_size / (1024 * 1024)
    logger.info(f"开始探测数据库文件: {db_path.name} (大小: {db_size_mb:.2f} MB)")
    print("-" * 80)
    print(f"数据库物理路径: {db_path.resolve()}")
    print("-" * 80)

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # 1. 查询所有用户定义数据表（排除 sqlite 内置序列追踪表）
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables: List[str] = [t[0] for t in cursor.fetchall()]

        if not tables:
            logger.warning("数据库中未检索到任何用户定义数据表。")
            conn.close()
            return True

        print(f"共发现 {len(tables)} 张数据表:\n")

        # 2. 逐表分析模式与数据概况
        for idx, table in enumerate(tables, 1):
            cursor.execute(f"SELECT COUNT(*) FROM `{table}`;")
            row_count: int = cursor.fetchone()[0]

            cursor.execute(f"PRAGMA table_info(`{table}`);")
            columns_info = cursor.fetchall()
            # columns_info 结构: (cid, name, type, notnull, dflt_value, pk)
            col_names: List[str] = [col[1] for col in columns_info]
            pk_cols: List[str] = [col[1] for col in columns_info if col[5] == 1]

            print(f"[{idx}] 数据表: {table}")
            print(f"    记录总量: {row_count} 行")
            print(f"    主键约束: {', '.join(pk_cols) if pk_cols else '未定义显式主键'}")
            print(f"    字段定义: {', '.join(col_names[:8])}{' ...' if len(col_names) > 8 else ''}")

            # 读取一条样例数据进行字段映射预览
            cursor.execute(f"SELECT * FROM `{table}` LIMIT 1;")
            sample = cursor.fetchone()
            if sample:
                sample_dict = {
                    col_names[i]: (str(sample[i])[:40] + "..." if len(str(sample[i])) > 40 else str(sample[i]))
                    for i in range(min(5, len(col_names)))
                }
                print(f"    数据样例: {sample_dict}")
            print("-" * 80)

        conn.close()
        logger.info("数据库模式与数据质检完成。")
        return True

    except sqlite3.Error as e:
        logger.error(f"SQLite 数据库读取异常: {e}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="SQLite 数据库模式与数据完整性质检工具")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="目标 SQLite 数据库的路径。若不指定，系统将自动在工程原数据目录下探测。"
    )
    args = parser.parse_args()

    target_db = args.db_path or resolve_default_db_path()
    if not target_db:
        logger.error("未找到有效的 SQLite 数据库文件，请确认原数据目录已正确放置 tcm_knowledge.db。")
        sys.exit(1)

    success = inspect_sqlite(target_db)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()