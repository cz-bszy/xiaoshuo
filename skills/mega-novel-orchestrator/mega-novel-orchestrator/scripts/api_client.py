"""
DeepSeek API 客户端
用于调用DeepSeek模型进行小说写作
"""

import os
import json
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass


@dataclass
class WritingPrompt:
    """写作提示词"""
    system_prompt: str
    user_prompt: str
    chapter_outline: str
    context: str
    worldbook: Dict[str, Any]
    
    
class DeepSeekClient:
    """DeepSeek API客户端"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: str = "https://api.deepseek.com",
        model: str = "deepseek-chat"
    ):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("请设置DEEPSEEK_API_KEY环境变量或传入api_key参数")
            
        self.api_base = api_base.rstrip("/")
        self.model = model
        
        # 尝试导入openai库（DeepSeek兼容OpenAI接口）
        try:
            from openai import OpenAI
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=f"{self.api_base}/v1"
            )
        except ImportError:
            raise ImportError("请安装openai库：pip install openai")
    
    def generate_chapter(
        self,
        prompt: WritingPrompt,
        temperature: float = 0.8,
        max_tokens: int = 4000,
        retry_count: int = 3
    ) -> str:
        """生成章节内容"""
        
        # 构建完整的用户提示词
        full_prompt = self._build_full_prompt(prompt)
        
        for attempt in range(retry_count):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": prompt.system_prompt},
                        {"role": "user", "content": full_prompt}
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                
                content = response.choices[0].message.content
                return content.strip()
                
            except Exception as e:
                print(f"API调用失败 (尝试 {attempt + 1}/{retry_count}): {e}")
                if attempt < retry_count - 1:
                    time.sleep(2 ** attempt)  # 指数退避
                else:
                    raise
    
    def _build_full_prompt(self, prompt: WritingPrompt) -> str:
        """构建完整的用户提示词"""
        parts = []
        
        # 章节大纲
        parts.append("## 本章大纲\n")
        parts.append(prompt.chapter_outline)
        parts.append("\n")
        
        # 前文上下文
        if prompt.context:
            parts.append("## 前文摘要\n")
            parts.append(prompt.context)
            parts.append("\n")
        
        # 世界书信息
        if prompt.worldbook:
            parts.append("## 相关设定\n")
            
            # 人物信息
            if "characters" in prompt.worldbook:
                parts.append("### 本章涉及人物\n")
                for char_id, char_data in prompt.worldbook["characters"].items():
                    name = char_data.get("name", char_id)
                    personality = char_data.get("personality", {})
                    traits = personality.get("core_traits", [])
                    parts.append(f"- **{name}**：{', '.join(traits)}\n")
                parts.append("\n")
            
            # 规则提醒
            if "rules" in prompt.worldbook:
                parts.append("### 写作规则提醒\n")
                for rule_name, rule_data in prompt.worldbook["rules"].items():
                    if isinstance(rule_data, dict) and "rules" in rule_data:
                        parts.append(f"**{rule_data.get('name', rule_name)}**：")
                        for r in rule_data["rules"][:3]:  # 只取前3条
                            parts.append(f"  - {r}")
                parts.append("\n")
        
        # 写作要求
        parts.append("## 写作要求\n")
        parts.append(prompt.user_prompt)
        
        return "\n".join(parts)


def get_default_system_prompt(genre: str = "western-fantasy-farming") -> str:
    """获取默认系统提示词"""
    
    prompts = {
        "western-fantasy-farming": """你是一位专业的中文网络小说作家，擅长西方幻想种田流小说。

## 写作风格
- 语言流畅自然，避免过于书面化
- 适当使用网文技法，保持节奏感
- 注重细节描写，增强代入感
- 对话生动有个性，符合人物设定

## 类型要求（种田流）
- 注重建设过程和成果积累
- 日常描写要有目标感和发现
- 展现规划和执行的乐趣
- 人物互动真实自然

## 低魔世界
- 魔法稀少且效果有限
- 发展主要靠技术和劳动
- 避免使用强力魔法解决问题

## 输出要求
- 直接输出章节正文
- 不要输出章节标题（会单独处理）
- 不要输出写作说明或备注
- 字数控制在2500-4000字""",

        "default": """你是一位专业的中文网络小说作家。

## 写作要求
- 语言流畅自然
- 注重情节和人物
- 保持良好的节奏感

## 输出要求
- 直接输出章节正文
- 不要输出章节标题
- 字数控制在2500-4000字"""
    }
    
    return prompts.get(genre, prompts["default"])


def get_default_user_prompt(target_words: int = 3000) -> str:
    """获取默认用户提示词"""
    return f"""请根据以上大纲和设定，写作本章内容。

要求：
1. 字数约{target_words}字
2. 遵循前文的情节发展
3. 保持人物性格一致
4. 细节描写生动有趣
5. 适当设置悬念或铺垫

现在请开始写作："""


if __name__ == "__main__":
    # 测试代码
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        print("测试DeepSeek API连接...")
        
        try:
            client = DeepSeekClient()
            
            # 简单测试
            test_prompt = WritingPrompt(
                system_prompt="你是一个测试助手。",
                user_prompt="请说'API连接成功'",
                chapter_outline="",
                context="",
                worldbook={}
            )
            
            response = client.client.chat.completions.create(
                model=client.model,
                messages=[
                    {"role": "system", "content": test_prompt.system_prompt},
                    {"role": "user", "content": test_prompt.user_prompt}
                ],
                max_tokens=50
            )
            
            print(f"✅ API连接成功！")
            print(f"响应：{response.choices[0].message.content}")
            
        except Exception as e:
            print(f"❌ API连接失败：{e}")
    else:
        print("用法：python api_client.py test")
