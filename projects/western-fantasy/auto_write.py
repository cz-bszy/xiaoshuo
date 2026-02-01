"""
自动化写作主脚本
新增硬状态闭环：Plan → Validate → Write → Extract → Validate → Commit → Memory
"""

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from openai import OpenAI

from story_state_manager import StoryStateManager
from story_memory_adapter import StoryMemoryAdapter
from consistency_checker import run_consistency_check


PROJECT_PATH = Path(__file__).resolve().parent
REPO_ROOT = PROJECT_PATH.parents[1]


def load_api_key() -> str:
    api_path = REPO_ROOT / "deepseek_api.txt"
    if api_path.exists():
        return api_path.read_text(encoding="utf-8").strip()
    config_path = PROJECT_PATH / "config.yaml"
    if config_path.exists():
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        return data.get("models", {}).get("writing", {}).get("api_key", "")
    return ""


with open(PROJECT_PATH / "config.yaml", "r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

MODEL_CONFIG = CONFIG.get("models", {}).get("writing", {})
MODEL_NAME = MODEL_CONFIG.get("model", "deepseek-chat")
API_BASE = MODEL_CONFIG.get("api_base", "https://api.deepseek.com")
TEMPERATURE = MODEL_CONFIG.get("temperature", 0.85)
MAX_TOKENS = MODEL_CONFIG.get("max_tokens", 6000)

API_KEY = load_api_key()

client = OpenAI(api_key=API_KEY, base_url=API_BASE)


# 加载世界书

def load_worldbook() -> Dict[str, Any]:
    worldbook = {}
    for name in ["characters", "locations", "rules", "items"]:
        path = PROJECT_PATH / "worldbook" / f"{name}.json"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                worldbook[name] = json.load(f)
    return worldbook


WORLDBOOK = load_worldbook()


# 加载创作宪法和规格

def load_constitution() -> str:
    path = PROJECT_PATH / "constitution.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def load_specification() -> str:
    path = PROJECT_PATH / "specification.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


CONSTITUTION = load_constitution()
SPECIFICATION = load_specification()


# 加载卷纲和篇纲

def load_volume_outline(volume: int) -> str:
    path = PROJECT_PATH / "outline" / "L1-volumes" / f"v{volume:02d}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def load_part_outline(volume: int, part: int) -> str:
    path = PROJECT_PATH / "outline" / "L2-parts" / f"v{volume:02d}-p{part:02d}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


# 生成章纲

def generate_chapter_outline(volume: int, chapter: int, title: str, main_content: str) -> str:
    volume_outline = load_volume_outline(volume)
    part = (chapter - 1) // 30 + 1
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
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": "你是专业的网络小说策划编辑，擅长创作西幻种田类小说的章纲。输出要简洁、实用，便于后续写作。",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=2000,
    )

    return response.choices[0].message.content


# 工具函数

def _extract_json(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        pass

    json_block = re.search(r"```json\s*([\s\S]*?)\s*```", text)
    if json_block:
        return json.loads(json_block.group(1))

    obj_block = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
    if obj_block:
        return json.loads(obj_block.group(1))

    raise ValueError("无法解析JSON输出")


def _has_error(issues: List[Dict[str, Any]]) -> bool:
    return any(issue.get("severity") == "error" for issue in issues)


# 计划生成 / 修复

def llm_generate_plan(
    chapter_num: int,
    title: str,
    outline: str,
    snapshot: Dict[str, Any],
    invariants_text: str,
    memory_context: str,
) -> Dict[str, Any]:
    hard_state = StoryStateManager.format_snapshot_for_prompt(snapshot)

    prompt = f"""你是小说章节规划器。请根据章纲与硬状态，输出严格JSON计划。

## 硬状态快照（必须遵守）
{hard_state}

## 硬规则（不得违反）
{invariants_text}

## 章纲
{outline}

## 记忆背景（参考）
{memory_context}

## 输出要求
1. 只输出严格JSON
2. 必须包含字段：chapter_num, title, actions, state_changes
3. 若要访问仓库，必须先在 state_changes 中声明解锁原因

示例结构：
{{
  "chapter_num": {chapter_num},
  "title": "{title}",
  "actions": [
    {{"type": "scene", "description": "..."}},
    {{"type": "warehouse_withdraw", "actor": "艾伦", "notes": "若未解锁则不得成功"}}
  ],
  "state_changes": [
    {{"path": "system.warehouse.accessible", "from": false, "to": true, "cause_event": "完成任务获得权限"}}
  ]
}}
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": "你是严谨的小说规划师，擅长输出结构化JSON计划。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=2000,
    )
    return _extract_json(response.choices[0].message.content)


def llm_fix_plan(plan: Dict[str, Any], issues: List[Dict[str, Any]], snapshot: Dict[str, Any]) -> Dict[str, Any]:
    hard_state = StoryStateManager.format_snapshot_for_prompt(snapshot)
    prompt = f"""以下计划存在硬状态冲突，请修复并输出严格JSON（只输出JSON）。

## 硬状态快照
{hard_state}

## 原计划
{json.dumps(plan, ensure_ascii=False, indent=2)}

## 问题
{json.dumps(issues, ensure_ascii=False, indent=2)}

修复要求：
- 若仓库不可用，必须改写为失败或补解锁桥段
- 保持其余内容不变
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": "你是严谨的小说规划师，擅长修复JSON计划。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=2000,
    )
    return _extract_json(response.choices[0].message.content)


# 写作 / 修复

def llm_write_chapter(
    chapter_num: int,
    plan: Dict[str, Any],
    outline: str,
    snapshot: Dict[str, Any],
    invariants_text: str,
    memory_context: str,
    prev_chapter_content: str,
) -> str:
    hard_state = StoryStateManager.format_snapshot_for_prompt(snapshot)

    prompt = f"""你是专业的网络小说写手，擅长创作西幻种田类小说。请根据计划写作完整章节内容。

## 创作宪法（核心原则）
{CONSTITUTION[:1500]}

## 硬状态快照（必须遵守）
{hard_state}

## 硬规则（不得违反）
{invariants_text}

## 计划（JSON）
{json.dumps(plan, ensure_ascii=False, indent=2)}

## 章纲（补充参考）
{outline}

## 记忆背景（参考）
{memory_context}

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
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": "你是顶级网络小说写手，文风流畅自然，擅长人物塑造和节奏把控。",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
    )

    return response.choices[0].message.content


def llm_repair_chapter(
    chapter_text: str,
    plan: Dict[str, Any],
    snapshot: Dict[str, Any],
    issues: List[Dict[str, Any]],
    repairs: List[Dict[str, Any]],
) -> str:
    hard_state = StoryStateManager.format_snapshot_for_prompt(snapshot)
    invariants_text = StoryStateManager.format_invariants_for_prompt(snapshot.get("invariants", []))

    prompt = f"""以下章节存在硬状态矛盾，请最小改写修复。要求：
- 只改动相关段落，不重写整章
- 两种修复路线任选其一：
  A) 改写为访问失败/权限不足
  B) 在首次成功访问前插入解锁桥段，并保证因果闭合

## 硬状态快照
{hard_state}

## 硬规则
{invariants_text}

## 问题
{json.dumps(issues, ensure_ascii=False, indent=2)}

## 修复指令包
{json.dumps(repairs, ensure_ascii=False, indent=2)}

## 计划
{json.dumps(plan, ensure_ascii=False, indent=2)}

## 原文
{chapter_text}

请输出修复后的章节正文：
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": "你是严谨的小说修订编辑。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.4,
        max_tokens=MAX_TOKENS,
    )

    return response.choices[0].message.content


# 质量检查

def check_quality(content: str, chapter: int) -> Dict[str, Any]:
    issues = []
    word_count = len(content)
    if word_count < 4500:
        issues.append(f"字数不足：{word_count} < 4500")

    forbidden = ["手机", "电脑", "汽车", "网络", "电力", "互联网"]
    for word in forbidden:
        if word in content:
            issues.append(f"可能的时代错误：包含'{word}'")

    if chapter <= 3 and "系统" in content and "星辰" in content:
        issues.append("第1-3章不应出现系统")

    return {"word_count": word_count, "issues": issues, "passed": len(issues) == 0}


# 保存章节

def save_chapter(volume: int, chapter: int, title: str, content: str) -> Path:
    chapter_dir = PROJECT_PATH / "chapters" / f"v{volume:02d}"
    chapter_dir.mkdir(parents=True, exist_ok=True)

    safe_title = title.replace(":", "：").replace("/", "_").replace("\\", "_")
    safe_title = safe_title.replace("?", "？").replace("*", "_").replace('"', "'")

    filename = f"第{chapter}章_{safe_title}.txt"
    filepath = chapter_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"第{chapter}章 {title}\n\n")
        f.write(content)

    return filepath


# 保存章纲

def save_chapter_outline(volume: int, chapter: int, outline_content: str) -> Path:
    outline_dir = PROJECT_PATH / "outline" / "L3-chapters"
    outline_dir.mkdir(parents=True, exist_ok=True)

    filepath = outline_dir / f"v{volume:02d}-c{chapter:03d}.md"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(outline_content)

    return filepath


# 加载章纲

def load_chapter_outline(volume: int, chapter: int) -> Optional[str]:
    filepath = PROJECT_PATH / "outline" / "L3-chapters" / f"v{volume:02d}-c{chapter:03d}.md"
    if filepath.exists():
        return filepath.read_text(encoding="utf-8")
    return None


# 加载前一章内容

def load_prev_chapter(volume: int, chapter: int) -> str:
    if chapter <= 1:
        return ""

    chapter_dir = PROJECT_PATH / "chapters" / f"v{volume:02d}"
    for f in chapter_dir.glob(f"第{chapter-1}章_*.txt"):
        return f.read_text(encoding="utf-8")
    return ""


# 章节规划（可扩展）
ALL_CHAPTERS: Dict[int, Tuple[str, str]] = {
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


def get_chapter_info(chapter: int) -> Tuple[str, str]:
    if chapter in ALL_CHAPTERS:
        return ALL_CHAPTERS[chapter]
    part = (chapter - 1) // 30 + 1
    chapter_in_part = (chapter - 1) % 30 + 1
    return (f"第{part}篇第{chapter_in_part}节", f"第{chapter}章内容待自动生成")


# 生成与提交流程

def save_artifacts(chapter: int, plan: Dict[str, Any], issues: List[Dict[str, Any]]):
    report_dir = PROJECT_PATH / "state" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    plan_path = report_dir / f"plan_c{chapter:03d}.json"
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    issues_path = report_dir / f"issues_c{chapter:03d}.json"
    with open(issues_path, "w", encoding="utf-8") as f:
        json.dump(issues, f, ensure_ascii=False, indent=2)


def save_fail_report(
    chapter: int,
    issues: List[Dict[str, Any]],
    plan: Optional[Dict[str, Any]] = None,
    draft: Optional[str] = None,
):
    report_dir = PROJECT_PATH / "state" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "chapter": chapter,
        "issues": issues,
        "plan": plan or {},
        "draft_excerpt": draft[:2000] if draft else "",
    }
    fail_path = report_dir / f"fail_c{chapter:03d}.json"
    with open(fail_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)



def generate_draft_payload(
    chapter: int,
    volume: int,
    state_manager: StoryStateManager,
    memory_adapter: Optional[StoryMemoryAdapter],
) -> Dict[str, Any]:
    title, main_content = get_chapter_info(chapter)

    outline = load_chapter_outline(volume, chapter)
    if not outline:
        outline = generate_chapter_outline(volume, chapter, title, main_content)
        save_chapter_outline(volume, chapter, outline)
        time.sleep(1)

    topics = [title, "领地建设", "外部威胁"]
    snapshot = state_manager.get_snapshot(chapter, topic_keywords=topics)
    invariants_text = StoryStateManager.format_invariants_for_prompt(snapshot.get("invariants", []))

    if memory_adapter is None:
        memory_context = ""
    else:
        memory_context = memory_adapter.get_writing_context(chapter, topics=topics)

    plan = llm_generate_plan(chapter, title, outline, snapshot, invariants_text, memory_context)
    issues = state_manager.validate_plan(plan, snapshot)
    if _has_error(issues):
        plan = llm_fix_plan(plan, issues, snapshot)
        issues = state_manager.validate_plan(plan, snapshot)
    save_artifacts(chapter, plan, issues)

    prev_content = load_prev_chapter(volume, chapter)
    draft = llm_write_chapter(
        chapter,
        plan,
        outline,
        snapshot,
        invariants_text,
        memory_context,
        prev_content,
    )
    time.sleep(1)

    return {
        "chapter": chapter,
        "title": title,
        "outline": outline,
        "plan": plan,
        "plan_issues": issues,
        "draft": draft,
        "topics": topics,
    }


def commit_chapter_payload(
    payload: Dict[str, Any],
    volume: int,
    state_manager: StoryStateManager,
    memory_adapter: StoryMemoryAdapter,
) -> Dict[str, Any]:
    chapter = payload["chapter"]
    title = payload["title"]
    plan = payload["plan"]
    draft = payload["draft"]
    topics = payload["topics"]

    snapshot = state_manager.get_snapshot(chapter, topic_keywords=topics)

    plan_issues = state_manager.validate_plan(plan, snapshot)
    if _has_error(plan_issues):
        plan = llm_fix_plan(plan, plan_issues, snapshot)
        plan_issues = state_manager.validate_plan(plan, snapshot)
        if _has_error(plan_issues):
            save_fail_report(chapter, plan_issues, plan=plan)
            return {"chapter": chapter, "status": "failed", "issues": plan_issues}

    post_issues = state_manager.validate_chapter(draft, snapshot)
    if _has_error(post_issues):
        checker_output = run_consistency_check(snapshot, plan, draft)
        repairs = checker_output.get("repairs", [])
        draft = llm_repair_chapter(draft, plan, snapshot, post_issues, repairs)
        post_issues = state_manager.validate_chapter(draft, snapshot)
        if _has_error(post_issues):
            save_fail_report(chapter, post_issues, plan=plan, draft=draft)
            return {"chapter": chapter, "status": "failed", "issues": post_issues}

    all_issues = plan_issues + post_issues

    updates = state_manager.extract_state_updates(draft, chapter)
    state_manager.commit(chapter, updates, all_issues)
    save_artifacts(chapter, plan, all_issues)

    quality = check_quality(draft, chapter)
    save_chapter(volume, chapter, title, draft)
    if memory_adapter is not None:
        memory_adapter.add_chapter(chapter_num=chapter, content=draft, title=title)

    return {
        "chapter": chapter,
        "status": "success",
        "issues": all_issues,
        "quality": quality,
    }


# 主流程

def run_auto_write(start_chapter: int = 2, end_chapter: int = 30):
    print("=" * 60)
    print(f"🚀 开始自动写作：第{start_chapter}章 到 第{end_chapter}章")
    print("=" * 60)

    pipeline_cfg = CONFIG.get("pipeline", {}) or {}
    if pipeline_cfg.get("enabled", False):
        from chapter_pipeline import ChapterPipeline

        pipeline = ChapterPipeline(PROJECT_PATH)
        stats = {"success": 0, "failed": 0, "issues": []}
        total_words = 0

        for chapter in range(start_chapter, end_chapter + 1):
            try:
                ok = pipeline.run(chapter)
                if ok:
                    stats["success"] += 1
                    final_path = (
                        PROJECT_PATH
                        / "pipeline"
                        / "chapters"
                        / f"c{chapter:03d}"
                        / "final.txt"
                    )
                    if final_path.exists():
                        total_words += len(final_path.read_text(encoding="utf-8").strip())
                else:
                    stats["failed"] += 1
                    stats["issues"].append(f"第{chapter}章：评审未通过")
            except Exception as e:
                stats["failed"] += 1
                stats["issues"].append(f"第{chapter}章：{str(e)}")

            if chapter % 5 == 0:
                print(f"\n{'=' * 40}")
                print(f"📊 进度报告：已完成 {chapter}/{end_chapter} 章")
                print(f"   总字数（估算字符）：{total_words:,}")
                print(f"{'=' * 40}\n")

        print("\n" + "=" * 60)
        print("📊 自动写作完成报告")
        print("=" * 60)
        print(f"  成功：{stats['success']} 章")
        print(f"  失败：{stats['failed']} 章")
        print(f"  总字数（估算字符）：{total_words:,}")

        if stats["issues"]:
            print("\n⚠️ 问题列表：")
            for issue in stats["issues"]:
                print(f"  - {issue}")

        return stats

    volume = 1
    total_words = 0
    stats = {"success": 0, "failed": 0, "issues": []}

    state_manager = StoryStateManager(project_path=PROJECT_PATH)
    writing_config = CONFIG.get("writing", {})
    use_memory = writing_config.get("use_memory", True)
    memory_adapter = StoryMemoryAdapter(clear_db=False) if use_memory else None

    strict_state = writing_config.get("strict_state", True)
    parallel_mode = writing_config.get("parallel_mode", "sequential_commit")
    max_workers = int(writing_config.get("max_workers", 1))

    if strict_state and parallel_mode == "full_parallel":
        print("⚠️ strict_state=true，已降级为 sequential_commit")
        parallel_mode = "sequential_commit"

    chapters = list(range(start_chapter, end_chapter + 1))
    payloads: Dict[int, Dict[str, Any]] = {}

    if parallel_mode == "sequential_commit" and max_workers > 1:
        print(f"⚡ 并行生成草稿（max_workers={max_workers}），串行提交状态")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    generate_draft_payload,
                    chapter,
                    volume,
                    state_manager,
                    None,
                ): chapter
                for chapter in chapters
            }
            for future in as_completed(futures):
                chapter = futures[future]
                try:
                    payloads[chapter] = future.result()
                except Exception as e:
                    stats["failed"] += 1
                    stats["issues"].append(f"第{chapter}章：{str(e)}")
    else:
        for chapter in chapters:
            try:
                payloads[chapter] = generate_draft_payload(
                    chapter, volume, state_manager, memory_adapter
                )
            except Exception as e:
                stats["failed"] += 1
                stats["issues"].append(f"第{chapter}章：{str(e)}")

    for chapter in chapters:
        if chapter not in payloads:
            continue
        try:
            result = commit_chapter_payload(payloads[chapter], volume, state_manager, memory_adapter)
            if result["status"] == "success":
                stats["success"] += 1
                quality = result.get("quality", {})
                total_words += quality.get("word_count", 0)
            else:
                stats["failed"] += 1
                stats["issues"].append(f"第{chapter}章：状态提交失败")
                stats["issues"].extend([f"第{chapter}章：{i['message']}" for i in result.get("issues", [])])
        except Exception as e:
            stats["failed"] += 1
            stats["issues"].append(f"第{chapter}章：{str(e)}")

        if chapter % 5 == 0:
            print(f"\n{'=' * 40}")
            print(f"📊 进度报告：已完成 {chapter}/{end_chapter} 章")
            print(f"   总字数：{total_words:,}")
            print(f"{'=' * 40}\n")

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
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    run_auto_write(start, end)
