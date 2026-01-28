"""
使用DeepSeek Reasoner写作章节
特点：更详细的Prompt、更严谨的逻辑、更好的质量
"""

import os
import sys
import json
import time
import yaml
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

# 章节规划
CHAPTERS = {
    51: ("冬季来临", "准备过冬，储备物资，天气转冷"),
    52: ("严冬挑战", "应对冬季各种困难，暴风雪、物资紧张"),
    53: ("冬日修炼", "利用冬季闭关修炼，感知更进一步"),
    54: ("系统升级", "完成里程碑任务，系统解锁新功能"),
    55: ("情报网络", "开始建立简单的情报系统，塞巴斯主导"),
    56: ("隐患显现", "发现领地内有人暗中作梗，疑似间谍"),
    57: ("清除隐患", "处理内部问题，抓获间谍"),
    58: ("春暖花开", "熬过冬天，迎来新的春天，万物复苏"),
    59: ("凝聚之路", "修炼达到临界点，准备突破"),
    60: ("凝聚者", "突破凝聚者境界，第二篇结束"),
}

# 世界观详细设定
WORLDBOOK = """
## 主角信息
- **姓名**：艾伦·诺斯
- **身份**：诺斯领领主（原诺斯家庶子）
- **年龄**：25岁
- **前世**：现代城市规划师
- **性格**：务实冷静，善于规划，不冲动，重信守诺
- **当前境界**：感知者中期，即将突破凝聚者

## 金手指：星辰系统
- 每日抽奖（普通70%，精良20%，稀有8%，史诗1.5%，传说0.5%）
- 任务系统（里程碑任务、日常任务）
- 系统空间（存储物品）
- 技能：源素共鸣（感知他人源素波动）

## 境界体系
感知者 → 凝聚者 → 外显者 → 领域者 → 大师 → 圣阶
- 感知者：能感知源素，无法外放
- 凝聚者：能将源素凝聚于体内，强化身体
- 外显者：能将源素外放，形成攻击或防御

## 核心配角
- **塞巴斯**：老管家，60岁，忠诚，识字不多，熟悉贵族礼仪
- **格雷**：流民首领，35岁，前军人，武力担当，沉稳多疑
- **托尔**：铁匠，50岁，技艺精湛，沉默寡言
- **汤姆**：马厩学徒，15岁，勤奋好学，跟随艾伦

## 领地现状（第50章后）
- 人口：约420人
- 设施：城堡（修缮中）、锻造坊、面包房、水渠
- 军事：巡逻队20人，民兵50人
- 经济：与马库斯商队建立贸易关系
- 粮食：可支撑过冬，但紧张

## 写作禁忌
- 禁止使用：电脑、手机、网络、汽车、互联网、现金流、投资回报
- 替代词：规划→筹谋、机制→法子、标准→规格、投资→付出
- 时间表达：用"一刻钟"、"半个时辰"代替"半小时"
"""

def load_prev_chapters_summary(current_chapter: int) -> str:
    """加载前几章的摘要"""
    summaries = []
    chapter_dir = PROJECT_PATH / "chapters" / "v01"
    
    for i in range(max(1, current_chapter - 3), current_chapter):
        for f in chapter_dir.glob(f"第{i}章_*.txt"):
            with open(f, 'r', encoding='utf-8') as file:
                content = file.read()
                # 提取前500字作为摘要
                summaries.append(f"第{i}章摘要：{content[:500]}...")
    
    return "\n\n".join(summaries[-2:])  # 只取最近2章

def load_prev_chapter_ending(current_chapter: int) -> str:
    """加载前一章结尾"""
    chapter_dir = PROJECT_PATH / "chapters" / "v01"
    
    for f in chapter_dir.glob(f"第{current_chapter - 1}章_*.txt"):
        with open(f, 'r', encoding='utf-8') as file:
            content = file.read()
            return content[-2000:]  # 最后2000字
    
    return ""

def generate_chapter_with_reasoner(chapter: int, title: str, main_content: str) -> tuple:
    """使用Reasoner生成章纲和正文"""
    
    prev_summary = load_prev_chapters_summary(chapter)
    prev_ending = load_prev_chapter_ending(chapter)
    
    # 第一步：生成详细章纲
    outline_prompt = f"""你是一位专业的网络小说策划编辑。请为第{chapter}章生成详细的章纲。

## 世界观设定
{WORLDBOOK}

## 前情提要
{prev_summary}

## 本章信息
- 章节号：第{chapter}章
- 标题：{title}
- 核心内容：{main_content}

## 输出要求
请输出完整的章纲，包含：
1. 本章目的（3点，用"- [ ]"格式）
2. 场景安排（3-4个场景，各1500-2000字）
3. 每个场景的：地点、人物、核心事件、氛围
4. 关键对话要点（2-3句）
5. 本章结尾悬念

请确保：
- 符合中世纪西幻设定
- 避免现代词汇
- 逻辑严谨，人物行为合理
"""

    print(f"  📋 Reasoner生成章纲...")
    outline_response = client.chat.completions.create(
        model="deepseek-reasoner",
        messages=[
            {"role": "system", "content": "你是一位资深网络小说策划编辑，擅长西幻种田流小说的章节设计。"},
            {"role": "user", "content": outline_prompt}
        ],
        max_tokens=3000
    )
    outline = outline_response.choices[0].message.content
    
    time.sleep(2)  # 避免限流
    
    # 第二步：根据章纲写作正文
    writing_prompt = f"""你是一位专业的网络小说写手。请根据以下章纲写作完整的章节正文。

## 世界观设定
{WORLDBOOK}

## 章纲
{outline}

## 前一章结尾（续写参考）
{prev_ending}

## 写作要求
1. **字数**：8000-10000字
2. **风格**：流畅自然的网文风格，对话和描写穿插
3. **POV**：主角艾伦第三人称视角
4. **节奏**：张弛有度，不要太赶
5. **细节**：适当的环境描写和心理描写
6. **对话**：自然，符合人物身份和性格
7. **禁止**：
   - 章节标题、作者备注
   - 现代词汇（电脑、手机、网络等）
   - 过于书面化的成语堆砌
   - 开头用"晨曦"、"阳光洒下"等俗套

## 特别注意
- 这是中世纪西幻世界，不是现代世界
- 主角有前世记忆，但对话时要用符合时代的表达
- 保持主角务实冷静的性格
- 配角要有个性，不是工具人

请直接输出章节正文，开头直接进入场景。
"""

    print(f"  ✍️ Reasoner写作正文...")
    content_response = client.chat.completions.create(
        model="deepseek-reasoner",
        messages=[
            {"role": "system", "content": "你是一位顶级网络小说写手，擅长西幻种田流。文风流畅自然，人物鲜活，节奏把控精准。"},
            {"role": "user", "content": writing_prompt}
        ],
        max_tokens=12000
    )
    content = content_response.choices[0].message.content
    
    return outline, content

def save_chapter(chapter: int, title: str, content: str):
    """保存章节"""
    chapter_dir = PROJECT_PATH / "chapters" / "v01"
    chapter_dir.mkdir(parents=True, exist_ok=True)
    
    # 清理标题
    safe_title = title.replace(":", "：").replace("/", "_").replace("\\", "_")
    safe_title = safe_title.replace("?", "？").replace("*", "_").replace('"', "'")
    
    filename = f"第{chapter}章_{safe_title}.txt"
    filepath = chapter_dir / filename
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"第{chapter}章 {title}\n\n")
        f.write(content)
    
    print(f"  ✅ 已保存：{filename}")
    return filepath

def save_outline(chapter: int, outline: str):
    """保存章纲"""
    outline_dir = PROJECT_PATH / "outline" / "L3-chapters"
    outline_dir.mkdir(parents=True, exist_ok=True)
    
    filepath = outline_dir / f"v01-c{chapter:03d}.md"
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(outline)
    
    return filepath

def run_reasoner_write(start_chapter: int = 51, end_chapter: int = 60):
    """使用Reasoner写作"""
    
    print("=" * 60)
    print(f"🧠 使用DeepSeek Reasoner写作：第{start_chapter}章 到 第{end_chapter}章")
    print("=" * 60)
    
    total_words = 0
    stats = {"success": 0, "failed": 0}
    
    for chapter in range(start_chapter, end_chapter + 1):
        print(f"\n📝 处理第{chapter}章...")
        
        if chapter not in CHAPTERS:
            print(f"  ⚠️ 未找到章节规划")
            continue
        
        title, main_content = CHAPTERS[chapter]
        
        try:
            # 生成章纲和正文
            outline, content = generate_chapter_with_reasoner(chapter, title, main_content)
            
            # 保存
            save_outline(chapter, outline)
            save_chapter(chapter, title, content)
            
            # 统计
            word_count = len(content)
            total_words += word_count
            stats["success"] += 1
            
            print(f"  📊 字数：{word_count}")
            
            # 每5章报告
            if chapter % 5 == 0:
                print(f"\n{'=' * 40}")
                print(f"📊 进度：{chapter - start_chapter + 1}/{end_chapter - start_chapter + 1}")
                print(f"   总字数：{total_words:,}")
                print(f"{'=' * 40}\n")
            
            time.sleep(3)  # 避免限流
            
        except Exception as e:
            print(f"  ❌ 错误：{e}")
            stats["failed"] += 1
    
    # 最终报告
    print("\n" + "=" * 60)
    print("📊 Reasoner写作完成报告")
    print("=" * 60)
    print(f"  成功：{stats['success']} 章")
    print(f"  失败：{stats['failed']} 章")
    print(f"  总字数：{total_words:,}")
    
    return stats

if __name__ == "__main__":
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 51
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    
    run_reasoner_write(start, end)
