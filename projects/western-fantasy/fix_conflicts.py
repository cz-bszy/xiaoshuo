"""
冲突章节修复脚本
使用 DeepSeek API + SimpleMem 记忆上下文重写有冲突的章节
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime
from openai import OpenAI

# 项目路径
PROJECT_PATH = Path(r"e:\Test\xiaoshuo\projects\western-fantasy")
SIMPLEMEM_PATH = Path(r"e:\Test\xiaoshuo\SimpleMem")
sys.path.insert(0, str(PROJECT_PATH))
sys.path.insert(0, str(SIMPLEMEM_PATH))

from story_memory_adapter import StoryMemoryAdapter

# 加载API密钥
with open(r"e:\Test\xiaoshuo\deepseek_api.txt", 'r') as f:
    API_KEY = f.read().strip()

client = OpenAI(api_key=API_KEY, base_url="https://api.deepseek.com")

# 需要修复的章节及其冲突描述
CONFLICT_CHAPTERS = {
    5: {
        "title": "第一次抽奖",
        "conflict": "关于'第一次系统抽取'的描述存在矛盾。前文说用10星尘抽取获得《元素基础引导法》，但本章说第一次抽取获得的是《高效犁具蓝图》。",
        "fix_instruction": "统一'第一次抽奖'的描述，确保获得的物品与前文一致。保留《元素基础引导法》作为第一次抽奖的奖励。"
    },
    17: {
        "title": "第一滴血",
        "conflict": "Jack在前文已明确死亡，但本章中Jack再次出现并重复死亡前的对话。",
        "fix_instruction": "确保Jack的死亡时间点正确。如果Jack在本章死亡，删除前文中关于他已死的描述；如果他在前文已死，本章不应出现活着的Jack。"
    },
    22: {
        "title": "人心",
        "conflict": "Allen'决定'去River Valley Village并宣布开荒雇佣计划，但这些事件在前文已经发生过，本章却再次作为新事件描述。",
        "fix_instruction": "删除重复的'决定'描述，或将其改写为回忆/执行已决定的事项。避免重复叙述已发生的事件。"
    },
    28: {
        "title": "巡逻队",
        "conflict": "前文描述North Castle为废墟，但本章中Allen却站在完好的庭院中，无任何修复说明。",
        "fix_instruction": "添加城堡修缮的说明，或者明确描述当前是'修缮后的简易庭院'，不要描述成完好的城堡。"
    },
    34: {
        "title": "水利工程",
        "conflict": "Allen已将'高品质铁锭兑换券'给予Thor，但本章再次将同一凭证给予Thor。",
        "fix_instruction": "删除重复给予物品的情节，或者改为给予其他物品/奖励。"
    },
    57: {
        "title": "清除隐患",
        "conflict": "Leon已被判处永久流放（permanent exile），但本章他仍以'水渠材料管理员'身份出现在Northshire。",
        "fix_instruction": "修正Leon的状态：要么删除前文的流放判决，要么在本章解释为什么他能回来（如被赦免、偷偷潜回等）。"
    }
}


def load_chapter_content(chapter: int) -> str:
    """加载原章节内容"""
    chapter_dir = PROJECT_PATH / "chapters" / "v01"
    for f in chapter_dir.glob(f"第{chapter}章_*.txt"):
        with open(f, 'r', encoding='utf-8') as file:
            return file.read()
    return ""


def get_memory_context(adapter: StoryMemoryAdapter, chapter: int, conflict_info: dict) -> str:
    """获取与冲突相关的记忆上下文"""
    # 提取冲突中的关键实体
    keywords = conflict_info["conflict"]
    
    # 查询相关记忆
    context_parts = []
    
    # 1. 查询前文关于本章涉及主题的记忆
    context_parts.append(f"## 第{chapter}章之前的相关记忆\n")
    prev_context = adapter.query_context(
        f"第{chapter}章之前发生的重要事件和角色状态",
        max_entries=10
    )
    context_parts.append(prev_context)
    
    # 2. 查询主角状态
    context_parts.append("\n## 艾伦当前状态\n")
    protagonist_context = adapter.query_context("艾伦的修炼境界、位置、能力")
    context_parts.append(protagonist_context)
    
    return "\n".join(context_parts)


def rewrite_chapter(chapter: int, conflict_info: dict, memory_context: str, original_content: str) -> str:
    """使用DeepSeek重写章节"""
    
    prompt = f"""你是一位专业的网络小说修订编辑。请根据以下信息修复章节中的逻辑冲突，重写整章内容。

## 冲突问题
{conflict_info["conflict"]}

## 修复指导
{conflict_info["fix_instruction"]}

## 故事记忆（必须遵守的前文设定）
{memory_context}

## 原章节内容
{original_content[:15000]}

## 修订要求
1. **核心任务**：修复上述冲突，确保本章与前文记忆一致
2. **保持风格**：保持原有的写作风格和叙事节奏
3. **最小改动**：尽量保留原文中没有冲突的部分
4. **字数控制**：与原文字数相近（原文{len(original_content)}字）
5. **自然过渡**：修改后的内容要自然融入，不能有突兀感

## 特别注意
- 严格遵守故事记忆中的设定
- 不要引入新的逻辑冲突
- 保持人物性格一致性
- 使用中世纪西幻世界的表达方式

请直接输出修订后的完整章节内容，开头直接进入场景，不要任何前言或解释。
"""

    print(f"  ✍️ 调用 DeepSeek 重写中...")
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "你是一位资深网络小说修订编辑，擅长发现并修复情节漏洞，同时保持原作风格。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=8192
    )
    
    return response.choices[0].message.content


def backup_chapter(chapter: int, original_content: str):
    """备份原章节"""
    backup_dir = PROJECT_PATH / "backups" / "conflict_fix"
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = backup_dir / f"第{chapter}章_backup_{timestamp}.txt"
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(original_content)
    
    return filepath


def save_fixed_chapter(chapter: int, title: str, content: str):
    """保存修复后的章节"""
    chapter_dir = PROJECT_PATH / "chapters" / "v01"
    
    # 删除旧文件
    for f in chapter_dir.glob(f"第{chapter}章_*.txt"):
        f.unlink()
    
    # 保存新文件
    safe_title = title.replace(":", "：").replace("/", "_")
    filename = f"第{chapter}章_{safe_title}.txt"
    filepath = chapter_dir / filename
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"第{chapter}章 {title}\n\n")
        f.write(content)
    
    return filepath


def run_conflict_fix(chapters_to_fix: list = None):
    """运行冲突修复"""
    
    if chapters_to_fix is None:
        chapters_to_fix = list(CONFLICT_CHAPTERS.keys())
    
    print("=" * 60)
    print(f"🔧 冲突章节修复工具")
    print(f"📅 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📖 修复章节: {chapters_to_fix}")
    print("=" * 60)
    
    # 初始化记忆适配器（不清空数据库）
    print("\n🧠 初始化记忆系统...")
    adapter = StoryMemoryAdapter(clear_db=False)
    
    stats = {"success": 0, "failed": 0, "chapters": []}
    
    for chapter in chapters_to_fix:
        if chapter not in CONFLICT_CHAPTERS:
            print(f"\n⚠️ 第{chapter}章不在冲突列表中，跳过")
            continue
        
        conflict_info = CONFLICT_CHAPTERS[chapter]
        print(f"\n{'=' * 50}")
        print(f"📝 处理第{chapter}章: {conflict_info['title']}")
        print(f"❌ 冲突: {conflict_info['conflict'][:80]}...")
        print("=" * 50)
        
        try:
            # 1. 加载原章节
            original_content = load_chapter_content(chapter)
            if not original_content:
                print(f"  ⚠️ 未找到原章节文件，跳过")
                stats["failed"] += 1
                continue
            
            print(f"  📄 原章节字数: {len(original_content)}")
            
            # 2. 备份
            backup_path = backup_chapter(chapter, original_content)
            print(f"  💾 已备份到: {backup_path.name}")
            
            # 3. 获取记忆上下文
            print(f"  🧠 查询相关记忆...")
            memory_context = get_memory_context(adapter, chapter, conflict_info)
            
            # 4. 重写章节
            fixed_content = rewrite_chapter(chapter, conflict_info, memory_context, original_content)
            
            # 5. 保存
            save_path = save_fixed_chapter(chapter, conflict_info["title"], fixed_content)
            print(f"  ✅ 已保存修复版本: {save_path.name}")
            print(f"  📊 修复后字数: {len(fixed_content)}")
            
            stats["success"] += 1
            stats["chapters"].append({
                "chapter": chapter,
                "original_words": len(original_content),
                "fixed_words": len(fixed_content),
                "status": "success"
            })
            
            # 避免API限流
            time.sleep(3)
            
        except Exception as e:
            print(f"  ❌ 修复失败: {e}")
            stats["failed"] += 1
            stats["chapters"].append({
                "chapter": chapter,
                "status": "failed",
                "error": str(e)
            })
    
    # 最终报告
    print("\n" + "=" * 60)
    print("📊 冲突修复完成报告")
    print("=" * 60)
    print(f"  ✅ 成功: {stats['success']} 章")
    print(f"  ❌ 失败: {stats['failed']} 章")
    
    # 保存报告
    report_path = PROJECT_PATH / "conflict_fix_report.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"  📄 报告已保存: {report_path}")
    
    return stats


if __name__ == "__main__":
    # 默认修复所有冲突章节
    if len(sys.argv) > 1:
        chapters = [int(c) for c in sys.argv[1:]]
    else:
        chapters = None  # 修复所有
    
    run_conflict_fix(chapters)
