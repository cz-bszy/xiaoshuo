"""
全面校正脚本
根据分析报告对1-60章进行自动校正
"""

import os
import sys
import json
import time
import re
from pathlib import Path
from openai import OpenAI

# 项目路径
PROJECT_PATH = Path(r"e:\Test\xiaoshuo\projects\western-fantasy")

# 加载API密钥
with open(r"e:\Test\xiaoshuo\deepseek_api.txt", 'r') as f:
    API_KEY = f.read().strip()

# 初始化客户端
client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.deepseek.com"
)

# 现代词汇替换表（扩展版）
WORD_REPLACEMENTS = {
    # 科技类
    "电脑": "账簿",
    "手机": "传讯石",
    "网络": "消息网",
    "互联网": "情报网络",
    "电力": "源素动力",
    "电视": "水镜",
    "汽车": "马车",
    
    # 商业类
    "投资": "付出",
    "现金流": "进项",
    "投资回报": "收益",
    "创业": "开创基业",
    
    # 管理类
    "规划": "筹谋",
    "机制": "法子",
    "标准": "规格",
    "预警机制": "示警安排",
    "资源栏": "账册",
    "里程碑任务": "关键要事",
    "催化剂": "引子",
    
    # 时间单位
    "半小时": "半个时辰",
    "一小时": "一个时辰",
    "分钟": "刻钟",
    
    # 度量单位（保留但标记）
    # "公里": "里",  # 需要数字转换，谨慎处理
    
    # 比喻类
    "像一台机器": "如一个初醒的巨人",
    "零件": "环节",
    "人体工学": "贴合手形",
    "跳一跳够得着": "量力而行",
}

def load_analysis_report():
    """加载分析报告"""
    report_path = PROJECT_PATH / "analysis_report.json"
    if report_path.exists():
        with open(report_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def load_chapter(chapter_num: int) -> tuple:
    """加载章节内容，返回(路径, 内容)"""
    chapter_dir = PROJECT_PATH / "chapters" / "v01"
    for f in chapter_dir.glob(f"第{chapter_num}章_*.txt"):
        with open(f, 'r', encoding='utf-8') as file:
            return f, file.read()
    return None, ""

def save_chapter(filepath: Path, content: str):
    """保存修正后的章节"""
    # 备份原文件
    backup_path = filepath.with_suffix('.bak')
    if filepath.exists():
        with open(filepath, 'r', encoding='utf-8') as f:
            with open(backup_path, 'w', encoding='utf-8') as bf:
                bf.write(f.read())
    
    # 保存新内容
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

def simple_word_replace(content: str) -> tuple:
    """简单词汇替换"""
    fixed_count = 0
    fixed_words = []
    
    for old_word, new_word in WORD_REPLACEMENTS.items():
        if old_word in content:
            # 检查是否在回忆/前世语境中
            # 简单规则：如果整段包含"前世"或"记忆中"，则可能是回忆，跳过
            count = content.count(old_word)
            content = content.replace(old_word, new_word)
            fixed_count += count
            fixed_words.append(f"{old_word}→{new_word}")
    
    return content, fixed_count, fixed_words

def get_chapter_issues(chapter_num: int, report: list) -> dict:
    """从报告中获取特定章节的问题"""
    for item in report:
        if item.get("chapter") == chapter_num:
            return item.get("analysis", {})
    return {}

def fix_with_reasoner(chapter_num: int, content: str, issues: dict) -> str:
    """使用Reasoner修复具体问题"""
    
    if not issues:
        return content
    
    # 构建修复提示
    fixes_needed = []
    
    # 时代错误
    time_errors = issues.get("time_period_errors", [])
    for error in time_errors[:3]:  # 最多处理3个
        if not error.get("is_flashback", False):
            fixes_needed.append(f"将「{error.get('text', '')}」改为「{error.get('suggestion', '')}」")
    
    # 质量问题
    quality_issues = issues.get("quality_issues", [])
    for issue in quality_issues[:2]:  # 最多处理2个
        fixes_needed.append(f"优化：{issue.get('text', '')[:50]}... → {issue.get('suggestion', '')[:50]}...")
    
    if not fixes_needed:
        return content
    
    prompt = f"""请对以下第{chapter_num}章内容进行修改。

## 需要修改的地方
{chr(10).join([f"{i+1}. {fix}" for i, fix in enumerate(fixes_needed)])}

## 原文内容
{content}

## 要求
1. 只修改上述指出的问题
2. 保持原文的整体结构和风格
3. 不要添加新内容
4. 不要删除重要内容
5. 直接输出修改后的完整章节内容

请直接输出修改后的内容：
"""

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",  # 用chat模型做修改，更快
            messages=[
                {"role": "system", "content": "你是一位专业的网络小说编辑。请根据要求修改文本，保持原有风格。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=8000,
            temperature=0.3  # 低温度保持一致性
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        print(f"    ⚠️ Reasoner修复失败: {e}")
        return content

def run_correction(start_chapter: int = 1, end_chapter: int = 60, use_reasoner: bool = True):
    """运行校正"""
    
    print("=" * 60)
    print(f"🔧 开始校正：第{start_chapter}章 到 第{end_chapter}章")
    print(f"   模式：{'深度修复(Reasoner)' if use_reasoner else '简单替换'}")
    print("=" * 60)
    
    # 加载分析报告
    report = load_analysis_report()
    print(f"📊 加载分析报告：{len(report)} 个章节有详细分析")
    
    stats = {
        "chapters_processed": 0,
        "words_replaced": 0,
        "reasoner_fixes": 0,
        "errors": []
    }
    
    for chapter in range(start_chapter, end_chapter + 1):
        print(f"\n📖 处理第{chapter}章...")
        
        # 加载章节
        filepath, content = load_chapter(chapter)
        if not content:
            print(f"  ⚠️ 未找到章节文件")
            continue
        
        original_length = len(content)
        
        # 1. 简单词汇替换
        content, fix_count, fixed_words = simple_word_replace(content)
        if fix_count > 0:
            print(f"  🔤 替换了 {fix_count} 处词汇")
            stats["words_replaced"] += fix_count
        
        # 2. 使用Reasoner修复特定问题（仅对有分析的章节）
        if use_reasoner:
            issues = get_chapter_issues(chapter, report)
            if issues:
                print(f"  🧠 Reasoner修复问题...")
                content = fix_with_reasoner(chapter, content, issues)
                stats["reasoner_fixes"] += 1
                time.sleep(2)  # 避免限流
        
        # 3. 保存
        if len(content) != original_length or fix_count > 0:
            save_chapter(filepath, content)
            print(f"  ✅ 已保存（{len(content)}字）")
        else:
            print(f"  ○ 无需修改")
        
        stats["chapters_processed"] += 1
        
        # 每10章报告进度
        if chapter % 10 == 0:
            print(f"\n{'=' * 40}")
            print(f"📊 进度：{chapter}/{end_chapter}")
            print(f"   已替换词汇：{stats['words_replaced']}处")
            print(f"   Reasoner修复：{stats['reasoner_fixes']}章")
            print(f"{'=' * 40}\n")
    
    # 最终报告
    print("\n" + "=" * 60)
    print("📊 校正完成报告")
    print("=" * 60)
    print(f"  处理章节：{stats['chapters_processed']} 章")
    print(f"  替换词汇：{stats['words_replaced']} 处")
    print(f"  深度修复：{stats['reasoner_fixes']} 章")
    
    if stats["errors"]:
        print("\n⚠️ 错误列表：")
        for error in stats["errors"]:
            print(f"  - {error}")
    
    return stats

if __name__ == "__main__":
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    use_reasoner = "--no-reasoner" not in sys.argv
    
    run_correction(start, end, use_reasoner)
