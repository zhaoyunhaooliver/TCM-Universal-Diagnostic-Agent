import os
from pathlib import Path

def scan_books():
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent.parent
    
    books_dir = project_root / "原数据" / "古籍"
    
    if not books_dir.exists():
        print(f"❌ 未找到目录: {books_dir}")
        return

    print("=" * 65)
    print(f"📚 正在递归扫描古籍目录: {books_dir}")
    print("=" * 65)

    # 递归查找所有文本文件 (.txt, .md)
    all_files = list(books_dir.rglob("*.txt")) + list(books_dir.rglob("*.md"))
    
    if not all_files:
        print("❌ 未在 原数据/古籍/ 下找到任何 .txt 或 .md 文件，请确认是否解压进去！")
        return

    # 按文件名排序
    all_files.sort(key=lambda x: x.name)
    
    print(f"🎉 扫描成功！总共发现 {len(all_files)} 部中医药古籍原典文本！\n")

    # 重点挑出与当前经方、伤寒、金匮、本草相关的经典
    key_classics = []
    shanghan_books = []
    jingui_books = []
    bencao_books = []
    
    for f in all_files:
        fname = f.name
        if '伤寒' in fname:
            shanghan_books.append(fname)
        elif '金匮' in fname:
            jingui_books.append(fname)
        elif '本草' in fname:
            bencao_books.append(fname)
            
    print("-----------------------------------------------------------------")
    print(f"🎯 【伤寒类专著】发现 {len(shanghan_books)} 部：")
    for b in shanghan_books[:10]:
        print(f"   • {b}")
    if len(shanghan_books) > 10:
        print(f"   ... 还有 {len(shanghan_books)-10} 部未列出")

    print("\n🎯 【金匮类专著】发现 {len(jingui_books)} 部：")
    for b in jingui_books[:10]:
        print(f"   • {b}")
        
    print("\n🎯 【本草本草类专著】发现 {len(bencao_books)} 部：")
    for b in bencao_books[:10]:
        print(f"   • {b}")
    print("-----------------------------------------------------------------")

    # 把全部 700 本书的书名保存到一个 txt 文件里，方便肉眼查阅
    summary_path = books_dir / "全套古籍书名清单.txt"
    with open(summary_path, 'w', encoding='utf-8') as out:
        out.write(f"=== 中医药古籍库收录清单（共 {len(all_files)} 部）===\n\n")
        for idx, f in enumerate(all_files, 1):
            out.write(f"[{idx:03d}] {f.name}\n")

    print(f"\n📄 完整书单已生成保存至: {summary_path}")
    print("=" * 65)

if __name__ == "__main__":
    scan_books()