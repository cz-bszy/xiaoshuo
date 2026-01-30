---
description: 小说写作自动化工作流 - 用于生成和管理西幻小说章节
---

# 小说写作工作流

以下是小说写作的常用操作，带有 `// turbo` 标记的步骤会自动执行。

## 安全操作（自动执行）

// turbo
1. 检查Git状态
```powershell
git status
```

// turbo
2. 检查写作进度
```powershell
python check_progress.py
```

// turbo
3. 查看章节列表
```powershell
Get-ChildItem chapters/v01 | Sort-Object Name
```

// turbo
4. 运行测试脚本（只读操作）
```powershell
python -c "print('测试通过')"
```

## 需要确认的操作

5. 运行自动写作脚本
```powershell
python auto_write.py
```

6. 提交更改到Git
```powershell
git add -A
git commit -m "更新章节内容"
```

7. 推送到GitHub
```powershell
git push origin main
```

8. 清理临时文件
```powershell
Remove-Item -Recurse -Force __pycache__
```

## 使用说明

- 输入 `/write-novel` 可以触发此工作流
- 安全操作（如查看状态、检查进度）会自动执行
- 涉及写入、删除、网络操作的命令需要手动确认
