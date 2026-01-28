"""
深度设定一致性修复脚本
修复用户报告的特定问题
"""

import re
from pathlib import Path

PROJECT_PATH = Path(r"e:\Test\xiaoshuo\projects\western-fantasy")
CHAPTERS_PATH = PROJECT_PATH / "chapters" / "v01"

# 统一设定（用于修复）
CANONICAL_SETTINGS = {
    # 父亲设定：二十年前战死
    "father_death_time": "二十年前",
    
    # 主角前世职业
    "past_job": "城市筹谋者",  # 不用"规划师"、"工程师"
    
    # 塞巴斯自称
    "sebastian_self": "我",  # 不用"老朽"
    
    # 主角年龄：17岁
    "protagonist_age": 17,
}

def fix_chapter_4():
    """修复第4章：系统仓库应该是可用的，高产小麦种子是第一次抽奖结果"""
    filepath = list(CHAPTERS_PATH.glob("第4章_*.txt"))[0]
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 第4章应该包含：
    # 1. 系统激活
    # 2. 仓库功能介绍
    # 3. 第一次抽奖（半价）得到高产小麦种子
    
    # 检查是否有"昨晚抽到"这种时间错乱
    if "昨晚抽到" in content:
        content = content.replace("昨晚抽到的高产小麦种子", "刚才抽到的高产小麦种子")
        print("  ✓ 修复时间描述：昨晚→刚才")
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

def fix_chapter_5():
    """修复第5章中的问题"""
    filepath = list(CHAPTERS_PATH.glob("第5章_*.txt"))[0]
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    changes = []
    
    # 1. 确认父亲设定（二十年前战死，这是正确的）
    # 第7行：二十年前老诺斯男爵战死 - 正确，保留
    
    # 2. 修复任何"规划"相关词汇
    if "规划" in content:
        content = content.replace("规划", "筹谋")
        changes.append("规划→筹谋")
    
    # 3. 检查系统仓库描述是否合理
    # 第5章仓库应该已经可用（第4章已激活）
    
    # 4. 修复第5章重复的标题
    if "# 第5章：星辰初现" in content:
        content = content.replace("# 第5章：星辰初现\r\n\r\n", "")
        content = content.replace("# 第5章：星辰初现\n\n", "")
        changes.append("删除重复标题")
    
    if changes:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  ✓ {', '.join(changes)}")

def fix_chapter_6():
    """修复第6章：前世职业"""
    filepath = list(CHAPTERS_PATH.glob("第6章_*.txt"))[0]
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 工程师→城市筹谋者（已在v3中修复为"筹谋者"）
    # 检查是否还有遗漏
    if "工程师" in content or "规划师" in content:
        content = content.replace("工程师", "筹谋者")
        content = content.replace("规划师", "筹谋者")
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print("  ✓ 修复职业描述")

def fix_repeated_descriptions():
    """修复章节间重复描写"""
    # 识别常见的重复描写模式
    repeated_patterns = [
        # 本家困境描写可能每章都有，需要精简
    ]
    
    # 这个功能需要更复杂的AI分析，暂时跳过
    print("  ○ 重复描写需要人工审查")

def fix_season_issues():
    """修复季节相关问题"""
    # 穿越时间：初秋
    # 第一卷结束：冬末
    # 农作物种植需要符合季节
    
    for filepath in sorted(CHAPTERS_PATH.glob("第*.txt")):
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        changes = []
        
        # 春播作物不应在秋天种（除非是冬小麦）
        # 冬小麦是秋播，可以保留
        # 检查是否有不合理的种植描述
        
        # 暂时标记需要检查的章节
        if "春天" in content and "种植" in content:
            print(f"  ⚠️ {filepath.name}: 可能存在季节问题，需人工检查")

def fix_house_descriptions():
    """修复宅邸描写一致性"""
    # 统一诺斯本家宅邸描写
    # 主角住处：西侧偏僻的别院（不是客房）
    
    for i in range(1, 11):
        for filepath in CHAPTERS_PATH.glob(f"第{i}章_*.txt"):
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if "客房" in content and "艾伦住" in content:
                content = content.replace("客房", "别院")
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"  ✓ {filepath.name}: 客房→别院")

def main():
    print("=" * 60)
    print("🔧 深度设定一致性修复")
    print("=" * 60)
    
    print("\n📖 第4章...")
    fix_chapter_4()
    
    print("\n📖 第5章...")
    fix_chapter_5()
    
    print("\n📖 第6章...")
    fix_chapter_6()
    
    print("\n📖 检查季节问题...")
    fix_season_issues()
    
    print("\n📖 检查宅邸描写...")
    fix_house_descriptions()
    
    print("\n📖 重复描写检查...")
    fix_repeated_descriptions()
    
    print("\n" + "=" * 60)
    print("✅ 深度修复完成")
    print("=" * 60)

if __name__ == "__main__":
    main()
