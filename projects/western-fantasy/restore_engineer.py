"""
恢复"工程师"设定
将之前改成"筹谋者"的地方改回"工程师"
"""

import re
from pathlib import Path

PROJECT_PATH = Path(r"e:\Test\xiaoshuo\projects\western-fantasy")
CHAPTERS_PATH = PROJECT_PATH / "chapters" / "v01"

def restore_engineer():
    """恢复工程师设定"""
    
    fixed_count = 0
    
    for filepath in sorted(CHAPTERS_PATH.glob("第*.txt")):
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original = content
        
        # 恢复前世职业描述
        content = content.replace("前世擅长筹谋规划", "前世是工程师")
        content = content.replace("匠人审视作品", "工程师审视项目现场")
        content = content.replace("城市筹谋者", "城市规划工程师")
        
        # 只在明确是前世职业描述时恢复
        # 不改变其他"筹谋者"（可能是本世界的表述）
        
        if content != original:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            fixed_count += 1
            print(f"  ✓ {filepath.name}")
    
    print(f"\n已恢复 {fixed_count} 个文件")

if __name__ == "__main__":
    print("🔧 恢复'工程师'设定")
    print("=" * 40)
    restore_engineer()
