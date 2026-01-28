"""
核心设定一致性修复脚本
修复祖父/父亲矛盾、前世职业等关键不一致问题
"""

import re
from pathlib import Path

PROJECT_PATH = Path(r"e:\Test\xiaoshuo\projects\western-fantasy")
CHAPTERS_PATH = PROJECT_PATH / "chapters" / "v01"

# 正确的设定（根据第4、7、8、9章多处描述）
CORRECT_SETTINGS = """
正确设定（已从多章节确认）：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【家族谱系】
- 曾祖父：开创诺斯领，建造城堡（120年前）
- 祖父（埃德加·诺斯）：外显者高阶，二十年前边境战争中战死
- 父亲（斯蒂芬·诺斯）：现任家主，凝聚者巅峰，在世
- 主角（艾伦·诺斯）：17岁庶子

【排挤原因】
- 庶子身份（母亲是小贵族之女，非正妻）
- 母亲已故（几年前病逝）
- 家族衰落，资源紧张，庶子不受重视
- 被"发配"到偏远别院"静养"

【住处描写统一】
- 第1-6章：诺斯本家的偏远别院（王都边缘）
  - 二楼石墙房间，木框窗
  - 别院有几间木屋围成小院
- 第7章起：启程前往诺斯领
- 第18章起：诺斯堡（领地城堡）

【前世职业】
- 林远/艾伦前世：城市规划师、项目经理
- 不用"工程师"

【系统设定】
- 第4章激活系统，包含仓库功能
- 第一次抽奖在第4章（半价，得高产小麦种子）
- 第5章是第二次抽奖（全价，得《源素基础导引法》）
"""

def fix_chapter_5():
    """修复第5章：父亲→祖父"""
    filepath = list(CHAPTERS_PATH.glob("第5章_*.txt"))[0]
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 核心问题：第5行说"父亲战死"，应该是"祖父战死"
    # 原文：二十年前老诺斯男爵——也就是他这具身体的父亲——在一次边境冲突中战死
    # 修复：二十年前老诺斯男爵——也就是他这具身体的祖父——在一次边境冲突中战死
    
    old_text = "二十年前老诺斯男爵——也就是他这具身体的父亲——在一次边境冲突中战死"
    new_text = "二十年前老诺斯男爵——也就是他这具身体的祖父——在一次边境冲突中战死"
    
    if old_text in content:
        content = content.replace(old_text, new_text)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print("  ✓ 第5章：父亲→祖父（战死者）")
        return True
    
    print("  ○ 第5章：未找到需要修改的内容或已修复")
    return False

def fix_chapter_6():
    """修复第6章：前世职业"""
    filepath = list(CHAPTERS_PATH.glob("第6章_*.txt"))[0]
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    changes = []
    
    # 工程师问题已在v3脚本中修复为"筹谋者"
    # 这里检查是否还有遗漏
    if "工程师" in content:
        content = content.replace("工程师", "筹谋者")
        changes.append("工程师→筹谋者")
    
    if "规划师" in content:
        content = content.replace("规划师", "筹谋者")
        changes.append("规划师→筹谋者")
    
    if changes:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  ✓ 第6章：{', '.join(changes)}")
        return True
    
    print("  ○ 第6章：无需修改")
    return False

def check_all_chapters_for_setting_conflicts():
    """检查所有章节的设定冲突"""
    
    conflicts = []
    
    # 检查祖父/父亲战死的描述
    for filepath in sorted(CHAPTERS_PATH.glob("第*.txt")):
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查"父亲战死"（错误）
        if re.search(r'父亲.{0,10}战死', content):
            # 排除正确的"祖父战死"
            if "祖父" not in content[:content.find("战死")+10]:
                match = re.search(r'.{0,30}父亲.{0,10}战死.{0,30}', content)
                if match:
                    conflicts.append(f"{filepath.name}: {match.group()}")
    
    return conflicts

def update_story_state():
    """更新story_state.json为正确设定"""
    state_path = PROJECT_PATH / "worldbook" / "dynamic" / "story_state.json"
    
    import json
    
    with open(state_path, 'r', encoding='utf-8') as f:
        state = json.load(f)
    
    # 添加祖父信息，修正父亲信息
    state["characters"]["祖父（埃德加·诺斯）"] = {
        "role": "已故祖父",
        "status": "已故",
        "death": "二十年前边境战争中战死",
        "realm": "外显者高阶"
    }
    
    state["characters"]["父亲（斯蒂芬·诺斯）"] = {
        "role": "现任家主",
        "status": "在世",
        "location": "诺斯本家（王都）",
        "realm": "凝聚者巅峰",
        "relationship": "冷淡疏离"
    }
    
    # 更新主角背景
    state["protagonist"]["background"] = {
        "status": "庶子",
        "mother": "已故（几年前病逝）",
        "exclusion_reason": "庶子身份、母亲去世、家族资源紧张",
        "current_residence": "诺斯本家偏远别院 → 诺斯堡"
    }
    
    with open(state_path, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    
    print("  ✓ story_state.json 已更新")

def main():
    print("=" * 60)
    print("🔧 核心设定一致性修复")
    print("=" * 60)
    
    print(CORRECT_SETTINGS)
    
    print("\n━━━ 开始修复 ━━━\n")
    
    print("📖 修复第5章（祖父/父亲设定）...")
    fix_chapter_5()
    
    print("\n📖 修复第6章（前世职业）...")
    fix_chapter_6()
    
    print("\n📖 检查所有章节设定冲突...")
    conflicts = check_all_chapters_for_setting_conflicts()
    if conflicts:
        print("  ⚠️ 发现可能的冲突：")
        for c in conflicts:
            print(f"    - {c}")
    else:
        print("  ✓ 未发现明显冲突")
    
    print("\n📖 更新story_state.json...")
    update_story_state()
    
    print("\n" + "=" * 60)
    print("✅ 核心设定修复完成")
    print("=" * 60)

if __name__ == "__main__":
    main()
