"""
故事状态管理系统
负责：加载状态、生成上下文、更新状态、一致性检查
集成 SimpleMem 提供语义记忆检索能力
"""

import json
import re
from pathlib import Path
from datetime import datetime
from openai import OpenAI
from typing import Optional, List

PROJECT_PATH = Path(r"e:\Test\xiaoshuo\projects\western-fantasy")
STATE_PATH = PROJECT_PATH / "worldbook" / "dynamic" / "story_state.json"

# 加载API密钥
with open(r"e:\Test\xiaoshuo\deepseek_api.txt", 'r') as f:
    API_KEY = f.read().strip()

client = OpenAI(api_key=API_KEY, base_url="https://api.deepseek.com")

# SimpleMem 适配器（延迟加载）
_memory_adapter = None

def get_memory_adapter():
    """获取或创建记忆适配器（单例模式）"""
    global _memory_adapter
    if _memory_adapter is None:
        try:
            from story_memory_adapter import StoryMemoryAdapter
            _memory_adapter = StoryMemoryAdapter(clear_db=False)
        except Exception as e:
            print(f"⚠️ SimpleMem 加载失败: {e}")
            _memory_adapter = None
    return _memory_adapter


class StoryStateManager:
    """故事状态管理器"""
    
    def __init__(self):
        self.state = self.load_state()
    
    def load_state(self) -> dict:
        """加载当前状态"""
        if STATE_PATH.exists():
            with open(STATE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def save_state(self):
        """保存状态"""
        self.state["meta"]["last_updated"] = datetime.now().strftime("%Y-%m-%d")
        with open(STATE_PATH, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)
    
    def generate_context_for_writing(self, chapter_num: int, topics: List[str] = None, use_semantic_memory: bool = True) -> str:
        """
        为写作生成上下文（注入prompt用）
        
        Args:
            chapter_num: 章节号
            topics: 本章涉及的主题（可选，用于语义检索）
            use_semantic_memory: 是否使用 SimpleMem 语义记忆
        """
        
        state = self.state
        
        context = f"""## 当前故事状态（第{chapter_num}章写作用）

### 时间
- 故事时间：{state.get('meta', {}).get('story_time', '未知')}
- 当前章节：第{chapter_num}章

### 主角状态
- 姓名：{state.get('protagonist', {}).get('name', '艾伦·诺斯')}
- 境界：{state.get('protagonist', {}).get('realm', {}).get('current', '未知')} ({state.get('protagonist', {}).get('realm', {}).get('level', '')})
- 位置：{state.get('protagonist', {}).get('location', '未知')}
- 技能：{', '.join([s['name'] for s in state.get('protagonist', {}).get('skills', [])])}

### 领地状态
- 人口：{state.get('territory', {}).get('population', 0)}人
- 设施：{', '.join([f['name'] for f in state.get('territory', {}).get('facilities', [])])}
- 军事：巡逻队{state.get('territory', {}).get('military', {}).get('patrol_team', 0)}人，民兵{state.get('territory', {}).get('military', {}).get('militia', 0)}人

### 关键角色
"""
        for name, info in state.get('characters', {}).items():
            if info.get('status') == '健康':
                context += f"- {name}：{info.get('role', '')}，{info.get('location', '')}\n"
        
        context += f"""
### 最近事件
"""
        for event in state.get('recent_events', [])[-3:]:
            context += f"- {event}\n"
        
        context += f"""
### 待回收伏笔
"""
        for thread in state.get('pending_threads', [])[:3]:
            context += f"- {thread.get('thread', '')} (期待章节：{thread.get('expected_chapter', '')})\n"
        
        context += f"""
### 禁止使用
- 现代词汇：{', '.join(state.get('forbidden_elements', {}).get('modern_terms', [])[:5])}
- 已解决的问题不再重复提及

### 境界体系（重要）
感知者 → 凝聚者 → 外显者 → 领域者 → 大师 → 圣阶
- 主角当前：{state.get('protagonist', {}).get('realm', {}).get('current', '')}
- 格雷当前：感知者中期
"""
        
        # 添加语义记忆检索（如果启用）
        if use_semantic_memory:
            memory_context = self._get_semantic_memory_context(chapter_num, topics)
            if memory_context:
                context += f"""
### 📚 语义记忆（来自前文）
{memory_context}
"""
        
        return context
    
    def _get_semantic_memory_context(self, chapter_num: int, topics: List[str] = None) -> str:
        """从 SimpleMem 获取语义记忆上下文"""
        adapter = get_memory_adapter()
        if adapter is None:
            return ""
        
        try:
            memory_parts = []
            
            # 查询前文关键事件
            events = adapter.query_context(f"第{chapter_num-5}章到第{chapter_num-1}章的重要事件", max_entries=5)
            if events and events != "未找到相关记忆":
                memory_parts.append(f"**前文事件**:\n{events}")
            
            # 如果有特定主题，查询相关内容
            if topics:
                for topic in topics[:3]:  # 最多3个主题
                    topic_memory = adapter.query_context(topic, max_entries=3)
                    if topic_memory and topic_memory != "未找到相关记忆":
                        memory_parts.append(f"**{topic}相关**:\n{topic_memory}")
            
            return "\n\n".join(memory_parts)
            
        except Exception as e:
            print(f"⚠️ 语义记忆检索失败: {e}")
            return ""
    
    def extract_state_changes(self, chapter_num: int, content: str) -> dict:
        """从新章节内容中提取状态变化"""
        
        prompt = f"""请分析以下第{chapter_num}章的内容，提取需要更新的状态变化。

## 章节内容
{content[:6000]}

## 需要提取的信息
请以JSON格式输出以下变化（如果有的话），没有变化的项留空：

```json
{{
  "realm_change": null,  // 如果有境界突破，填写新境界
  "location_change": null,  // 如果位置变化，填写新位置
  "new_characters": [],  // 新登场的重要角色
  "character_status_changes": {{}},  // 角色状态变化（如受伤、死亡）
  "new_skills": [],  // 新获得的技能
  "new_facilities": [],  // 新建的设施
  "population_change": null,  // 人口变化
  "key_events": [],  // 本章关键事件（1-2条）
  "new_threads": [],  // 新埋下的伏笔
  "resolved_threads": [],  // 本章回收的伏笔
  "time_progression": null  // 时间推进描述（如"过了三天"）
}}
```

只输出JSON，不要其他内容：
"""

        try:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "你是小说状态分析师。精确提取章节中的状态变化，以JSON格式输出。"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1500,
                temperature=0.1
            )
            
            result_text = response.choices[0].message.content
            
            # 提取JSON
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', result_text)
            if json_match:
                return json.loads(json_match.group(1))
            else:
                return json.loads(result_text)
                
        except Exception as e:
            print(f"  ⚠️ 状态提取失败: {e}")
            return {}
    
    def update_state_after_chapter(self, chapter_num: int, changes: dict):
        """根据提取的变化更新状态"""
        
        # 更新元信息
        self.state["meta"]["current_chapter"] = chapter_num
        
        # 境界变化
        if changes.get("realm_change"):
            self.state["protagonist"]["realm"]["current"] = changes["realm_change"]
            self.state["protagonist"]["realm"]["level"] = "初阶"
            self.state["protagonist"]["realm"]["breakthrough_chapter"] = chapter_num
        
        # 位置变化
        if changes.get("location_change"):
            self.state["protagonist"]["location"] = changes["location_change"]
        
        # 新技能
        for skill in changes.get("new_skills", []):
            self.state["protagonist"]["skills"].append({
                "name": skill,
                "level": "基础",
                "source": f"第{chapter_num}章获得"
            })
        
        # 人口变化
        if changes.get("population_change"):
            try:
                self.state["territory"]["population"] += int(changes["population_change"])
            except:
                pass
        
        # 关键事件
        for event in changes.get("key_events", []):
            event_str = f"第{chapter_num}章：{event}"
            if event_str not in self.state["recent_events"]:
                self.state["recent_events"].append(event_str)
        
        # 保持最近事件只有10条
        self.state["recent_events"] = self.state["recent_events"][-10:]
        
        # 新伏笔
        for thread in changes.get("new_threads", []):
            self.state["pending_threads"].append({
                "thread": thread,
                "urgency": "中",
                "expected_chapter": f"{chapter_num + 5}+"
            })
        
        # 回收的伏笔
        for resolved in changes.get("resolved_threads", []):
            self.state["pending_threads"] = [
                t for t in self.state["pending_threads"] 
                if resolved.lower() not in t.get("thread", "").lower()
            ]
            self.state["forbidden_elements"]["resolved_threads"].append(resolved)
        
        # 时间推进
        if changes.get("time_progression"):
            self.state["meta"]["story_time"] += f" ({changes['time_progression']})"
        
        # 时间线更新
        for event in changes.get("key_events", [])[:1]:
            self.state["timeline"].append({
                "chapter": chapter_num,
                "event": event,
                "time": self.state["meta"]["story_time"]
            })
        
        self.save_state()
        print(f"  📝 状态已更新")
    
    def check_consistency(self, chapter_num: int, content: str) -> list:
        """一致性检查"""
        
        issues = []
        state = self.state
        
        # 1. 境界一致性
        current_realm = state.get("protagonist", {}).get("realm", {}).get("current", "")
        if current_realm:
            # 检查是否有错误的境界描述
            wrong_realms = ["凝聚者", "外显者", "领域者", "大师", "圣阶"]
            if current_realm in wrong_realms:
                wrong_realms.remove(current_realm)
            
            for wrong in wrong_realms:
                if f"艾伦是{wrong}" in content or f"已是{wrong}" in content:
                    if wrong != current_realm:
                        issues.append(f"境界错误：主角当前应为{current_realm}，但内容提及{wrong}")
        
        # 2. 禁用词汇检查
        for term in state.get("forbidden_elements", {}).get("modern_terms", []):
            if term in content:
                issues.append(f"现代词汇：发现'{term}'")
        
        # 3. 死亡角色检查
        for char in state.get("forbidden_elements", {}).get("dead_characters", []):
            if char in content and "回忆" not in content[:500]:
                issues.append(f"角色错误：{char}已死亡，不应出现")
        
        return issues


# 便捷函数
def get_writing_context(chapter_num: int) -> str:
    """获取写作上下文"""
    manager = StoryStateManager()
    return manager.generate_context_for_writing(chapter_num)

def update_state_after_writing(chapter_num: int, content: str):
    """写作后更新状态"""
    manager = StoryStateManager()
    changes = manager.extract_state_changes(chapter_num, content)
    if changes:
        manager.update_state_after_chapter(chapter_num, changes)
    return changes

def check_chapter_consistency(chapter_num: int, content: str) -> list:
    """检查章节一致性"""
    manager = StoryStateManager()
    return manager.check_consistency(chapter_num, content)


if __name__ == "__main__":
    # 测试
    manager = StoryStateManager()
    context = manager.generate_context_for_writing(61)
    print(context)
