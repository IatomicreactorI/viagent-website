#!/usr/bin/env python3
"""
Viagent 分析流水线集成脚本

当有实际视频文件时，调用 Viagent 的分析流水线对爬取的视频进行真伪检测，
并将结果写入 website/data/results.json 供前端展示。

用法:
    # 在 src/ 目录下运行
    cd src
    python ../website/analyze_videos.py [--config config.yaml] [--limit 10]

注意: 需要先配置好 .env 中的 LLM API Key 和相关环境变量。
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# 确保 src 在 Python 路径中
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

WEBSITE_DIR = Path(__file__).resolve().parent
DATA_DIR = WEBSITE_DIR / "data"
RESULTS_FILE = DATA_DIR / "results.json"


def load_existing_results() -> dict:
    """加载已有的结果文件"""
    if RESULTS_FILE.exists():
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"generated_at": None, "total": 0, "items": []}


def analyze_with_viagent(video_path: str, config_path: str = None) -> dict:
    """
    调用 Viagent 流水线分析单个视频。
    返回分析结果字典。
    """
    try:
        from pipeline.analyze import analyze_video
        from util.config import load_config

        config = load_config(config_path)
        result = analyze_video(video_path, config=config)
        return result
    except ImportError as e:
        print(f"  ⚠ 无法导入 Viagent 模块: {e}")
        print("  请确保在 src/ 目录下运行此脚本")
        return None
    except Exception as e:
        print(f"  ⚠ 分析失败: {e}")
        return None


def format_viagent_result(raw_result: dict, news_item: dict) -> dict:
    """将 Viagent 原始分析结果格式化为前端展示格式"""
    if not raw_result:
        return None

    verdict = raw_result.get("verdict", {})
    results = raw_result.get("results", {})

    agents = {}
    for agent_name, agent_result in results.items():
        if agent_name in ("human_eyes", "judge", "planner"):
            continue
        agents[agent_name] = {
            "status": agent_result.get("status", "ok"),
            "score_fake": round(agent_result.get("score_fake", 0.5), 3),
            "confidence": round(agent_result.get("confidence", 0.5), 3),
        }

    return {
        "id": raw_result.get("run_id", ""),
        "title": news_item.get("title", "未知标题"),
        "source": news_item.get("source", ""),
        "source_url": news_item.get("source_url", ""),
        "description": news_item.get("description", ""),
        "pub_date": news_item.get("pub_date", ""),
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "verdict": {
            "label": verdict.get("label", "uncertain"),
            "score_fake": round(verdict.get("score_fake", 0.5), 3),
            "confidence": round(verdict.get("confidence", 0.5), 3),
        },
        "agents": agents,
        "thumbnail": None,
    }


def main():
    parser = argparse.ArgumentParser(description="使用 Viagent 分析视频并更新网站数据")
    parser.add_argument("--config", type=str, default=None, help="Viagent 配置文件路径")
    parser.add_argument("--video-dir", type=str, default=None, help="视频目录")
    parser.add_argument("--limit", type=int, default=10, help="最多分析数量")
    args = parser.parse_args()

    print("🔬 Viagent 视频分析集成")
    print("=" * 50)

    # 查找待分析的视频
    video_dir = Path(args.video_dir) if args.video_dir else DATA_DIR / "videos"
    if not video_dir.exists():
        print(f"⚠ 视频目录不存在: {video_dir}")
        print("请先运行 crawler.py 下载视频，或指定 --video-dir")
        return

    video_exts = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv"}
    videos = [f for f in video_dir.iterdir() if f.suffix.lower() in video_exts]
    videos = videos[: args.limit]

    if not videos:
        print(f"⚠ 在 {video_dir} 中未找到视频文件")
        return

    print(f"📹 找到 {len(videos)} 个视频待分析\n")

    # 分析每个视频
    existing = load_existing_results()
    analyzed_ids = {item["id"] for item in existing.get("items", [])}

    for i, vpath in enumerate(videos, 1):
        print(f"[{i}/{len(videos)}] 🎬 分析: {vpath.name}")
        result = analyze_with_viagent(str(vpath), args.config)

        if result:
            formatted = format_viagent_result(result, {
                "title": vpath.stem.replace("_", " ").replace("-", " "),
                "source": "local",
                "description": f"本地视频文件分析: {vpath.name}",
            })
            if formatted and formatted["id"] not in analyzed_ids:
                existing["items"].append(formatted)
                analyzed_ids.add(formatted["id"])
                print(f"  ✅ {formatted['verdict']['label']} "
                      f"(score={formatted['verdict']['score_fake']:.2f})")
        else:
            print(f"  ❌ 分析失败")

    # 保存结果
    existing["generated_at"] = datetime.now(timezone.utc).isoformat()
    existing["total"] = len(existing["items"])

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

    print(f"\n✅ 分析完成，共 {existing['total']} 条记录 → {RESULTS_FILE}")


if __name__ == "__main__":
    main()
