#!/usr/bin/env python3
"""
웹 파노라마 뷰어 서버 실행 스크립트

로컬 HTTP 서버를 시작하여 브라우저에서 360도 파노라마 투어를 확인합니다.

사용법:
  python3 05_web_viewer.py --data_dir ../output --port 8080
"""

import argparse
import http.server
import os
import socketserver
import threading
import webbrowser

class CORSHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """CORS 헤더를 포함한 HTTP 핸들러"""
    
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()
    
    def log_message(self, format, *args):
        # 로그 간소화
        if '200' in str(args):
            pass  # 성공 요청은 숨김
        else:
            super().log_message(format, *args)

def start_server(data_dir, port=8080):
    """HTTP 서버 시작"""
    web_dir = os.path.join(data_dir, 'web')
    os.chdir(web_dir)
    
    handler = CORSHTTPRequestHandler
    
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"\n{'='*60}")
        print(f"  360° Panorama Virtual Tour Viewer")
        print(f"{'='*60}")
        print(f"  Server: http://localhost:{port}")
        print(f"  Data:   {data_dir}")
        print(f"\n  브라우저에서 http://localhost:{port} 를 열어주세요")
        print(f"  종료: Ctrl+C")
        print(f"{'='*60}\n")
        
        # 브라우저 자동 열기
        threading.Timer(1.0, lambda: webbrowser.open(f'http://localhost:{port}')).start()
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[INFO] Server stopped")

def main():
    parser = argparse.ArgumentParser(description='Start panorama tour web viewer')
    parser.add_argument('--data_dir', '-d', default='../output', help='Data directory')
    parser.add_argument('--port', '-p', type=int, default=8080, help='HTTP server port')
    args = parser.parse_args()
    
    data_dir = os.path.abspath(args.data_dir)
    
    if not os.path.exists(os.path.join(data_dir, 'web', 'index.html')):
        print(f"[ERROR] Web viewer not found at {data_dir}/web/index.html")
        print("[INFO] Run the pipeline first:")
        print("  python3 01_extract_from_msg.py --input robot_map.msg --output_dir output")
        return
    
    start_server(data_dir, args.port)

if __name__ == '__main__':
    main()
