import os
import sqlite3
from pathlib import Path

def inspect_sqlite():
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent.parent
    
    # 查找 原数据/药 或 原数据/ 下的 .db 文件
    search_dirs = [
        project_root / "原数据" / "药",
        project_root / "原数据" / "中药",
        project_root / "原数据"
    ]
    
    db_file = None
    for d in search_dirs:
        if d.exists():
            db_candidates = list(d.rglob("*.db")) + list(d.rglob("*.sqlite")) + list(d.rglob("*.sqlite3"))
            if db_candidates:
                db_file = db_candidates[0]
                break
                
    if not db_file:
        print("❌ 未找到任何 .db 数据库文件，请确认是否解压并放到了 原数据/药/ 目录下！")
        return

    print("=" * 60)
    print(f"🔍 正在探测数据库: {db_file.name} (大小: {db_file.stat().st_size / (1024*1024):.2f} MB)")
    print("=" * 60)

    try:
        conn = sqlite3.connect(str(db_file))
        cursor = conn.cursor()
        
        # 1. 查询所有数据表名
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [t[0] for t in cursor.fetchall() if t[0] != 'sqlite_sequence']
        
        print(f"📦 发现总共包含 {len(tables)} 张数据表：\n")
        
        # 2. 遍历每张表，获取行数、列字段名、并打印一行样例
        for idx, table in enumerate(tables, 1):
            # 获取总行数
            cursor.execute(f"SELECT COUNT(*) FROM `{table}`;")
            count = cursor.fetchone()[0]
            
            # 获取字段名
            cursor.execute(f"PRAGMA table_info(`{table}`);")
            columns = [col[1] for col in cursor.fetchall()]
            
            print(f"[{idx}] 数据表: 【{table}】 | 数据行数: {count} 条")
            print(f"    包含字段: {', '.join(columns[:10])}{' ...' if len(columns) > 10 else ''}")
            
            # 获取第一条样例数据
            cursor.execute(f"SELECT * FROM `{table}` LIMIT 1;")
            sample = cursor.fetchone()
            if sample:
                # 简化显示样例
                sample_preview = {columns[i]: str(sample[i])[:30] for i in range(min(5, len(columns)))}
                print(f"    样例数据: {sample_preview}")
            print("-" * 60)
            
        conn.close()
        print("✅ 探测完成！")
        
    except Exception as e:
        print(f"❌ 读取数据库出错: {e}")

if __name__ == "__main__":
    inspect_sqlite()
