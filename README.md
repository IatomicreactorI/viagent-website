# Viagent 网站 — AI 视频真伪检测展示平台

自动抓取最新热门 AI 视频新闻，通过 Viagent 多智能体检测引擎分析视频真伪，并在简洁直观的 Web 页面上展示结果。

## 快速开始

### 1. 生成数据（爬取新闻 + 分析）

```bash
# 从项目根目录
python website/crawler.py --limit 30
```

这会从 RSS 源抓取与 AI 视频相关的新闻报道，并生成模拟分析数据到 `website/data/results.json`。

> 如果无法联网，爬虫会自动使用内置的示例新闻数据。

### 2. 启动本地预览

```bash
python website/serve.py --port 8080
```

浏览器访问 `http://localhost:8080` 即可查看。

### 3. （可选）接入 Viagent 真实分析

如果有实际视频文件需要分析：

```bash
# 1. 确保 .env 已配置 LLM API Key
# 2. 将视频放入 website/data/videos/
# 3. 在 src 目录下运行分析
cd src
python ../website/analyze_videos.py --config config.yaml --limit 10
```

## 文件结构

```
website/
├── index.html          # 主页面（自包含 HTML/CSS/JS）
├── crawler.py          # 新闻爬虫与数据生成
├── analyze_videos.py   # Viagent 分析流水线集成
├── serve.py            # 本地开发服务器
├── README.md           # 本文件
└── data/
    ├── results.json    # 分析结果数据（自动生成）
    ├── meta/           # 爬虫元数据
    └── videos/         # 视频文件（可选）
```

## 部署

这是一个纯静态网站，可以部署到任何静态托管服务：

- **GitHub Pages**: 直接把 `website/` 目录部署即可
- **Vercel / Netlify**: 配置根目录为 `website/`
- **任意 HTTP 服务器**: 将所有文件放到 web 目录

只需确保 `data/results.json` 存在即可正常展示。

## 检测维度说明

| 维度 | 图标 | 说明 |
|------|------|------|
| Style | 🎨 | FFT 频谱分析检测 AI 纹理特征和渲染风格异常 |
| Physics | ⚡ | 光流分析检测运动一致性、重力违反等物理错误 |
| Spatial | 🔲 | ELA 误差分析、边缘一致性、人脸崩塌检测 |
| Temporal | 🕐 | 局部相位相干性和特征点追踪检测帧间异常 |
| Watermark | 💧 | 检测 AI 工具生成器水印 (Sora/Runway/Pika) |
