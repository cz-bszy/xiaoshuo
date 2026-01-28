"""
Mega Novel Orchestrator - 核心调度模块
超长篇小说自动化写作系统

用于调度写作模型(DeepSeek)和监控界面
"""

import json
import os
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from enum import Enum


class ProjectStatus(Enum):
    """项目状态"""
    INIT = "init"           # 初始化中
    PLANNING = "planning"   # 规划中
    READY = "ready"         # 准备就绪
    WRITING = "writing"     # 写作中
    PAUSED = "paused"       # 暂停
    COMPLETED = "completed" # 完成


@dataclass
class ChapterTask:
    """章节写作任务"""
    volume: int
    chapter: int
    title: str
    chapter_outline: str
    target_words: int
    context: str  # 前文摘要
    worldbook_context: Dict[str, Any]  # 相关世界书信息


@dataclass
class WriteResult:
    """写作结果"""
    chapter_id: str
    content: str
    word_count: int
    success: bool
    issues: List[str]
    timestamp: str


class MegaNovelOrchestrator:
    """超长篇小说调度器"""
    
    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.config: Dict[str, Any] = {}
        self.state: Dict[str, Any] = {}
        
    def load_project(self) -> bool:
        """加载项目"""
        config_path = self.project_path / "config.yaml"
        state_path = self.project_path / "project-state.json"
        
        if not config_path.exists():
            print(f"错误：配置文件不存在 {config_path}")
            return False
            
        # 加载配置
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
            
        # 加载状态
        if state_path.exists():
            with open(state_path, 'r', encoding='utf-8') as f:
                self.state = json.load(f)
        else:
            self.state = self._init_state()
            
        return True
    
    def _init_state(self) -> Dict[str, Any]:
        """初始化项目状态"""
        return {
            "project": {
                "name": self.config.get("project", {}).get("name", "未命名"),
                "created": datetime.now().isoformat(),
                "status": ProjectStatus.INIT.value
            },
            "progress": {
                "current": {
                    "volume": 1,
                    "part": 1,
                    "chapter": 0
                },
                "completed": {
                    "words": 0,
                    "chapters": 0,
                    "volumes": 0
                },
                "percentage": 0.0
            },
            "milestones": [],
            "statistics": {
                "avg_words_per_chapter": 0,
                "total_writing_time": 0,
                "sessions": []
            },
            "issues": []
        }
    
    def save_state(self):
        """保存项目状态"""
        state_path = self.project_path / "project-state.json"
        with open(state_path, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)
    
    def get_next_chapter_task(self) -> Optional[ChapterTask]:
        """获取下一章写作任务"""
        current = self.state["progress"]["current"]
        next_chapter = current["chapter"] + 1
        volume = current["volume"]
        
        # 检查是否需要进入下一卷
        chapters_per_volume = self.config.get("project", {}).get("chapters_per_volume", 100)
        if next_chapter > chapters_per_volume:
            volume += 1
            next_chapter = 1
            
        # 读取章纲
        chapter_outline = self._load_chapter_outline(volume, next_chapter)
        if not chapter_outline:
            return None
            
        # 构建上下文
        context = self._build_context(volume, next_chapter)
        worldbook = self._load_relevant_worldbook(volume, next_chapter)
        
        return ChapterTask(
            volume=volume,
            chapter=next_chapter,
            title=chapter_outline.get("title", f"第{next_chapter}章"),
            chapter_outline=chapter_outline.get("content", ""),
            target_words=self.config.get("project", {}).get("words_per_chapter", 3000),
            context=context,
            worldbook_context=worldbook
        )
    
    def _load_chapter_outline(self, volume: int, chapter: int) -> Optional[Dict]:
        """加载章节大纲"""
        outline_path = self.project_path / "outline" / "L3-chapters" / f"v{volume:02d}-c{chapter:03d}.md"
        
        if not outline_path.exists():
            # 尝试自动生成（需要调用大纲管理器）
            return None
            
        with open(outline_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        return {
            "title": self._extract_title(content),
            "content": content
        }
    
    def _extract_title(self, content: str) -> str:
        """从大纲中提取标题"""
        for line in content.split('\n'):
            if line.startswith('# '):
                return line[2:].strip()
        return "未命名章节"
    
    def _build_context(self, volume: int, chapter: int, context_chapters: int = 3) -> str:
        """构建写作上下文（前N章摘要）"""
        context_parts = []
        
        for i in range(max(1, chapter - context_chapters), chapter):
            chapter_path = self.project_path / "chapters" / f"v{volume:02d}" / f"c{i:03d}.md"
            if chapter_path.exists():
                with open(chapter_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # 提取摘要（前500字或到第一个分隔）
                    summary = content[:500] + "..." if len(content) > 500 else content
                    context_parts.append(f"【第{i}章摘要】\n{summary}")
        
        return "\n\n".join(context_parts)
    
    def _load_relevant_worldbook(self, volume: int, chapter: int) -> Dict[str, Any]:
        """加载相关世界书信息"""
        worldbook = {}
        
        # 加载人物信息
        characters_path = self.project_path / "worldbook" / "characters.json"
        if characters_path.exists():
            with open(characters_path, 'r', encoding='utf-8') as f:
                all_chars = json.load(f)
                # 只加载活跃人物（最近出场的）
                worldbook["characters"] = self._filter_active_characters(all_chars, volume, chapter)
        
        # 加载当前场景
        locations_path = self.project_path / "worldbook" / "locations.json"
        if locations_path.exists():
            with open(locations_path, 'r', encoding='utf-8') as f:
                worldbook["locations"] = json.load(f)
        
        # 加载规则
        rules_path = self.project_path / "worldbook" / "rules.json"
        if rules_path.exists():
            with open(rules_path, 'r', encoding='utf-8') as f:
                worldbook["rules"] = json.load(f)
        
        return worldbook
    
    def _filter_active_characters(self, characters: Dict, volume: int, chapter: int) -> Dict:
        """筛选活跃人物"""
        active = {}
        current_chapter_id = f"v{volume:02d}c{chapter:03d}"
        
        for char_id, char_data in characters.get("characters", {}).items():
            # 主角始终包含
            if char_data.get("type") == "main":
                active[char_id] = char_data
                continue
                
            # 检查最近出场
            appearances = char_data.get("appearances", [])
            if appearances:
                last_appearance = appearances[-1].get("chapter", "")
                # 简单比较（实际应该更复杂）
                if last_appearance >= f"v{volume:02d}c{max(1, chapter-10):03d}":
                    active[char_id] = char_data
                    
        return active
    
    def save_chapter(self, volume: int, chapter: int, content: str, title: str = ""):
        """保存章节
        
        Args:
            volume: 卷号
            chapter: 章节号
            content: 章节内容
            title: 章节标题（用于文件命名）
        """
        chapter_dir = self.project_path / "chapters" / f"v{volume:02d}"
        chapter_dir.mkdir(parents=True, exist_ok=True)
        
        # 获取输出格式和命名方式
        output_format = self.config.get("automation", {}).get("output_format", "md")
        filename_format = self.config.get("automation", {}).get("filename_format", "chapter_number")
        
        # 确定文件名
        if filename_format == "chapter_title" and title:
            # 清理标题中不能用于文件名的字符
            safe_title = title.replace(":", "：").replace("/", "_").replace("\\", "_")
            safe_title = safe_title.replace("?", "？").replace("*", "_").replace('"', "'")
            safe_title = safe_title.replace("<", "《").replace(">", "》").replace("|", "_")
            filename = f"第{chapter}章_{safe_title}"
        else:
            filename = f"c{chapter:03d}"
        
        # 确定扩展名
        ext = "txt" if output_format == "txt" else "md"
        chapter_path = chapter_dir / f"{filename}.{ext}"
        
        # 写入文件（txt格式包含章节标题）
        with open(chapter_path, 'w', encoding='utf-8') as f:
            if output_format == "txt" and title:
                f.write(f"第{chapter}章 {title}\n\n")
            f.write(content)
        
        # 同时保存一份md格式备份（方便读取上下文）
        backup_path = chapter_dir / f"c{chapter:03d}.md"
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # 更新进度
        self.state["progress"]["current"]["volume"] = volume
        self.state["progress"]["current"]["chapter"] = chapter
        self.state["progress"]["completed"]["chapters"] += 1
        self.state["progress"]["completed"]["words"] += len(content)
        
        # 计算百分比
        target_words = self.config.get("project", {}).get("target_words", 4000000)
        self.state["progress"]["percentage"] = round(
            self.state["progress"]["completed"]["words"] / target_words * 100, 1
        )
        
        self.save_state()
        
        return chapter_path
    
    def get_status(self) -> str:
        """获取当前状态报告"""
        p = self.state["progress"]
        project_name = self.state["project"]["name"]
        target_words = self.config.get("project", {}).get("target_words", 4000000)
        
        status = f"""
📊 项目状态报告
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📖 项目：{project_name}
🎯 目标：{target_words:,} 字

📈 当前进度
├── 已完成：{p['completed']['words']:,} 字 ({p['percentage']}%)
├── 已写章节：{p['completed']['chapters']}
├── 当前卷：第{p['current']['volume']}卷
└── 当前章：第{p['current']['chapter']}章

⏱️ 项目状态：{self.state['project']['status']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        return status


def init_project(project_path: str, project_name: str, target_words: int = 4000000):
    """初始化新项目"""
    path = Path(project_path)
    
    # 创建目录结构
    dirs = [
        "outline/L1-volumes",
        "outline/L2-parts", 
        "outline/L3-chapters",
        "chapters",
        "worldbook",
        "logs/quality",
        "logs/progress",
        "logs/revisions",
        "backups"
    ]
    
    for d in dirs:
        (path / d).mkdir(parents=True, exist_ok=True)
    
    # 创建配置文件
    config = {
        "project": {
            "name": project_name,
            "target_words": target_words,
            "words_per_chapter": 3000,
            "chapters_per_volume": 100
        },
        "models": {
            "writing": {
                "provider": "deepseek",
                "model": "deepseek-chat",
                "api_key": "${DEEPSEEK_API_KEY}",
                "api_base": "https://api.deepseek.com",
                "temperature": 0.8,
                "max_tokens": 4000
            }
        },
        "automation": {
            "auto_write_batch": 5,
            "quality_check_interval": 5,
            "auto_save": True,
            "backup_interval": 10
        },
        "quality": {
            "min_words_per_chapter": 2500,
            "max_words_per_chapter": 4000,
            "consistency_check": True,
            "style_check": True
        }
    }
    
    import yaml
    config_path = path / "config.yaml"
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
    
    # 创建空的世界书文件
    worldbook_files = {
        "characters.json": {"characters": {}},
        "locations.json": {"locations": {}},
        "items.json": {"items": {}},
        "events.json": {"events": {}},
        "rules.json": {"rules": {}}
    }
    
    for filename, content in worldbook_files.items():
        with open(path / "worldbook" / filename, 'w', encoding='utf-8') as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
    
    # 创建大纲模板
    main_outline = f"""# 《{project_name}》总纲

## 核心信息

- **类型**：西方幻想、低魔、种田流
- **目标字数**：{target_words:,}字
- **预计卷数**：{target_words // 400000}卷

## 核心主线

[待填写：主角的终极目标和发展方向]

## 世界观核心

### 魔法体系（低魔）
[待填写]

### 社会制度
[待填写]

### 主要势力
[待填写]

## 主角设定

- 姓名：
- 身份：
- 核心目标：
- 成长方向：

## 核心配角

[待填写]

## 终极结局

[待填写]
"""
    
    with open(path / "outline" / "L0-main.md", 'w', encoding='utf-8') as f:
        f.write(main_outline)
    
    # 创建宪法模板
    constitution = f"""# 《{project_name}》创作宪法

## 核心价值观

[待填写：这个故事要传达什么]

## 质量底线

1. [待填写：绝对不能突破的底线]

## 风格原则

### 语言风格
[待填写]

### 叙事风格
[待填写]

### 节奏原则
[待填写]

## 类型原则

### 种田流核心
- 日常种田占比：60-70%
- 发展要有积累感
- 金手指要有限制

### 低魔原则
- 魔法稀少且效果有限
- 不使用高等魔法解决问题
- 技术和劳动是发展核心

## 禁止事项

1. [待填写]
"""
    
    with open(path / "constitution.md", 'w', encoding='utf-8') as f:
        f.write(constitution)
    
    # 创建规格模板
    specification = f"""# 《{project_name}》故事规格

## 一句话概括

[待填写]

## 目标读者

[待填写]

## 核心冲突

### 外部冲突
[待填写]

### 内部冲突
[待填写]

## 主要角色

### 主角
[详细设定]

### 核心配角
[列表]

## 成功标准

- [ ] [待填写]
"""
    
    with open(path / "specification.md", 'w', encoding='utf-8') as f:
        f.write(specification)
    
    print(f"✅ 项目初始化完成：{path}")
    print(f"📁 已创建目录结构和模板文件")
    print(f"📝 下一步：填写 constitution.md 和 specification.md")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("用法：")
        print("  初始化项目：python orchestrator.py init <项目路径> <项目名称> [目标字数]")
        print("  查看状态：python orchestrator.py status <项目路径>")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "init":
        if len(sys.argv) < 4:
            print("用法：python orchestrator.py init <项目路径> <项目名称> [目标字数]")
            sys.exit(1)
        project_path = sys.argv[2]
        project_name = sys.argv[3]
        target_words = int(sys.argv[4]) if len(sys.argv) > 4 else 4000000
        init_project(project_path, project_name, target_words)
        
    elif command == "status":
        if len(sys.argv) < 3:
            print("用法：python orchestrator.py status <项目路径>")
            sys.exit(1)
        project_path = sys.argv[2]
        orchestrator = MegaNovelOrchestrator(project_path)
        if orchestrator.load_project():
            print(orchestrator.get_status())
        else:
            print("加载项目失败")
    
    else:
        print(f"未知命令：{command}")
