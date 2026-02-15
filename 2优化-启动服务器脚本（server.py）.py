#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import http.server
import socketserver
import socket
import webbrowser
import os
import sys
import re
from urllib.parse import urlparse

# 尝试导入 requests，若失败则给出友好提示
try:
    import requests
except ImportError:
    print("错误：缺少 requests 库，请运行以下命令安装：")
    print("    pip install requests")
    input("按 Enter 键退出...")
    sys.exit(1)

PORT = 8090
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

# 内网流媒体服务器地址（请根据实际情况修改）
STREAM_SERVER = "192.168.6.200:8088"


class ProxyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """自定义请求处理器，支持静态文件服务和直播流代理"""

    def __init__(self, *args, **kwargs):
        # 指定静态文件目录
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def end_headers(self):
        # 添加跨域及缓存控制头
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        # 代理直播流请求（路径以 /livelan/ 开头）
        if self.path.startswith('/livelan/'):
            self.proxy_request()
        else:
            # 普通文件请求，默认返回 index.html
            if self.path == '/':
                self.path = '/index.html'
            return super().do_GET()

    def proxy_request(self):
        """将请求转发到内网流媒体服务器，并重写 M3U8 内容中的地址"""
        try:
            # 构造目标 URL
            target_url = f"http://{STREAM_SERVER}{self.path}"
            print(f"[代理] {target_url}")

            # 转发请求
            resp = requests.get(target_url, stream=True, timeout=10)
            self.send_response(resp.status_code)

            # 复制响应头（过滤掉可能导致问题的头）
            excluded_headers = ('transfer-encoding', 'content-encoding', 'content-length')
            for key, value in resp.headers.items():
                if key.lower() not in excluded_headers:
                    self.send_header(key, value)

            # 处理 M3U8 文件：重写内部地址
            if self.path.endswith('.m3u8'):
                content = resp.text

                # 更通用的替换：将内网服务器的绝对路径替换为代理的相对路径
                # 匹配 http://192.168.6.200:8088/livelan/xxx 或 https://... 等形式
                content = re.sub(
                    r'https?://' + re.escape(STREAM_SERVER) + r'(/livelan/)?',
                    '/livelan/',
                    content
                )

                # 重新计算长度并发送
                encoded_content = content.encode('utf-8')
                self.send_header('Content-Length', str(len(encoded_content)))
                self.end_headers()
                self.wfile.write(encoded_content)
                print(f"[代理] 已重写 M3U8 文件，长度 {len(encoded_content)} 字节")
            else:
                # 非 M3U8 文件（如 TS 片段），直接流式转发
                self.end_headers()
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        self.wfile.write(chunk)
        except requests.exceptions.Timeout:
            print("[错误] 代理请求超时")
            self.send_error(504, "Gateway Timeout")
        except requests.exceptions.ConnectionError:
            print("[错误] 无法连接到内网流媒体服务器")
            self.send_error(502, "Bad Gateway: Cannot connect to stream server")
        except Exception as e:
            print(f"[错误] 代理异常: {e}")
            self.send_error(502, f"Bad Gateway: {e}")


def get_local_ip():
    """获取本机内网 IP 地址"""
    try:
        # 创建一个 UDP 套接字（不需要真正连接）
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main():
    """主函数：启动 HTTP 服务器"""
    # 检查静态文件目录下是否存在 index.html（可选）
    index_path = os.path.join(DIRECTORY, "index.html")
    if not os.path.isfile(index_path):
        print("提示：当前目录下未找到 index.html，访问根路径可能返回 404。")

    handler = ProxyHTTPRequestHandler

    # 尝试绑定端口，若被占用则提示并退出
    try:
        httpd = socketserver.TCPServer(("", PORT), handler)
    except OSError as e:
        if e.winerror == 10048:  # Windows 下端口被占用错误码
            print(f"错误：端口 {PORT} 已被占用，请关闭占用程序或修改 PORT 变量。")
        else:
            print(f"错误：无法启动服务器 - {e}")
        input("按 Enter 键退出...")
        sys.exit(1)

    # 获取本机 IP 并显示访问地址
    local_ip = get_local_ip()
    print("\n" + "="*50)
    print(f"服务器已启动！")
    print(f"本地访问地址： http://localhost:{PORT}")
    print(f"局域网访问地址： http://{local_ip}:{PORT}")
    print("="*50)
    print("按 Ctrl+C 停止服务器\n")

    # 尝试自动打开浏览器
    try:
        webbrowser.open(f"http://localhost:{PORT}")
    except Exception:
        pass  # 忽略打开浏览器失败

    # 开始服务循环
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n收到停止信号，正在关闭服务器...")
    finally:
        httpd.shutdown()
        httpd.server_close()
        print("服务器已停止。")


if __name__ == '__main__':
    main()