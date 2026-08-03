# 知识库导入

知识压缩包已完成一次盘点和导入。现有结果：

- 盘点 1798 个条目；
- 1796 个页面资源、脚本、图片和运行资产被排除；
- 1 个知识页成功提取原始文档正文；
- 1 个知识页因没有“预览原始文档”正文而跳过；
- 导入内容保持 `verified: false`。

## 1. 只读盘点

```powershell
$archive = 'D:\APP\Dev\imports\coze.zip'
& D:\APP\Dev\Python\envs\yicheng-agent\Scripts\python.exe `
  -m scripts.import_knowledge --zip $archive
```

检查 `docs/reference/knowledge_inventory.json`，确认分类结果。

## 2. 导入

```powershell
$archive = 'D:\APP\Dev\imports\coze.zip'
& D:\APP\Dev\Python\envs\yicheng-agent\Scripts\python.exe `
  -m scripts.import_knowledge --zip $archive --apply
```

默认支持 Markdown、TXT、JSON、CSV、HTML、PDF、DOCX、PPTX 和 XLSX。
平台 Prompt、工作流和插件元数据会被排除。默认只导入路径被识别为
知识库的文件。盘点后确认其他普通文档也属于正式知识时，显式增加：

```powershell
$archive = 'D:\APP\Dev\imports\coze.zip'
& D:\APP\Dev\Python\envs\yicheng-agent\Scripts\python.exe `
  -m scripts.import_knowledge `
  --zip $archive `
  --apply `
  --include-documents
```

保存网页只有在能从“预览原始文档”区域提取正文时才会导入。不要仅因
文件格式是 PDF、Word 或 PPT 就导入；答辩材料和方案稿会污染检索结果。
所有导入文档标记
`verified: false`，核对来源和更新时间后才能作为正式校园事实。

导入后重新启动服务，使本地检索重新加载文档。
