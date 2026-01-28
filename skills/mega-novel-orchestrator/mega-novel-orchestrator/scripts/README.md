# Mega Novel Orchestrator 脚本集

## 安装依赖

```bash
pip install -r requirements.txt
```

## 环境配置

设置DeepSeek API密钥：

```bash
# Windows
set DEEPSEEK_API_KEY=你的API密钥

# Linux/Mac
export DEEPSEEK_API_KEY=你的API密钥
```

## 使用方法

### 1. 初始化项目

```bash
python orchestrator.py init <项目路径> <项目名称> [目标字数]

# 示例
python orchestrator.py init ./projects/my-novel "我的西幻种田小说" 4000000
```

### 2. 查看项目状态

```bash
python orchestrator.py status <项目路径>
```

### 3. 测试API连接

```bash
python api_client.py test
```

### 4. 运行写作循环

```bash
python writing_loop.py run <项目路径> [章节数]

# 示例：写5章
python writing_loop.py run ./projects/my-novel 5
```

## 工作流程

### 推荐流程

1. **初始化项目**
   ```bash
   python orchestrator.py init ./projects/my-novel "我的小说" 4000000
   ```

2. **填写设定文件**
   - 编辑 `constitution.md`（创作宪法）
   - 编辑 `specification.md`（故事规格）
   - 编辑 `outline/L0-main.md`（总纲）

3. **创建大纲**
   - 创建卷纲 `outline/L1-volumes/v01.md`
   - 创建篇纲 `outline/L2-parts/v01-p01.md`
   - 创建章纲 `outline/L3-chapters/v01-c001.md` ...

4. **初始化世界书**
   - 编辑 `worldbook/characters.json`
   - 编辑 `worldbook/locations.json`
   - 编辑 `worldbook/rules.json`

5. **开始写作**
   ```bash
   python writing_loop.py run ./projects/my-novel 5
   ```

6. **质量检查**
   - 使用监控界面（当前对话）进行质量评估
   - 根据反馈调整

## 文件说明

| 文件 | 功能 |
|------|------|
| `orchestrator.py` | 核心调度器，项目管理 |
| `api_client.py` | DeepSeek API调用 |
| `prompt_templates.py` | 提示词模板 |
| `writing_loop.py` | 自动写作循环 |

## 注意事项

1. 首次使用前请确保API密钥正确
2. 建议先写3-5章测试效果
3. 每5章建议进行一次质量检查
4. 定期备份项目文件
