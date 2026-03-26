# Viagent Website — 视频真伪检测结果展示

展示 Viagent 多智能体分析流水线的检测结果。

## 工作流程

```
data/        ← 1. 放入待检测视频（.mp4）
   ├── Real/
   ├── Fake/
   └── Unknown/
     ↓
cd src && python main.py --label all   ← 2. 运行分析
     ↓
python sync_to_web.py                  ← 3. 同步到网页
     ↓
python website/serve.py                ← 4. 本地预览 (localhost:8080)
```

## 快速开始

```bash
# 1. 把视频放入 data/ 目录（支持子目录分类）
#    data/Real/video1.mp4
#    data/Fake/generated_video.mp4
#    data/Unknown/suspicious.mp4

# 2. 运行 Viagent 分析（需要先配置 .env 中的 API Key）
cd src
python main.py --label all

# 3. 同步结果到网页
cd ..
python sync_to_web.py

# 4. 本地预览
python website/serve.py
# 打开 http://localhost:8080
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `index.html` | 主页面（纯静态 HTML/CSS/JS） |
| `serve.py` | 本地预览 HTTP 服务器 |
| `data/results.json` | 分析结果数据（由 sync_to_web.py 生成） |
| `thumbs/` | 视频缩略图（由 sync_to_web.py 提取） |

## sync_to_web.py 参数

```bash
python sync_to_web.py                  # 默认：生成缩略图
python sync_to_web.py --no-thumbs      # 不生成缩略图
python sync_to_web.py --thumb-size 320x180  # 自定义缩略图尺寸
```

## 数据格式

`data/results.json` 由 `sync_to_web.py` 从 SQLite 数据库自动生成，包含：

- 每个视频的最终判定（`verdict.label`: real/fake/uncertain）
- 各智能体评分（style, physics, spatial, temporal, watermark）
- 证据详情（evidence）
- 判定依据（rationale）
