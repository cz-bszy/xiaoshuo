"""
Prompt 模板集合
用于生成写作和分析的提示词
"""

from typing import Dict, Any, Optional


class PromptTemplates:
    """提示词模板集合"""
    
    # ============== 写作类提示词 ==============
    
    @staticmethod
    def chapter_writing_system(genre: str = "western-fantasy-farming") -> str:
        """章节写作系统提示词"""
        
        base = """你是一位专业的中文网络小说作家，拥有丰富的创作经验。

## 你的优势
- 文笔流畅，节奏感强
- 善于描写细节，营造氛围
- 对话生动，人物鲜活
- 情节设计巧妙，引人入胜

## 写作原则
- 展示，不要讲述（Show, don't tell）
- 每个场景都有目的
- 保持节奏，避免拖沓
- 留有余韵，设置悬念"""

        genre_specific = {
            "western-fantasy-farming": """

## 类型特化（西方幻想种田流）

### 世界观
- 西方中世纪风格的奇幻世界
- 低魔设定：魔法稀少，效果有限
- 封建领地制度

### 种田流核心
- 建设过程要有成就感
- 日常也要有小目标和发现
- 展现规划执行的乐趣
- 渐进式发展，不要一步登天

### 节奏把控
- 日常种田占主体（60-70%）
- 适当穿插小事件和冲突
- 大事件要有铺垫

### 避免问题
- 不要让主角无所不能
- 不要让发展毫无阻碍
- 不要让配角沦为背景板
- 不要让日常变成流水账""",

            "default": """

## 通用写作要求
- 保持故事连贯性
- 人物性格一致
- 情节发展合理"""
        }
        
        return base + genre_specific.get(genre, genre_specific["default"])
    
    @staticmethod
    def chapter_writing_user(
        chapter_outline: str,
        context: str,
        worldbook: Dict[str, Any],
        target_words: int = 3000,
        special_requirements: Optional[str] = None
    ) -> str:
        """章节写作用户提示词"""
        
        parts = []
        
        # 大纲部分
        parts.append("# 本章大纲\n")
        parts.append(chapter_outline)
        parts.append("\n")
        
        # 前文摘要
        if context:
            parts.append("# 前文摘要\n")
            parts.append(context)
            parts.append("\n")
        
        # 世界书信息
        if worldbook:
            parts.append("# 相关设定信息\n")
            
            # 人物
            if "characters" in worldbook and worldbook["characters"]:
                parts.append("## 本章涉及人物\n")
                for char_id, char in worldbook["characters"].items():
                    if isinstance(char, dict):
                        name = char.get("name", char_id)
                        traits = char.get("personality", {}).get("core_traits", [])
                        speech = char.get("personality", {}).get("speech_pattern", "")
                        parts.append(f"- **{name}**")
                        if traits:
                            parts.append(f"  - 性格：{', '.join(traits)}")
                        if speech:
                            parts.append(f"  - 说话方式：{speech}")
                parts.append("\n")
            
            # 地点
            if "locations" in worldbook and worldbook["locations"]:
                parts.append("## 当前场景\n")
                for loc_id, loc in worldbook["locations"].items():
                    if isinstance(loc, dict):
                        name = loc.get("name", loc_id)
                        features = loc.get("features", {})
                        parts.append(f"- **{name}**")
                        if features:
                            parts.append(f"  - {json.dumps(features, ensure_ascii=False)[:200]}")
                parts.append("\n")
            
            # 规则提醒
            if "rules" in worldbook and worldbook["rules"]:
                parts.append("## 写作规则提醒\n")
                for rule_name, rule in worldbook["rules"].items():
                    if isinstance(rule, dict):
                        parts.append(f"**{rule.get('name', rule_name)}**：")
                        for r in rule.get("rules", [])[:3]:
                            parts.append(f"  - {r}")
                parts.append("\n")
        
        # 写作要求
        parts.append("# 写作要求\n")
        parts.append(f"1. 字数要求：约{target_words}字（2500-4000字范围内）")
        parts.append("2. 直接输出正文，不要包含章节标题")
        parts.append("3. 保持与前文的连贯性")
        parts.append("4. 遵循大纲安排，可适当丰富细节")
        parts.append("5. 保持人物性格一致")
        
        if special_requirements:
            parts.append(f"\n## 特殊要求\n{special_requirements}")
        
        parts.append("\n请开始写作本章内容：")
        
        return "\n".join(parts)
    
    # ============== 分析类提示词 ==============
    
    @staticmethod
    def quality_analysis_system() -> str:
        """质量分析系统提示词"""
        return """你是一位资深的小说编辑和评论家，擅长分析网络小说的质量。

## 分析维度
1. **一致性**：人物性格、世界观规则、时间线
2. **节奏**：日常/事件比例、张力曲线、信息密度
3. **文笔**：重复率、表达多样性、描写质量
4. **逻辑**：因果关系、金手指使用、情节合理性

## 输出格式
请以JSON格式输出分析结果，包含：
- overall_score: 总分(1-10)
- dimensions: 各维度评分
- issues: 问题列表
- suggestions: 改进建议

## 评分标准
- 9-10: 优秀，几乎无问题
- 7-8: 良好，小问题可接受
- 5-6: 及格，需要关注
- 3-4: 需改进，建议修改
- 1-2: 严重问题，需要重写"""
    
    @staticmethod
    def quality_analysis_user(
        chapters: str,
        worldbook: Dict[str, Any],
        focus_areas: Optional[list] = None
    ) -> str:
        """质量分析用户提示词"""
        
        parts = []
        parts.append("# 待分析内容\n")
        parts.append(chapters)
        parts.append("\n")
        
        if worldbook:
            parts.append("# 参考设定\n")
            parts.append(json.dumps(worldbook, ensure_ascii=False, indent=2)[:2000])
            parts.append("\n")
        
        parts.append("# 分析要求\n")
        if focus_areas:
            parts.append(f"重点关注：{', '.join(focus_areas)}\n")
        
        parts.append("""请分析以上内容，输出JSON格式的评估结果：
```json
{
    "overall_score": 0,
    "dimensions": {
        "consistency": {"score": 0, "details": ""},
        "pacing": {"score": 0, "details": ""},
        "writing": {"score": 0, "details": ""},
        "logic": {"score": 0, "details": ""}
    },
    "issues": [
        {"severity": "high/medium/low", "type": "", "description": "", "location": ""}
    ],
    "suggestions": [""]
}
```""")
        
        return "\n".join(parts)
    
    # ============== 修正类提示词 ==============
    
    @staticmethod
    def revision_system() -> str:
        """章节修正系统提示词"""
        return """你是一位专业的小说编辑，负责修正和润色章节内容。

## 修正原则
- 保持原文风格和语气
- 只修正明确的问题
- 不大幅改变内容走向
- 保持字数相近

## 修正类型
1. 一致性错误修正
2. 重复表达优化
3. 逻辑漏洞填补
4. 描写质量提升"""
    
    @staticmethod
    def revision_user(
        original_content: str,
        issues: list,
        revision_instructions: str
    ) -> str:
        """章节修正用户提示词"""
        
        parts = []
        parts.append("# 原始内容\n")
        parts.append(original_content)
        parts.append("\n")
        
        parts.append("# 需要修正的问题\n")
        for i, issue in enumerate(issues, 1):
            if isinstance(issue, dict):
                parts.append(f"{i}. [{issue.get('type', '问题')}] {issue.get('description', '')}")
            else:
                parts.append(f"{i}. {issue}")
        parts.append("\n")
        
        parts.append("# 修正说明\n")
        parts.append(revision_instructions)
        parts.append("\n")
        
        parts.append("请输出修正后的完整章节内容（直接输出正文，不要解释）：")
        
        return "\n".join(parts)
    
    # ============== 大纲类提示词 ==============
    
    @staticmethod
    def chapter_outline_system() -> str:
        """章节大纲生成系统提示词"""
        return """你是一位专业的小说策划，负责生成详细的章节大纲。

## 章节大纲要求
- 明确本章目的（推进什么）
- 场景安排（地点、人物）
- 情节要点（发生什么）
- 氛围基调（什么感觉）
- 字数分配建议

## 输出格式
使用Markdown格式，包含：
- 章节标题
- 本章目的
- 场景安排
- 写作要点
- 注意事项"""
    
    @staticmethod
    def chapter_outline_user(
        volume_outline: str,
        part_outline: str,
        chapter_number: int,
        previous_chapters_summary: str
    ) -> str:
        """章节大纲生成用户提示词"""
        
        return f"""# 参考信息

## 卷纲
{volume_outline}

## 篇纲
{part_outline}

## 前文发展
{previous_chapters_summary}

# 任务

请为第{chapter_number}章生成详细的章节大纲。

输出格式：
```markdown
# 第{chapter_number}章：[标题]

## 本章目的
- [目的1]
- [目的2]

## 场景安排
### 场景1：[场景名]（约xxx字）
- 内容：
- 氛围：
- 重点：

### 场景2：[场景名]（约xxx字）
...

## 写作要点
- [要点1]
- [要点2]

## 注意事项
- [注意1]
```"""


# 为了避免循环导入，这里做个简单的json模拟
import json


if __name__ == "__main__":
    # 测试模板
    templates = PromptTemplates()
    
    print("=== 写作系统提示词 ===")
    print(templates.chapter_writing_system()[:500])
    print("...")
    
    print("\n=== 质量分析系统提示词 ===")
    print(templates.quality_analysis_system()[:500])
    print("...")
