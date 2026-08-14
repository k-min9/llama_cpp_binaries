'''
llama-server 실행파일 경로 제공 (자체 빌드 휠 — oobabooga 드롭인 대체, Windows 전용)
'''
import os


'''
llama-server.exe의 절대경로 반환
'''
def get_binary_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bin', 'llama-server.exe')
