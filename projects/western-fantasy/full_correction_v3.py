"""
全面校正脚本 v3
修复用户报告的所有问题
"""

import os
import sys
import re
from pathlib import Path

PROJECT_PATH = Path(r"e:\Test\xiaoshuo\projects\western-fantasy")
CHAPTERS_PATH = PROJECT_PATH / "chapters" / "v01"

# 统一设定
SETTINGS = {
    "protagonist_age": 17,
    "protagonist_past_job": "城市筹谋师",  # 不用"规划师"保持西幻感
    "father_status": "已故于边境战役（五年前）",
    "sebastian_self_refer": "我",  # 不用"老朽"
    "time_start": "初秋",
}

def fix_chapter(filepath: Path) -> dict:
    """修复单个章节"""
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    fixes = []
    
    # 1. "老朽" → "我"（塞巴斯自称）
    if "老朽" in content:
        count = content.count("老朽")
        content = content.replace("老朽", "我")
        fixes.append(f"老朽→我: {count}处")
    
    # 2. "工程师" → "城市筹谋者"或去掉
    if "工程师" in content:
        count = content.count("工程师")
        # 保留"工程师审视项目"这种比喻，改为更通用的描述
        content = content.replace("工程师审视项目", "匠人审视作品")
        content = content.replace("前世是工程师", "前世擅长筹谋规划")
        content = content.replace("工程师", "筹谋者")
        fixes.append(f"工程师修正: {count}处")
    
    # 3. 删除 *** 分隔符
    if "***" in content:
        count = content.count("***")
        content = content.replace("\n***\n", "\n\n")
        content = content.replace("***", "")
        fixes.append(f"删除***: {count}处")
    
    # 4. 将 **文字** 格式改为普通文字（小说不需要markdown）
    # 但保留一些特殊情况（如系统提示）
    pattern = r'\*\*([^*]+)\*\*'
    matches = re.findall(pattern, content)
    if matches:
        # 系统提示保留，其他改为普通文字
        for match in matches:
            if any(kw in match for kw in ["任务", "奖励", "星尘", "系统", "【"]):
                continue  # 保留系统相关的格式
            content = content.replace(f"**{match}**", match)
        fixes.append(f"简化**格式: {len(matches)}处")
    
    # 5. 确保前世职业一致
    content = content.replace("城市规划师", "城市筹谋者")
    
    # 6. 修复"天才地宝"（如果有）
    if "天才地宝" in content:
        content = content.replace("天才地宝", "奇珍异材")
        fixes.append("天才地宝→奇珍异材")
    
    # 7. 将详细列表计划改为概括（针对第7-9章的规划部分）
    # 这需要更复杂的处理，暂时标记
    
    # 保存
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return {"fixed": True, "changes": fixes}
    
    return {"fixed": False, "changes": []}

def run_full_correction():
    """运行全面校正"""
    
    print("=" * 60)
    print("🔧 全面校正：第1-60章")
    print("=" * 60)
    
    stats = {"chapters_fixed": 0, "total_fixes": []}
    
    for i in range(1, 61):
        for filepath in CHAPTERS_PATH.glob(f"第{i}章_*.txt"):
            print(f"\n📖 第{i}章...")
            result = fix_chapter(filepath)
            
            if result["fixed"]:
                stats["chapters_fixed"] += 1
                for change in result["changes"]:
                    print(f"  ✓ {change}")
                    stats["total_fixes"].append(f"第{i}章: {change}")
            else:
                print(f"  ○ 无需修改")
    
    print("\n" + "=" * 60)
    print("📊 校正完成")
    print("=" * 60)
    print(f"  修正章节：{stats['chapters_fixed']} 章")
    print(f"  总修正项：{len(stats['total_fixes'])} 项")
    
    return stats

if __name__ == "__main__":
    run_full_correction()
