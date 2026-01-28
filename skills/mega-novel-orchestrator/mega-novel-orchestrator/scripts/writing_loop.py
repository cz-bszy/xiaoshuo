"""
自动写作循环
实现批量自动写作的核心逻辑
"""

import json
import asyncio
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

from orchestrator import MegaNovelOrchestrator, ChapterTask
from api_client import DeepSeekClient, WritingPrompt, get_default_system_prompt, get_default_user_prompt
from prompt_templates import PromptTemplates


class WritingLoop:
    """自动写作循环"""
    
    def __init__(self, project_path: str):
        self.orchestrator = MegaNovelOrchestrator(project_path)
        self.client: Optional[DeepSeekClient] = None
        self.templates = PromptTemplates()
        
        # 配置
        self.batch_size = 5  # 每批写作章节数
        self.quality_check_interval = 5  # 质量检查间隔
        self.auto_retry = True  # 自动重试失败章节
        self.max_retries = 3  # 最大重试次数
        
        # 状态
        self.is_running = False
        self.chapters_written_this_session = 0
        self.session_start_time = None
        
    def initialize(self) -> bool:
        """初始化写作循环"""
        # 加载项目
        if not self.orchestrator.load_project():
            return False
        
        # 初始化API客户端
        try:
            model_config = self.orchestrator.config.get("models", {}).get("writing", {})
            self.client = DeepSeekClient(
                api_key=model_config.get("api_key"),
                api_base=model_config.get("api_base", "https://api.deepseek.com"),
                model=model_config.get("model", "deepseek-chat")
            )
        except Exception as e:
            print(f"初始化API客户端失败：{e}")
            return False
        
        # 加载自动化配置
        auto_config = self.orchestrator.config.get("automation", {})
        self.batch_size = auto_config.get("auto_write_batch", 5)
        self.quality_check_interval = auto_config.get("quality_check_interval", 5)
        
        return True
    
    def write_single_chapter(self, task: ChapterTask) -> Dict[str, Any]:
        """写作单个章节"""
        print(f"\n📝 开始写作：第{task.volume}卷 第{task.chapter}章 - {task.title}")
        
        result = {
            "success": False,
            "chapter_id": f"v{task.volume:02d}c{task.chapter:03d}",
            "content": "",
            "word_count": 0,
            "issues": [],
            "retries": 0
        }
        
        # 构建提示词
        system_prompt = self.templates.chapter_writing_system("western-fantasy-farming")
        user_prompt = self.templates.chapter_writing_user(
            chapter_outline=task.chapter_outline,
            context=task.context,
            worldbook=task.worldbook_context,
            target_words=task.target_words
        )
        
        prompt = WritingPrompt(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            chapter_outline=task.chapter_outline,
            context=task.context,
            worldbook=task.worldbook_context
        )
        
        # 调用写作API
        for attempt in range(self.max_retries):
            try:
                content = self.client.generate_chapter(
                    prompt=prompt,
                    temperature=0.8,
                    max_tokens=4000
                )
                
                # 基本检查
                word_count = len(content)
                min_words = self.orchestrator.config.get("quality", {}).get("min_words_per_chapter", 2500)
                max_words = self.orchestrator.config.get("quality", {}).get("max_words_per_chapter", 4000)
                
                if word_count < min_words:
                    result["issues"].append(f"字数不足：{word_count} < {min_words}")
                    if attempt < self.max_retries - 1:
                        print(f"  ⚠️ 字数不足，重试中...")
                        result["retries"] += 1
                        continue
                
                if word_count > max_words * 1.2:  # 允许20%的超出
                    result["issues"].append(f"字数过多：{word_count}")
                
                result["content"] = content
                result["word_count"] = word_count
                result["success"] = True
                print(f"  ✅ 完成：{word_count}字")
                break
                
            except Exception as e:
                result["issues"].append(f"API错误：{str(e)}")
                if attempt < self.max_retries - 1:
                    print(f"  ⚠️ 出错，重试中：{e}")
                    result["retries"] += 1
                    time.sleep(2 ** attempt)
                else:
                    print(f"  ❌ 失败：{e}")
        
        return result
    
    def quick_consistency_check(self, content: str, worldbook: Dict) -> List[str]:
        """快速一致性检查"""
        issues = []
        
        # 简单的关键词检查
        # 这里只是示例，实际应该更复杂
        
        # 检查是否提到了不应该存在的技术
        forbidden_tech = ["手机", "电脑", "汽车", "电力", "互联网", "枪"]
        for tech in forbidden_tech:
            if tech in content:
                issues.append(f"可能的时代错误：提到了'{tech}'")
        
        # 检查魔法相关（低魔设定）
        high_magic_keywords = ["毁天灭地", "一招秒杀", "无敌", "碾压", "神级"]
        for keyword in high_magic_keywords:
            if keyword in content:
                issues.append(f"可能违反低魔设定：使用了'{keyword}'")
        
        return issues
    
    def run_batch(self, batch_size: Optional[int] = None) -> Dict[str, Any]:
        """运行一批写作任务"""
        if batch_size is None:
            batch_size = self.batch_size
        
        self.session_start_time = datetime.now()
        self.chapters_written_this_session = 0
        
        results = {
            "success_count": 0,
            "fail_count": 0,
            "total_words": 0,
            "chapters": [],
            "needs_review": False,
            "review_reason": ""
        }
        
        print(f"\n🚀 开始批量写作：计划写作 {batch_size} 章")
        print("=" * 50)
        
        for i in range(batch_size):
            # 获取下一章任务
            task = self.orchestrator.get_next_chapter_task()
            if not task:
                print("⚠️ 没有更多章节任务")
                break
            
            # 写作章节
            result = self.write_single_chapter(task)
            results["chapters"].append(result)
            
            if result["success"]:
                # 快速一致性检查
                issues = self.quick_consistency_check(
                    result["content"],
                    task.worldbook_context
                )
                result["issues"].extend(issues)
                
                if issues:
                    print(f"  ⚠️ 发现问题：{len(issues)}个")
                    for issue in issues:
                        print(f"     - {issue}")
                
                # 保存章节
                self.orchestrator.save_chapter(
                    task.volume,
                    task.chapter,
                    result["content"]
                )
                
                results["success_count"] += 1
                results["total_words"] += result["word_count"]
                self.chapters_written_this_session += 1
            else:
                results["fail_count"] += 1
            
            # 检查是否需要质量检查
            if self.chapters_written_this_session % self.quality_check_interval == 0:
                results["needs_review"] = True
                results["review_reason"] = f"已写作{self.chapters_written_this_session}章，建议进行质量检查"
        
        # 会话统计
        duration = (datetime.now() - self.session_start_time).total_seconds()
        print("\n" + "=" * 50)
        print(f"📊 批次完成统计")
        print(f"  成功：{results['success_count']} 章")
        print(f"  失败：{results['fail_count']} 章")
        print(f"  总字数：{results['total_words']:,}")
        print(f"  耗时：{duration:.1f}秒")
        
        if results["needs_review"]:
            print(f"\n⚠️ {results['review_reason']}")
        
        return results
    
    def get_session_status(self) -> str:
        """获取当前会话状态"""
        status = self.orchestrator.get_status()
        
        session_info = f"""
📋 本次会话
├── 已写章节：{self.chapters_written_this_session}
└── 运行时长：{(datetime.now() - self.session_start_time).total_seconds():.0f}秒
""" if self.session_start_time else ""
        
        return status + session_info


def main():
    """主函数"""
    import sys
    
    if len(sys.argv) < 3:
        print("用法：")
        print("  python writing_loop.py run <项目路径> [章节数]")
        print("  python writing_loop.py test <项目路径>")
        sys.exit(1)
    
    command = sys.argv[1]
    project_path = sys.argv[2]
    
    loop = WritingLoop(project_path)
    
    if command == "run":
        if not loop.initialize():
            print("初始化失败")
            sys.exit(1)
        
        batch_size = int(sys.argv[3]) if len(sys.argv) > 3 else 5
        results = loop.run_batch(batch_size)
        
        if results["needs_review"]:
            print("\n建议：请使用监控界面进行质量评估")
    
    elif command == "test":
        if not loop.initialize():
            print("初始化失败")
            sys.exit(1)
        
        print("✅ 初始化成功！")
        print(loop.orchestrator.get_status())
    
    else:
        print(f"未知命令：{command}")


if __name__ == "__main__":
    main()
