"""
全面校正脚本 v4
根据用户确认的新设定进行修正
设定：前世职业=工程师（允许）
"""

import os
import sys
import re
from pathlib import Path

PROJECT_PATH = Path(r"e:\Test\xiaoshuo\projects\western-fantasy")
CHAPTERS_PATH = PROJECT_PATH / "chapters" / "v01"

# 确认的设定
SETTINGS = {
    "protagonist_age": 17,
    "protagonist_past_job": "工程师",  # 用户确认使用工程师
    "grandfather_death": "二十年前边境战役战死",
    "father_status": "在世，现任家主",
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
    
    # 2. 删除 *** 分隔符
    if "***" in content:
        count = content.count("***")
        content = content.replace("\n***\n", "\n\n")
        content = content.replace("***", "")
        fixes.append(f"删除***: {count}处")
    
    # 3. 将 **文字** 格式改为普通文字（小说不需要markdown）
    # 但保留系统提示
    pattern = r'\*\*([^*]+)\*\*'
    matches = re.findall(pattern, content)
    if matches:
        for match in matches:
            if any(kw in match for kw in ["任务", "奖励", "星尘", "系统", "【"]):
                continue  # 保留系统相关的格式
            content = content.replace(f"**{match}**", match)
        fixes.append(f"简化**格式: {len(matches)}处")
    
    # 4. 修复"天才地宝"（如果有）
    if "天才地宝" in content:
        content = content.replace("天才地宝", "奇珍异材")
        fixes.append("天才地宝→奇珍异材")
    
    # 5. 修复"筹谋者"回到"工程师"（用户要求）
    if "前世擅长筹谋规划" in content:
        content = content.replace("前世擅长筹谋规划", "前世是工程师")
        fixes.append("恢复工程师描述")
    
    if "匠人审视作品" in content:
        content = content.replace("匠人审视作品", "工程师审视项目现场")
        fixes.append("恢复工程师比喻")
    
    # 保存
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return {"fixed": True, "changes": fixes}
    
    return {"fixed": False, "changes": []}

def run_full_correction():
    """运行全面校正"""
    
    print("=" * 60)
    print("🔧 全面校正 v4：第1-60章")
    print("   设定：前世职业=工程师")
    print("=" * 60)
    
    stats = {"chapters_fixed": 0, "total_fixes": []}
    
    for i in range(1, 61):
        for filepath in CHAPTERS_PATH.glob(f"第{i}章_*.txt"):
            result = fix_chapter(filepath)
            
            if result["fixed"]:
                stats["chapters_fixed"] += 1
                print(f"📖 第{i}章: {', '.join(result['changes'])}")
                for change in result["changes"]:
                    stats["total_fixes"].append(f"第{i}章: {change}")
    
    print("\n" + "=" * 60)
    print("📊 校正完成")
    print("=" * 60)
    print(f"  修正章节：{stats['chapters_fixed']} 章")
    print(f"  总修正项：{len(stats['total_fixes'])} 项")
    
    return stats

if __name__ == "__main__":
    run_full_correction()
