"""
章节导入脚本 - 批量将历史章节导入 SimpleMem 记忆库
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

# 添加项目路径
PROJECT_PATH = Path(r"e:\Test\xiaoshuo\projects\western-fantasy")
sys.path.insert(0, str(PROJECT_PATH))

from story_memory_adapter import StoryMemoryAdapter


def parse_range(range_str: str) -> tuple:
    """解析章节范围字符串，如 '1-60' 或 '1,5,10'"""
    if '-' in range_str:
        parts = range_str.split('-')
        return (int(parts[0]), int(parts[1]))
    else:
        # 逗号分隔的列表
        chapters = [int(c.strip()) for c in range_str.split(',')]
        return (min(chapters), max(chapters))


def import_chapters(
    start: int = 1,
    end: int = 60,
    clear_db: bool = False,
    test_mode: bool = False
):
    """
    导入章节到记忆库
    
    Args:
        start: 起始章节
        end: 结束章节
        clear_db: 是否清空现有数据库
        test_mode: 测试模式（只导入前5章）
    """
    print("=" * 60)
    print("📚 SimpleMem 章节导入工具")
    print("=" * 60)
    print(f"📅 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📖 范围: 第{start}章 到 第{end}章")
    print(f"🗑️  清空数据库: {'是' if clear_db else '否'}")
    print(f"🧪 测试模式: {'是' if test_mode else '否'}")
    print("=" * 60)
    
    if test_mode:
        end = min(start + 4, end)
        print(f"⚠️  测试模式：只导入第{start}章到第{end}章")
    
    # 初始化适配器
    adapter = StoryMemoryAdapter(clear_db=clear_db)
    
    # 导入章节
    stats = adapter.import_all_chapters((start, end))
    
    # 打印统计
    print("\n" + "=" * 60)
    print("📊 导入报告")
    print("=" * 60)
    print(f"✅ 成功导入: {stats['total_chapters']} 章")
    print(f"📝 记忆片段: {stats['total_segments']} 个")
    
    if stats['failed_chapters']:
        print(f"❌ 失败章节: {stats['failed_chapters']}")
    
    # 测试查询
    print("\n" + "=" * 60)
    print("🔍 验证查询测试")
    print("=" * 60)
    
    test_queries = [
        "艾伦的修炼境界是什么？",
        "格雷是什么身份？",
        "诺斯领有哪些设施？"
    ]
    
    for query in test_queries:
        print(f"\n❓ {query}")
        result = adapter.query_context(query)
        print(f"💬 {result[:300]}..." if len(result) > 300 else f"💬 {result}")
    
    print("\n" + "=" * 60)
    print("✅ 导入完成！")
    print("=" * 60)
    
    return stats


def main():
    parser = argparse.ArgumentParser(description='将小说章节导入 SimpleMem 记忆库')
    parser.add_argument(
        '--chapters', '-c',
        type=str,
        default='1-60',
        help='章节范围，如 1-60 或 1,5,10'
    )
    parser.add_argument(
        '--clear', '-x',
        action='store_true',
        help='清空现有数据库'
    )
    parser.add_argument(
        '--test', '-t',
        action='store_true',
        help='测试模式（只导入前5章）'
    )
    
    args = parser.parse_args()
    
    # 解析章节范围
    start, end = parse_range(args.chapters)
    
    # 执行导入
    import_chapters(
        start=start,
        end=end,
        clear_db=args.clear,
        test_mode=args.test
    )


if __name__ == "__main__":
    main()
