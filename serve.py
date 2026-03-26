#!/usr/bin/env python3
"""
本地开发服务器 — 启动一个简单的 HTTP 服务器来预览网站

用法:
    python website/serve.py [--port 8080]
"""
import argparse
import http.server
import os
import functools


def main():
    parser = argparse.ArgumentParser(description="启动本地预览服务器")
    parser.add_argument("--port", type=int, default=8080, help="端口号 (默认 8080)")
    args = parser.parse_args()

    web_dir = os.path.dirname(os.path.abspath(__file__))
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=web_dir)

    with http.server.HTTPServer(("", args.port), handler) as httpd:
        print(f"🌐 Viagent 网站服务已启动")
        print(f"   地址: http://localhost:{args.port}")
        print(f"   目录: {web_dir}")
        print(f"   按 Ctrl+C 停止\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n👋 服务已停止")


if __name__ == "__main__":
    main()
