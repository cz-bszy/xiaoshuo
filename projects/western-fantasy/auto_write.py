"""
自动化写作主脚本
批量生成章纲 + 调用DeepSeek API写作 + 质量检查
"""

import os
import sys
import json
import time
import yaml
from pathlib import Path
from datetime import datetime
from openai import OpenAI
from story_state_manager import StoryStateManager

# 项目路径
PROJECT_PATH = Path(r"e:\Test\xiaoshuo\projects\western-fantasy")
SCRIPTS_PATH = Path(r"e:\Test\xiaoshuo\skills\mega-novel-orchestrator\mega-novel-orchestrator\scripts")

# 加载API密钥
with open(r"e:\Test\xiaoshuo\deepseek_api.txt", 'r') as f:
    API_KEY = f.read().strip()

# 初始化客户端
client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.deepseek.com"
)

# 加载项目配置
with open(PROJECT_PATH / "config.yaml", 'r', encoding='utf-8') as f:
    CONFIG = yaml.safe_load(f)

# 加载世界书
def load_worldbook():
    worldbook = {}
    for name in ["characters", "locations", "rules"]:
        path = PROJECT_PATH / "worldbook" / f"{name}.json"
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                worldbook[name] = json.load(f)
    return worldbook

WORLDBOOK = load_worldbook()

# 加载创作宪法和规格
def load_constitution():
    path = PROJECT_PATH / "constitution.md"
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    return ""

def load_specification():
    path = PROJECT_PATH / "specification.md"
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    return ""

CONSTITUTION = load_constitution()
SPECIFICATION = load_specification()

# 加载卷纲和篇纲
def load_volume_outline(volume: int):
    path = PROJECT_PATH / "outline" / "L1-volumes" / f"v{volume:02d}.md"
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    return ""

def load_part_outline(volume: int, part: int):
    path = PROJECT_PATH / "outline" / "L2-parts" / f"v{volume:02d}-p{part:02d}.md"
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    return ""

# 生成章纲
def generate_chapter_outline(volume: int, chapter: int, title: str, main_content: str):
    """使用DeepSeek生成章纲"""
    
    volume_outline = load_volume_outline(volume)
    part = (chapter - 1) // 30 + 1  # 每30章一篇
    part_outline = load_part_outline(volume, part)
    
    prompt = f"""你是一位专业的网络小说策划编辑。请根据以下信息，为第{chapter}章生成详细的章纲。

## 故事规格（摘要）
{SPECIFICATION[:2000]}

## 第{volume}卷大纲
{volume_outline[:1500]}

## 本篇大纲
{part_outline[:1500]}

## 本章信息
- 章节号：第{chapter}章
- 参考标题：{title}
- 主要内容：{main_content}

请按以下格式输出章纲：

# 第{chapter}章：[正式标题]

## 基本信息
- **字数目标**：5000字
- **POV**：主角第三人称
- **时间**：[故事时间]
- **地点**：[场景地点]

## 本章目的
- [ ] [目的1]
- [ ] [目的2]
- [ ] [目的3]

## 场景安排

### 场景1：[场景名]（约1500字）
**内容**：
- [要点1]
- [要点2]
**氛围**：[氛围描述]

### 场景2：[场景名]（约1500字）
[同上格式]

### 场景3：[场景名]（约1200字）
[同上格式]

### 场景4：[场景名]（约800字）
[同上格式]

## 写作要点
1. [要点1]
2. [要点2]

## 注意事项
- ❌ [不要做的事]
- ✅ [要做的事]
"""

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "你是一位专业的网络小说策划编辑，擅长创作西幻种田类小说的章纲。输出要简洁、实用，便于后续写作。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=2000
    )
    
    return response.choices[0].message.content

# 写作章节
def write_chapter(volume: int, chapter: int, chapter_outline: str, prev_chapter_content: str = "", context: str = ""):
    """使用DeepSeek写作章节"""
    
    prompt = f"""你是一位专业的网络小说写手，擅长创作西幻种田类小说。请根据以下章纲写作完整的章节内容。

## 创作宪法（核心原则）
{CONSTITUTION[:1500]}

## 章纲
{chapter_outline}

## 故事状态与记忆（核心参考）
{context}

## 前一章结尾（续写参考）
{prev_chapter_content[-2000:] if prev_chapter_content else "（第1章，无前文）"}

## 写作要求
1. 字数：5000字以上
2. 风格：流畅自然的网文风格，对话和描写穿插
3. POV：主角第三人称视角
4. 节奏：张弛有度，不要太赶
5. 细节：适当的环境和心理描写
6. 不要：章节标题、作者备注、元叙述

请直接输出章节正文内容，开头直接进入场景，不要任何前言。
"""

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "你是一位顶级网络小说写手，擅长西幻种田流。你的文风流畅自然，擅长人物塑造和节奏把控。每章至少5000字。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.85,
        max_tokens=8000
    )
    
    return response.choices[0].message.content

# 质量检查
def check_quality(content: str, chapter: int):
    """基本质量检查"""
    issues = []
    
    # 字数检查
    word_count = len(content)
    if word_count < 4500:
        issues.append(f"字数不足：{word_count} < 4500")
    
    # 禁忌词检查
    forbidden = ["手机", "电脑", "汽车", "网络", "电力", "互联网"]
    for word in forbidden:
        if word in content:
            issues.append(f"可能的时代错误：包含'{word}'")
    
    # 系统检查（前3章不应出现）
    if chapter <= 3 and "系统" in content and "星辰" in content:
        issues.append("第1-3章不应出现系统")
    
    return {
        "word_count": word_count,
        "issues": issues,
        "passed": len(issues) == 0
    }

# 保存章节
def save_chapter(volume: int, chapter: int, title: str, content: str):
    """保存章节到txt文件"""
    chapter_dir = PROJECT_PATH / "chapters" / f"v{volume:02d}"
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

# 保存章纲
def save_chapter_outline(volume: int, chapter: int, outline_content: str):
    """保存章纲"""
    outline_dir = PROJECT_PATH / "outline" / "L3-chapters"
    outline_dir.mkdir(parents=True, exist_ok=True)
    
    filepath = outline_dir / f"v{volume:02d}-c{chapter:03d}.md"
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(outline_content)
    
    return filepath

# 加载章纲
def load_chapter_outline(volume: int, chapter: int):
    """加载已有章纲"""
    filepath = PROJECT_PATH / "outline" / "L3-chapters" / f"v{volume:02d}-c{chapter:03d}.md"
    if filepath.exists():
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    return None

# 加载前一章内容
def load_prev_chapter(volume: int, chapter: int):
    """加载前一章内容"""
    if chapter <= 1:
        return ""
    
    chapter_dir = PROJECT_PATH / "chapters" / f"v{volume:02d}"
    # 查找前一章文件
    for f in chapter_dir.glob(f"第{chapter-1}章_*.txt"):
        with open(f, 'r', encoding='utf-8') as file:
            return file.read()
    return ""

# 所有章节规划（可扩展）
ALL_CHAPTERS = {
    # 第一篇：穿越觉醒（1-30）
    1: ("异世界醒来", "穿越附身，懵懂觉醒，初见世界"),
    2: ("破落的诺斯家", "认识塞巴斯，了解身份现状"),
    3: ("边缘人的处境", "庶子地位，家族边缘，困境展示"),
    4: ("星辰系统", "系统觉醒，了解功能，第一次任务"),
    5: ("第一次抽奖", "完成任务，首次抽奖，获得基础功法"),
    6: ("源素之力", "学习功法，感知源素，了解境界"),
    7: ("诺斯家的历史", "家族往事，曾经辉煌，如今衰落"),
    8: ("洛兰王国", "王国形势，贵族政治，世界格局"),
    9: ("庶子的选择", "分析处境，三条路（留/走/发展）"),
    10: ("决定：前往诺斯领", "做出决定，准备离开，获得支持"),
    11: ("离开诺斯本家", "启程，塞巴斯同行，路上交谈"),
    12: ("边境道路", "旅途见闻，魔兽痕迹，世界展示"),
    13: ("流民之困", "遇到流民群体，格雷登场"),
    14: ("一个交易", "与格雷谈判，达成协议"),
    15: ("收拢人手", "流民加入，队伍扩大"),
    16: ("魔兽！", "遭遇魔兽，战斗，格雷展示实力"),
    17: ("第一滴血", "战斗结束，有伤亡，现实教训"),
    18: ("破败的城堡", "抵达诺斯堡，看到荒凉景象"),
    19: ("河谷村", "视察村庄，村民态度冷淡"),
    20: ("领地现状", "全面了解，问题清单，初步规划"),
    21: ("领主的第一道命令", "安置流民，分配任务，建立秩序"),
    22: ("人心", "与村民建立信任的努力"),
    23: ("修缮工程", "开始修缮城堡，展示规划能力"),
    24: ("小规模冲突", "处理刺头/刁民，初步立威"),
    25: ("系统任务：站稳脚跟", "完成成长任务，准备下一次抽奖"),
    26: ("源力的共鸣", "修炼有进展，感知加强"),
    27: ("边境的消息", "外部威胁信息，盗匪/魔兽活动"),
    28: ("巡逻队", "建立巡逻队，格雷负责"),
    29: ("突破契机", "战斗/危机触发突破"),
    30: ("感知者", "突破感知者境界，第一篇结束"),
    
    # 第二篇：领地初建（31-60）
    31: ("新的开始", "突破后的变化，制定发展计划"),
    32: ("春耕准备", "规划农业发展，播种高产种子"),
    33: ("开垦荒田", "组织流民开垦，扩大耕地面积"),
    34: ("水利工程", "挖掘灌溉渠道，改善水源问题"),
    35: ("第一批收获", "高产小麦成熟，村民震惊"),
    36: ("名声初起", "周边村庄听闻诺斯领的变化"),
    37: ("新的流民", "更多流民慕名而来"),
    38: ("人口翻倍", "领地人口增加，管理挑战"),
    39: ("建立规矩", "制定领地法规，规范管理"),
    40: ("锻造坊", "建立锻造工坊，生产农具武器"),
    41: ("格雷的建议", "格雷提议训练民兵"),
    42: ("民兵训练", "开始系统性训练民兵"),
    43: ("边境摩擦", "与邻近势力发生小冲突"),
    44: ("外交试探", "邻居贵族派人探查"),
    45: ("抽奖收获", "获得重要技能或物品"),
    46: ("修炼突破在即", "感觉凝聚者境界不远"),
    47: ("暗流涌动", "有人开始注意诺斯领的发展"),
    48: ("第一笔生意", "开始与外界进行贸易"),
    49: ("商人来访", "商人发现诺斯领的潜力"),
    50: ("商路初通", "建立初步商业联系"),
    51: ("冬季来临", "准备过冬，储备物资"),
    52: ("严冬挑战", "应对冬季的各种困难"),
    53: ("冬日修炼", "利用冬季修炼提升"),
    54: ("系统升级", "完成里程碑任务，系统解锁新功能"),
    55: ("情报网络", "开始建立简单的情报系统"),
    56: ("隐患显现", "发现领地内有人暗中作梗"),
    57: ("清除隐患", "处理内部问题"),
    58: ("春暖花开", "熬过冬天，迎来新的春天"),
    59: ("凝聚之路", "修炼达到临界点"),
    60: ("凝聚者", "突破凝聚者境界，第二篇结束"),
    
    # 第三篇：崛起之路（61-70）
    61: ("第一艘船", "春耕顺利，为了贸易，艾伦决定建立河运码头，探索水路"),
    62: ("商人的回归", "马库斯带回关于‘渡鸦’的情报，警告艾伦"),
    63: ("林中阴影", "巡逻队在森林遭遇‘渡鸦’精锐斥候，发生冲突"),
    64: ("修炼与应用", "艾伦探索凝聚者能力，尝试附魔工具"),
    65: ("人口爆发", "北方稳定引来流民潮，推行分区规划"),
    66: ("河中巨兽", "水路被魔兽阻断，艾伦带队讨伐"),
    67: ("贸易协定", "打通至白河城的商路，签订第一份正式协议"),
    68: ("第二座工坊", "建立木工坊或陶艺坊，冲击领地升级条件"),
    69: ("暗流", "邻近男爵受‘渡鸦’挑拨，施压诺斯领"),
    70: ("备战", "扩充卫队，准备应对可能的冲突"),
}

def get_chapter_info(chapter: int):
    """获取章节信息，如果没有预设则自动生成"""
    if chapter in ALL_CHAPTERS:
        return ALL_CHAPTERS[chapter]
    else:
        # 自动生成章节信息
        part = (chapter - 1) // 30 + 1
        chapter_in_part = (chapter - 1) % 30 + 1
        return (f"第{part}篇第{chapter_in_part}节", f"第{chapter}章内容待自动生成")

def run_auto_write(start_chapter: int = 2, end_chapter: int = 30):
    """运行自动写作"""
    
    print("=" * 60)
    print(f"🚀 开始自动写作：第{start_chapter}章 到 第{end_chapter}章")
    print("=" * 60)
    
    volume = 1
    total_words = 0
    stats = {"success": 0, "failed": 0, "issues": []}
    
    # 初始化状态管理器
    state_manager = StoryStateManager()
    
    for chapter in range(start_chapter, end_chapter + 1):
        print(f"\n📝 处理第{chapter}章...")
        
        # 获取章节信息
        chapter_info = get_chapter_info(chapter)
        title = chapter_info[0]
        main_content = chapter_info[1]
        
        try:
            # 1. 检查/生成章纲
            outline = load_chapter_outline(volume, chapter)
            if not outline:
                print(f"  📋 生成章纲...")
                outline = generate_chapter_outline(volume, chapter, title, main_content)
                save_chapter_outline(volume, chapter, outline)
                time.sleep(1)  # 避免API限流
            
            # 2. 加载前一章
            prev_content = load_prev_chapter(volume, chapter)
            
            # 3. 生成上下文与写作
            print(f"  🧠 生成记忆上下文...")
            # 提取本章关键词作为主题
            topics = [title, "领地建设", "外部威胁"]
            context = state_manager.generate_context_for_writing(chapter, topics=topics)
            
            print(f"  ✍️ 写作中...")
            content = write_chapter(volume, chapter, outline, prev_content, context)
            time.sleep(2)  # 避免API限流
            
            # 4. 质量检查
            quality = check_quality(content, chapter)
            print(f"  📊 字数：{quality['word_count']}")
            
            if not quality["passed"]:
                for issue in quality["issues"]:
                    print(f"  ⚠️ {issue}")
                    stats["issues"].append(f"第{chapter}章：{issue}")
            
            # 5. 保存
            save_chapter(volume, chapter, title, content)
            
            total_words += quality["word_count"]
            stats["success"] += 1
            
            # 每5章报告进度
            if chapter % 5 == 0:
                print(f"\n{'=' * 40}")
                print(f"📊 进度报告：已完成 {chapter}/{end_chapter} 章")
                print(f"   总字数：{total_words:,}")
                print(f"{'=' * 40}\n")
            
        except Exception as e:
            print(f"  ❌ 错误：{e}")
            stats["failed"] += 1
            stats["issues"].append(f"第{chapter}章：{str(e)}")
    
    # 最终报告
    print("\n" + "=" * 60)
    print("📊 自动写作完成报告")
    print("=" * 60)
    print(f"  成功：{stats['success']} 章")
    print(f"  失败：{stats['failed']} 章")
    print(f"  总字数：{total_words:,}")
    
    if stats["issues"]:
        print("\n⚠️ 问题列表：")
        for issue in stats["issues"]:
            print(f"  - {issue}")
    
    return stats

if __name__ == "__main__":
    # 默认从第2章开始（第1章已手写）
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 5  # 默认先写5章测试
    
    run_auto_write(start, end)
