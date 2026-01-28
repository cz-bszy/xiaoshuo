"""
实际示例：SimpleMem 记忆系统如何传递给 API
演示完整的"记忆检索→构建Prompt→调用API"流程
"""

import sys
from pathlib import Path
from openai import OpenAI
from typing import List

# 添加 SimpleMem 路径
SIMPLEMEM_PATH = Path(r"e:\Test\xiaoshuo\SimpleMem")
sys.path.insert(0, str(SIMPLEMEM_PATH))

# 导入记忆适配器
from story_memory_adapter import StoryMemoryAdapter

# 加载 API 密钥
with open(r"e:\Test\xiaoshuo\deepseek_api.txt", 'r') as f:
    API_KEY = f.read().strip()


def example_1_basic_memory_to_prompt():
    """
    示例1: 基础流程 - 从记忆检索到 API 调用
    """
    print("=" * 60)
    print("示例1: 基础记忆检索 → Prompt → API")
    print("=" * 60)
    
    # 1. 初始化记忆适配器（连接到已有记忆库）
    print("\n📖 步骤1: 加载记忆库...")
    adapter = StoryMemoryAdapter(clear_db=False)
    
    # 2. 查询相关记忆
    print("\n🔍 步骤2: 检索相关记忆...")
    question = "艾伦在诺斯领做了哪些事情？"
    
    # 调用 SimpleMem 检索
    contexts = adapter.memory_system.hybrid_retriever.retrieve(question)
    
    print(f"\n  找到 {len(contexts)} 条相关记忆：")
    for i, entry in enumerate(contexts[:5], 1):
        print(f"  {i}. {entry.lossless_restatement[:100]}...")
    
    # 3. 格式化为 prompt 上下文
    print("\n📝 步骤3: 构建上下文字符串...")
    context_text = "\n".join([
        f"- {entry.lossless_restatement}" 
        for entry in contexts[:10]
    ])
    
    print(f"\n上下文内容（前300字）：\n{context_text[:300]}...\n")
    
    # 4. 构建完整 Prompt
    print("\n🔨 步骤4: 构建完整 Prompt...")
    prompt = f"""请根据以下故事记忆回答问题。

## 故事记忆（SimpleMem 提取）
{context_text}

## 问题
{question}

请基于上述记忆，用简洁的语言回答问题。
"""
    
    print(f"Prompt 总长度: {len(prompt)} 字符")
    
    # 5. 调用 DeepSeek API
    print("\n🚀 步骤5: 调用 DeepSeek API...")
    client = OpenAI(
        api_key=API_KEY,
        base_url="https://api.deepseek.com"
    )
    
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {
                "role": "system",
                "content": "你是一个故事助手，根据提供的记忆回答问题。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.7,
        max_tokens=500
    )
    
    answer = response.choices[0].message.content
    
    # 6. 输出结果
    print("\n✅ 步骤6: 获得回答")
    print("=" * 60)
    print(answer)
    print("=" * 60)
    
    return answer


def example_2_write_chapter_with_memory():
    """
    示例2: 实际写作场景 - 使用记忆生成新章节
    """
    print("\n\n" + "=" * 60)
    print("示例2: 使用记忆系统写作新章节")
    print("=" * 60)
    
    # 1. 初始化
    print("\n📖 步骤1: 初始化记忆系统...")
    adapter = StoryMemoryAdapter(clear_db=False)
    
    # 假设要写第 61 章
    chapter_num = 61
    
    # 2. 构建多维度记忆上下文
    print(f"\n🧠 步骤2: 为第{chapter_num}章构建记忆上下文...")
    
    # 2.1 前文摘要
    print("  - 检索前文事件...")
    prev_events = adapter.memory_system.hybrid_retriever.retrieve(
        f"第{chapter_num-1}章到第{chapter_num}章之前发生的重要事件"
    )
    prev_summary = "\n".join([
        f"- {e.lossless_restatement}" for e in prev_events[:8]
    ])
    
    # 2.2 主角状态
    print("  - 检索主角状态...")
    char_status = adapter.memory_system.hybrid_retriever.retrieve(
        "艾伦当前的境界、位置、能力和状态"
    )
    char_summary = "\n".join([
        f"- {e.lossless_restatement}" for e in char_status[:5]
    ])
    
    # 2.3 特定主题
    print("  - 检索主题背景...")
    topics = ["领地建设", "外部威胁", "系统任务"]
    topic_contexts = {}
    
    for topic in topics:
        results = adapter.memory_system.hybrid_retriever.retrieve(topic)
        topic_contexts[topic] = "\n".join([
            f"- {e.lossless_restatement}" for e in results[:3]
        ])
    
    # 3. 组装完整上下文
    print("\n📝 步骤3: 组装完整写作上下文...")
    full_context = f"""## 前文关键事件
{prev_summary}

## 主角当前状态
{char_summary}

## 相关主题背景

### 领地建设
{topic_contexts['领地建设']}

### 外部威胁
{topic_contexts['外部威胁']}

### 系统任务
{topic_contexts['系统任务']}
"""
    
    print(f"\n上下文总长度: {len(full_context)} 字符")
    print(f"\n上下文预览（前500字）：\n{full_context[:500]}...\n")
    
    # 4. 构建写作 Prompt
    print("\n🔨 步骤4: 构建写作 Prompt...")
    
    chapter_outline = f"""# 第{chapter_num}章：第一艘船

## 基本信息
- 字数目标：5000字
- POV：主角第三人称
- 时间：春季，融雪后第一周
- 地点：诺斯领、诺斯河畔

## 本章目的
- [ ] 展示领地经济发展（从农业到贸易）
- [ ] 引入水路贸易线
- [ ] 为后续商路冲突埋下伏笔

## 场景安排

### 场景1：春耕总结（约1500字）
**内容**：
- 艾伦视察丰收的冬小麦田
- 塞巴斯汇报粮食储备翻倍
- 村民感激，领地氛围改善
**氛围**：欣欣向荣，成就感

### 场景2：河运构想（约2000字）
**内容**：
- 格雷提出贸易难题（陆路不便）
- 艾伦提出建造河船和码头
- 商人马库斯表示支持
**氛围**：务实规划，商业思维

### 场景3：动工准备（约1500字）
**内容**：
- 选址码头位置
- 调集木工和人力
- 系统发布新任务
**氛围**：干劲十足
"""
    
    writing_prompt = f"""你是专业网络小说写手。请根据以下信息写作章节。

## 故事状态与记忆（SimpleMem 系统提供）
{full_context}

## 章纲
{chapter_outline}

## 写作要求
1. 字数：5000字以上
2. POV：主角第三人称视角
3. 风格：流畅自然的网文风格，对话和描写穿插
4. 节奏：张弛有度，不要太赶
5. 细节：环境和心理描写适当
6. 不要：章节标题、作者备注、元叙述

请直接输出章节正文内容，开头直接进入场景。
"""
    
    print(f"完整 Prompt 长度: {len(writing_prompt)} 字符")
    
    # 5. 调用 API（实际写作）
    print("\n🚀 步骤5: 调用 DeepSeek API 生成章节...")
    print("（演示模式：实际调用已注释，避免消耗 tokens）")
    
    # 实际使用时取消注释：
    """
    client = OpenAI(api_key=API_KEY, base_url="https://api.deepseek.com")
    
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {
                "role": "system",
                "content": "你是顶级网络小说写手，擅长西幻种田流。每章至少5000字。"
            },
            {
                "role": "user",
                "content": writing_prompt
            }
        ],
        temperature=0.85,
        max_tokens=8000
    )
    
    chapter_content = response.choices[0].message.content
    
    # 保存章节
    with open(f"第{chapter_num}章_第一艘船.txt", 'w', encoding='utf-8') as f:
        f.write(chapter_content)
    
    print(f"✅ 章节生成完成，字数：{len(chapter_content)}")
    """
    
    print("\n✅ 演示完成！实际使用时取消注释即可生成章节。")


def example_3_batch_multi_chapters():
    """
    示例3: 批量处理多章节
    """
    print("\n\n" + "=" * 60)
    print("示例3: 批量写作多章节（61-65章）")
    print("=" * 60)
    
    adapter = StoryMemoryAdapter(clear_db=False)
    
    chapters_to_write = [61, 62, 63, 64, 65]
    
    print(f"\n📚 计划写作：{chapters_to_write}")
    
    for chapter_num in chapters_to_write:
        print(f"\n{'='*40}")
        print(f"处理第 {chapter_num} 章")
        print('='*40)
        
        # 1. 生成上下文
        print(f"  🧠 检索记忆...")
        context = adapter.get_writing_context(
            chapter_num=chapter_num,
            topics=["领地发展", "角色关系"]
        )
        
        print(f"  上下文长度: {len(context)} 字符")
        
        # 2. 构建 Prompt（简化版）
        prompt = f"""根据以下记忆写作第{chapter_num}章。

{context[:1000]}

请生成约5000字的章节内容。
"""
        
        # 3. 调用 API（演示模式）
        print(f"  🚀 调用 API（演示模式，跳过）")
        
        # 实际调用：
        # response = client.chat.completions.create(...)
        # content = response.choices[0].message.content
        
        # 4. 写入记忆（重要！）
        print(f"  💾 将新章节加入记忆库（跳过）")
        
        # 实际操作：
        # adapter.add_chapter(chapter_num, content, title=f"第{chapter_num}章")
        
        print(f"  ✅ 第{chapter_num}章完成")
    
    print(f"\n✅ 批量写作演示完成！")
    print(f"实际使用时，每章写完后立即调用 add_chapter() 更新记忆。")


def main():
    """
    主函数：运行所有示例
    """
    print("\n" + "="*60)
    print("SimpleMem 记忆→API 完整示例")
    print("="*60)
    print("\n本脚本演示三个场景：")
    print("1. 基础记忆检索与问答")
    print("2. 使用记忆写作单章")
    print("3. 批量写作多章节")
    print("\n请选择要运行的示例（输入数字 1-3，或 0 运行全部）：")
    
    choice = input("> ")
    
    if choice == "1" or choice == "0":
        example_1_basic_memory_to_prompt()
    
    if choice == "2" or choice == "0":
        example_2_write_chapter_with_memory()
    
    if choice == "3" or choice == "0":
        example_3_batch_multi_chapters()
    
    print("\n" + "="*60)
    print("示例运行完成！")
    print("="*60)


if __name__ == "__main__":
    main()
