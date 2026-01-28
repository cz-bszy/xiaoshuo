"""
使用DeepSeek Reasoner整理和优化章节内容
功能：
1. 检查并修复时代错误词汇
2. 检查剧情一致性
3. 优化文笔质量
4. 使用Reasoner为后续章节生成更好的章纲
"""

import os
import sys
import json
import time
import re
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

# 现代词汇列表（需要替换）
MODERN_WORDS = {
    "电脑": "水晶球/账簿",
    "网络": "消息网/情报网",
    "手机": "传讯石",
    "汽车": "马车",
    "互联网": "情报网络",
    "电力": "源素动力",
    "电视": "水镜",
}

def load_chapter(chapter_num: int) -> str:
    """加载章节内容"""
    chapter_dir = PROJECT_PATH / "chapters" / "v01"
    for f in chapter_dir.glob(f"第{chapter_num}章_*.txt"):
        with open(f, 'r', encoding='utf-8') as file:
            return file.read()
    return ""

def save_chapter(chapter_num: int, title: str, content: str):
    """保存修正后的章节"""
    chapter_dir = PROJECT_PATH / "chapters" / "v01"
    # 清理标题
    safe_title = title.replace(":", "：").replace("/", "_").replace("\\", "_")
    safe_title = safe_title.replace("?", "？").replace("*", "_").replace('"', "'")
    
    filename = f"第{chapter_num}章_{safe_title}.txt"
    filepath = chapter_dir / filename
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return filepath

def fix_modern_words(content: str) -> tuple:
    """修复现代词汇（简单替换）"""
    fixed_count = 0
    fixed_words = []
    
    for modern, replacement in MODERN_WORDS.items():
        if modern in content:
            count = content.count(modern)
            # 在回忆前世的语境中保留
            if "前世" in content or "记忆" in content:
                # 跳过直接替换，需要更智能的处理
                pass
            else:
                content = content.replace(modern, replacement)
                fixed_count += count
                fixed_words.append(f"{modern}->{replacement}")
    
    return content, fixed_count, fixed_words

def analyze_chapter_with_reasoner(chapter_num: int, content: str) -> dict:
    """使用DeepSeek Reasoner分析章节问题"""
    
    prompt = f"""请仔细分析以下第{chapter_num}章的内容，找出需要修改的问题：

1. **时代错误**：找出不符合中世纪西幻设定的现代词汇或概念（电脑、手机、网络等）
   - 注意：如果是主角回忆前世，可以保留这些词
   
2. **逻辑漏洞**：角色行为、剧情发展是否合理

3. **设定冲突**：是否与已有设定冲突（境界体系、世界规则）

4. **文笔问题**：表达不清、重复啰嗦的地方

## 章节内容：
{content[:8000]}

请用以下JSON格式输出分析结果：
```json
{{
  "time_period_errors": [
    {{"text": "问题原文", "suggestion": "修改建议", "is_flashback": true/false}}
  ],
  "logic_issues": [
    {{"description": "问题描述", "suggestion": "修改建议"}}
  ],
  "setting_conflicts": [
    {{"description": "问题描述", "rule_violated": "违反的规则"}}
  ],
  "quality_issues": [
    {{"text": "问题原文", "suggestion": "修改建议"}}
  ],
  "overall_score": 8.5,
  "summary": "章节整体评价"
}}
```
"""

    try:
        response = client.chat.completions.create(
            model="deepseek-reasoner",
            messages=[
                {"role": "system", "content": "你是一位专业的网络小说编辑，擅长发现文本问题并提供具体的修改建议。请仔细分析并以JSON格式输出结果。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=4000
        )
        
        result_text = response.choices[0].message.content
        
        # 提取JSON
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', result_text)
        if json_match:
            return json.loads(json_match.group(1))
        else:
            # 尝试直接解析
            return json.loads(result_text)
            
    except Exception as e:
        print(f"  ⚠️ 分析出错: {e}")
        return {"error": str(e)}

def generate_chapter_outline_with_reasoner(chapter_num: int, prev_summary: str) -> str:
    """使用Reasoner生成更高质量的章纲"""
    
    # 加载世界观设定
    worldbook_summary = """
## 核心设定
- 主角：艾伦·诺斯，穿越者，诺斯领领主
- 金手指：星辰系统（每日抽奖）
- 境界体系：感知者→凝聚者→外显者→领域者→大师→圣阶
- 职业：战士、游侠、斗士、守卫、元素师、生命师

## 主要配角
- 塞巴斯：老管家，忠诚
- 格雷：流民首领，武力担当

## 当前状态（第50章后）
- 领地已初步稳定
- 人口增加，商路初通
- 主角境界：感知者（即将凝聚）
"""

    prompt = f"""你是一位专业的网络小说策划。请为第{chapter_num}章生成详细的章纲。

## 世界观
{worldbook_summary}

## 前情提要
{prev_summary}

## 要求
1. 章节长度：5000-8000字
2. 场景数量：3-4个场景
3. 需要有：冲突、发展、悬念
4. 保持种田流的节奏

请输出完整的章纲，包括：
- 章节标题
- 本章目的（3点）
- 场景安排（3-4个场景，各约1000-2000字）
- 关键对话要点
- 本章结尾悬念
"""

    try:
        response = client.chat.completions.create(
            model="deepseek-reasoner",
            messages=[
                {"role": "system", "content": "你是一位资深网络小说策划编辑，擅长设计引人入胜的章节结构。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=3000
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        print(f"  ⚠️ 生成章纲出错: {e}")
        return ""

def run_analysis(start_chapter: int = 1, end_chapter: int = 50):
    """运行批量分析"""
    
    print("=" * 60)
    print(f"🔍 开始分析：第{start_chapter}章 到 第{end_chapter}章")
    print("=" * 60)
    
    all_issues = []
    
    for chapter in range(start_chapter, end_chapter + 1):
        print(f"\n📖 分析第{chapter}章...")
        
        content = load_chapter(chapter)
        if not content:
            print(f"  ⚠️ 未找到章节文件")
            continue
        
        # 1. 简单词汇修复
        content, fix_count, fixed_words = fix_modern_words(content)
        if fix_count > 0:
            print(f"  🔧 修复了 {fix_count} 处现代词汇: {', '.join(fixed_words)}")
        
        # 2. 使用Reasoner深度分析（每5章做一次）
        if chapter % 5 == 0:
            print(f"  🧠 使用Reasoner深度分析...")
            analysis = analyze_chapter_with_reasoner(chapter, content)
            
            if "error" not in analysis:
                score = analysis.get("overall_score", "N/A")
                print(f"  📊 评分: {score}/10")
                
                if analysis.get("time_period_errors"):
                    print(f"  ⚠️ 时代错误: {len(analysis['time_period_errors'])}处")
                if analysis.get("logic_issues"):
                    print(f"  ⚠️ 逻辑问题: {len(analysis['logic_issues'])}处")
                    
                all_issues.append({
                    "chapter": chapter,
                    "analysis": analysis
                })
            
            time.sleep(2)  # 避免API限流
        
        # 每10章报告进度
        if chapter % 10 == 0:
            print(f"\n{'=' * 40}")
            print(f"📊 进度: {chapter}/{end_chapter}")
            print(f"{'=' * 40}\n")
    
    # 保存分析报告
    report_path = PROJECT_PATH / "analysis_report.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(all_issues, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 分析完成，报告已保存至: {report_path}")
    return all_issues

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "analyze"
    
    if mode == "analyze":
        start = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        end = int(sys.argv[3]) if len(sys.argv) > 3 else 50
        run_analysis(start, end)
    elif mode == "outline":
        chapter = int(sys.argv[2]) if len(sys.argv) > 2 else 51
        outline = generate_chapter_outline_with_reasoner(chapter, "前50章完成领地初建")
        print(outline)
