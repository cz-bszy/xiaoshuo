"""
深度校正脚本 v2
针对分析报告中的具体问题进行逐章修正
使用分段处理解决长文本限制
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

def load_analysis_report():
    """加载分析报告"""
    report_path = PROJECT_PATH / "analysis_report.json"
    if report_path.exists():
        with open(report_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def load_chapter(chapter_num: int) -> tuple:
    """加载章节内容"""
    chapter_dir = PROJECT_PATH / "chapters" / "v01"
    for f in chapter_dir.glob(f"第{chapter_num}章_*.txt"):
        with open(f, 'r', encoding='utf-8') as file:
            return f, file.read()
    return None, ""

def save_chapter(filepath: Path, content: str):
    """保存修正后的章节"""
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

def get_chapter_issues(chapter_num: int, report: list) -> dict:
    """获取章节问题"""
    for item in report:
        if item.get("chapter") == chapter_num:
            return item.get("analysis", {})
    return {}

def fix_specific_issues(content: str, issues: dict, chapter_num: int) -> str:
    """修复具体问题（使用小范围替换）"""
    
    if not issues:
        return content
    
    # 1. 处理时代错误
    time_errors = issues.get("time_period_errors", [])
    for error in time_errors:
        if error.get("is_flashback", False):
            continue  # 跳过回忆场景
        
        original = error.get("text", "")
        suggestion = error.get("suggestion", "")
        
        if original and suggestion and original in content:
            # 直接替换
            content = content.replace(original, suggestion, 1)
            print(f"    ✓ 时代错误修复：{original[:30]}...")
    
    # 2. 处理质量问题（文笔优化）
    quality_issues = issues.get("quality_issues", [])
    for issue in quality_issues:
        original = issue.get("text", "")
        suggestion = issue.get("suggestion", "")
        
        if original and suggestion:
            # 提取原文中的关键句子
            if original in content:
                content = content.replace(original, suggestion, 1)
                print(f"    ✓ 文笔优化：{original[:30]}...")
    
    return content

def analyze_and_fix_chapter(chapter_num: int, content: str) -> str:
    """分析并修复单个章节（使用Reasoner）"""
    
    # 将章节分成几段（每段约3000字）处理
    chunk_size = 3000
    chunks = []
    
    # 按段落分割
    paragraphs = content.split('\n\n')
    current_chunk = ""
    
    for para in paragraphs:
        if len(current_chunk) + len(para) < chunk_size:
            current_chunk += para + "\n\n"
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = para + "\n\n"
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    # 对每段进行分析和修复
    fixed_chunks = []
    
    for i, chunk in enumerate(chunks):
        prompt = f"""请仔细检查以下第{chapter_num}章的片段，修复以下问题：

1. **现代词汇**：将不符合中世纪西幻设定的词汇替换（电脑→账簿、投资→付出、机制→法子等）
2. **时代错误**：修正不符合时代的表达方式
3. **文笔优化**：优化啰嗦或重复的表达

原文片段：
{chunk}

要求：
- 只修改有问题的地方，保持其他内容不变
- 保持原文风格和语气
- 不要添加新内容，不要删除重要内容
- 如果没有问题，直接返回原文

直接输出修改后的内容："""

        try:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "你是专业的网络小说编辑。只修改有问题的地方，保持原文风格。"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=4000,
                temperature=0.2
            )
            
            fixed_chunk = response.choices[0].message.content
            fixed_chunks.append(fixed_chunk)
            
        except Exception as e:
            print(f"    ⚠️ 片段{i+1}处理失败: {e}")
            fixed_chunks.append(chunk)  # 保留原文
        
        time.sleep(1)  # 避免限流
    
    return "\n\n".join(fixed_chunks)

def run_deep_correction(start_chapter: int = 1, end_chapter: int = 60, mode: str = "report"):
    """运行深度校正
    
    mode: 
        "report" - 仅使用报告中的已知问题修复（快速）
        "full" - 全面分析每章并修复（慢但彻底）
    """
    
    print("=" * 60)
    print(f"🔧 深度校正：第{start_chapter}章 到 第{end_chapter}章")
    print(f"   模式：{'基于报告' if mode == 'report' else '全面分析'}")
    print("=" * 60)
    
    report = load_analysis_report()
    print(f"📊 加载分析报告：{len(report)} 个章节")
    
    stats = {
        "chapters_fixed": 0,
        "issues_fixed": 0
    }
    
    for chapter in range(start_chapter, end_chapter + 1):
        print(f"\n📖 第{chapter}章...")
        
        filepath, content = load_chapter(chapter)
        if not content:
            print(f"  ⚠️ 未找到")
            continue
        
        original_content = content
        
        if mode == "report":
            # 基于报告修复
            issues = get_chapter_issues(chapter, report)
            if issues:
                print(f"  🔍 发现 {len(issues.get('time_period_errors', []))} 个时代错误，{len(issues.get('quality_issues', []))} 个文笔问题")
                content = fix_specific_issues(content, issues, chapter)
            else:
                print(f"  ○ 无报告，跳过")
                continue
        else:
            # 全面分析修复
            print(f"  🧠 全面分析...")
            content = analyze_and_fix_chapter(chapter, content)
        
        # 保存
        if content != original_content:
            save_chapter(filepath, content)
            stats["chapters_fixed"] += 1
            print(f"  ✅ 已修正")
        else:
            print(f"  ○ 无变化")
        
        # 进度报告
        if chapter % 10 == 0:
            print(f"\n{'=' * 40}")
            print(f"📊 进度：{chapter}/{end_chapter}")
            print(f"   已修正：{stats['chapters_fixed']} 章")
            print(f"{'=' * 40}\n")
    
    print("\n" + "=" * 60)
    print("📊 深度校正完成")
    print("=" * 60)
    print(f"  修正章节：{stats['chapters_fixed']} 章")
    
    return stats

if __name__ == "__main__":
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    mode = sys.argv[3] if len(sys.argv) > 3 else "report"
    
    run_deep_correction(start, end, mode)
