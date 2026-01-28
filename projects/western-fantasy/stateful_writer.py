"""
集成状态系统的写作脚本 v3
特点：
1. 写作前自动加载当前状态作为上下文
2. 写作后自动提取变化并更新状态
3. 一致性检查
"""

import os
import sys
import json
import time
from pathlib import Path
from openai import OpenAI

# 导入状态管理器
from story_state_manager import (
    StoryStateManager,
    get_writing_context,
    update_state_after_writing,
    check_chapter_consistency
)

PROJECT_PATH = Path(r"e:\Test\xiaoshuo\projects\western-fantasy")

# 加载API密钥
with open(r"e:\Test\xiaoshuo\deepseek_api.txt", 'r') as f:
    API_KEY = f.read().strip()

client = OpenAI(api_key=API_KEY, base_url="https://api.deepseek.com")

# 第二卷章节规划（61-90）
CHAPTERS = {
    61: ("春日新篇", "春天到来，规划新一年的发展"),
    62: ("商队归来", "马库斯商队带来消息和物资"),
    63: ("边境警报", "魔兽异动加剧，边境形势紧张"),
    64: ("防御工事", "加强领地防御，修建城墙"),
    65: ("新移民潮", "更多流民涌入，人口增长"),
    66: ("扩张计划", "制定领地扩张计划"),
    67: ("开拓新地", "开垦新的农田"),
    68: ("水利升级", "升级灌溉系统"),
    69: ("铁矿消息", "发现可用的铁矿"),
    70: ("矿区开发", "开始铁矿开采"),
    # ... 后续章节可继续添加
}


def load_prev_chapter_content(chapter_num: int, chars: int = 2000) -> str:
    """加载前一章结尾"""
    chapter_dir = PROJECT_PATH / "chapters" / "v01"
    for f in chapter_dir.glob(f"第{chapter_num - 1}章_*.txt"):
        with open(f, 'r', encoding='utf-8') as file:
            content = file.read()
            return content[-chars:]
    return ""


def generate_chapter_outline(chapter_num: int, title: str, main_content: str, state_context: str) -> str:
    """使用Reasoner生成章纲（带状态上下文）"""
    
    prompt = f"""你是专业的网络小说策划编辑。请为第{chapter_num}章生成详细的章纲。

{state_context}

## 本章信息
- 章节号：第{chapter_num}章
- 标题：{title}
- 核心内容：{main_content}

## 输出要求
请输出完整的章纲，包含：
1. 本章目的（3点）
2. 场景安排（3-4个场景，各1500-2000字）
3. 每个场景的：地点、人物、核心事件、氛围
4. 关键对话要点
5. 本章结尾悬念

请确保：
- 符合当前故事状态（主角境界、位置等）
- 延续前文剧情
- 避免使用现代词汇
"""

    response = client.chat.completions.create(
        model="deepseek-reasoner",
        messages=[
            {"role": "system", "content": "你是资深网络小说策划，擅长西幻种田流章节设计。"},
            {"role": "user", "content": prompt}
        ],
        max_tokens=3000
    )
    
    return response.choices[0].message.content


def write_chapter_content(chapter_num: int, outline: str, state_context: str, prev_ending: str) -> str:
    """写作章节正文"""
    
    prompt = f"""你是专业的网络小说写手。请根据以下章纲写作完整的章节正文。

{state_context}

## 章纲
{outline}

## 前一章结尾（续写参考）
{prev_ending}

## 写作要求
1. **字数**：8000-10000字
2. **风格**：流畅自然的网文风格
3. **POV**：主角艾伦第三人称视角
4. **节奏**：张弛有度
5. **禁止**：
   - 章节标题、作者备注
   - 现代词汇（电脑、手机、网络、投资等）
   - 开头用俗套描写

## 特别注意
- 主角当前境界必须与状态一致
- 角色言行符合已建立的性格
- 不要重复已解决的问题

请直接输出章节正文：
"""

    response = client.chat.completions.create(
        model="deepseek-reasoner",
        messages=[
            {"role": "system", "content": "你是顶级网络小说写手，文风流畅，人物鲜活，擅长西幻种田流。"},
            {"role": "user", "content": prompt}
        ],
        max_tokens=12000
    )
    
    return response.choices[0].message.content


def save_chapter(chapter_num: int, title: str, content: str) -> Path:
    """保存章节"""
    chapter_dir = PROJECT_PATH / "chapters" / "v01"
    chapter_dir.mkdir(parents=True, exist_ok=True)
    
    safe_title = title.replace(":", "：").replace("/", "_").replace("\\", "_")
    safe_title = safe_title.replace("?", "？").replace("*", "_").replace('"', "'")
    
    filename = f"第{chapter_num}章_{safe_title}.txt"
    filepath = chapter_dir / filename
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"第{chapter_num}章 {title}\n\n")
        f.write(content)
    
    return filepath


def save_outline(chapter_num: int, outline: str):
    """保存章纲"""
    outline_dir = PROJECT_PATH / "outline" / "L3-chapters"
    outline_dir.mkdir(parents=True, exist_ok=True)
    
    filepath = outline_dir / f"v01-c{chapter_num:03d}.md"
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(outline)


def run_stateful_writing(start_chapter: int, end_chapter: int):
    """运行带状态管理的写作"""
    
    print("=" * 60)
    print(f"🚀 状态感知写作：第{start_chapter}章 到 第{end_chapter}章")
    print("=" * 60)
    
    manager = StoryStateManager()
    total_words = 0
    stats = {"success": 0, "failed": 0, "issues": []}
    
    for chapter in range(start_chapter, end_chapter + 1):
        print(f"\n📝 第{chapter}章...")
        
        if chapter not in CHAPTERS:
            print(f"  ⚠️ 未找到章节规划，跳过")
            continue
        
        title, main_content = CHAPTERS[chapter]
        
        try:
            # 1. 获取当前状态上下文
            print(f"  📋 加载状态上下文...")
            state_context = manager.generate_context_for_writing(chapter)
            
            # 2. 加载前一章结尾
            prev_ending = load_prev_chapter_content(chapter)
            
            # 3. 生成章纲
            print(f"  📋 Reasoner生成章纲...")
            outline = generate_chapter_outline(chapter, title, main_content, state_context)
            save_outline(chapter, outline)
            time.sleep(2)
            
            # 4. 写作正文
            print(f"  ✍️ Reasoner写作正文...")
            content = write_chapter_content(chapter, outline, state_context, prev_ending)
            time.sleep(2)
            
            # 5. 一致性检查
            print(f"  🔍 一致性检查...")
            issues = check_chapter_consistency(chapter, content)
            if issues:
                for issue in issues:
                    print(f"    ⚠️ {issue}")
                    stats["issues"].append(f"第{chapter}章: {issue}")
            
            # 6. 保存
            save_chapter(chapter, title, content)
            word_count = len(content)
            total_words += word_count
            print(f"  📊 字数：{word_count}")
            
            # 7. 更新状态
            print(f"  🔄 更新故事状态...")
            changes = manager.extract_state_changes(chapter, content)
            if changes:
                manager.update_state_after_chapter(chapter, changes)
            
            stats["success"] += 1
            print(f"  ✅ 完成")
            
            time.sleep(3)
            
        except Exception as e:
            print(f"  ❌ 错误: {e}")
            stats["failed"] += 1
        
        # 每5章报告
        if chapter % 5 == 0:
            print(f"\n{'=' * 40}")
            print(f"📊 进度：{chapter - start_chapter + 1}/{end_chapter - start_chapter + 1}")
            print(f"   总字数：{total_words:,}")
            print(f"{'=' * 40}\n")
    
    # 最终报告
    print("\n" + "=" * 60)
    print("📊 写作完成报告")
    print("=" * 60)
    print(f"  成功：{stats['success']} 章")
    print(f"  失败：{stats['failed']} 章")
    print(f"  总字数：{total_words:,}")
    
    if stats["issues"]:
        print("\n⚠️ 一致性问题：")
        for issue in stats["issues"]:
            print(f"  - {issue}")
    
    return stats


if __name__ == "__main__":
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 61
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 70
    
    run_stateful_writing(start, end)
