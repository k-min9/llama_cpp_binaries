'''
llama.cpp 원본에서 llama-server 바이너리 휠 자체 빌드 (Windows 전용)
선행 검토: MY-Little-Jarvis-Plus의 poc/jarvis-cpp-binaries 레시피 — oobabooga 코드 미사용(클린룸), 원본 llama.cpp는 MIT
 - ggml-org/llama.cpp를 b태그로 고정 클론(work/llama.cpp) → pip wheel이 setup.py의 CMake 빌드를 호출
 - 휠 태그 py3-none-win_amd64: 내용물이 exe+DLL뿐(libpython 링크 없음)이라 빌드 파이썬 버전 무관
 - 휠 버전 = llama.cpp 상류 버전 그대로: b태그의 빌드 번호(단조 증가)를 쓴다 (b10423 → 10423).
   b#### 형식이 아닌 ref면 날짜 버전(YYYY.M.D) 폴백. CUDA 변형은 로컬 태그로 기록 (+cu128 / +cpu)
 - GPU 아키텍처는 감지하지 않고 고정 리스트로 컴파일 — GPU 없는 CI 러너에서도 동일하게 빌드 가능
 - CMake는 빌드 격리환경에 pip로 자동 조달되지만, MSVC와 CUDA Toolkit(nvcc)은 시스템에 있어야 한다

사용 (로컬 빌드 시 "x64 Native Tools Command Prompt for VS 2022"에서 — CI는 .github/workflows/build_wheel.yml):
  python build_llama_wheel.py                              # 기본 태그, CUDA, 기본 아키텍처 리스트 (1시간+)
  python build_llama_wheel.py --tag b10423                 # llama.cpp 릴리스 태그 지정 (새 모델 아키텍처 대응)
  python build_llama_wheel.py --cuda-archs "86"            # 아키텍처 축소 (빌드 시간 단축용)
  python build_llama_wheel.py --cpu                        # CPU 전용 휠 (+cpu — nvcc/CUDA 불필요)
산출: dist/llama_cpp_binaries-10423+cu128-py3-none-win_amd64.whl 형태
'''
import argparse
import datetime
import os
import re
import shutil
import stat
import subprocess
import sys
import zipfile

# 콘솔 인코딩 UTF-8 강제 — 한국어 Windows(cp949) 콘솔/파이프에서 print 크래시 방지
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))          # 저장소 루트
SRC_DIR = os.path.join(BASE_DIR, 'work', 'llama.cpp')          # llama.cpp 클론 위치 (커밋 제외)
BUILD_DIR = os.path.join(BASE_DIR, 'work', 'build')            # CMake 작업 폴더 (커밋 제외)
DIST_DIR = os.path.join(BASE_DIR, 'dist')                      # 휠 산출 폴더 (커밋 제외 — Releases 업로드)
LLAMA_REPO = 'https://github.com/ggml-org/llama.cpp'
DEFAULT_TAG = 'b10423'                                         # 2026-08-14 기준 최신 릴리스 — 새 모델 아키텍처 필요 시 상향
DEFAULT_CUDA_ARCHS = '61;70;75;80;86;89;120'                   # Pascal(GTX10)~RTX50 — 감지 없이 고정, 구형 GPU 커버 (sm_120은 CUDA 12.8+)


'''
명령 실행 래퍼 — 실행 커맨드를 로그로 남기고 실패 시 즉시 중단
'''
def run_cmd(cmd, env=None):
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, check=True, env=env)


'''
git 클론 폴더 삭제용 rmtree 에러 핸들러 — .git 내 읽기전용 파일을 해제하고 재시도
'''
def force_remove(func, path, exc_info):
    os.chmod(path, stat.S_IWRITE)
    func(path)


'''
nvcc --version에서 CUDA 버전 접미사 추출 (예: release 12.8 → cu128). nvcc 부재 시 None
'''
def detect_cuda_suffix():
    if not shutil.which('nvcc'):
        return None
    output = subprocess.run(['nvcc', '--version'], capture_output=True, text=True).stdout
    matched = re.search(r'release (\d+)\.(\d+)', output)
    if not matched:
        return None
    return f"cu{matched.group(1)}{matched.group(2)}"


'''
llama.cpp 소스 준비 — 요청 태그로 얕은 클론. 이미 같은 태그면 재사용, 다르면 새로 클론
'''
def prepare_source(tag):
    # 기존 클론의 태그 확인 (describe 실패 = 불일치로 간주하고 재클론)
    if os.path.isdir(SRC_DIR):
        current = subprocess.run(['git', '-C', SRC_DIR, 'describe', '--tags', '--exact-match'],
                                 capture_output=True, text=True).stdout.strip()
        if current == tag:
            print(f"[INFO] 기존 클론 재사용: {tag}")
            return
        print(f"[INFO] 태그 변경 감지 ({current or '불명'} → {tag}) — 재클론")
        shutil.rmtree(SRC_DIR, onerror=force_remove)
    # b태그 고정 얕은 클론 — "휠 버전 = llama.cpp 태그" 대응이 휠 파일명에 기록되어 재현 가능
    run_cmd(['git', 'clone', '--depth', '1', '--branch', tag, LLAMA_REPO, SRC_DIR])


'''
휠 내용물 검증 — llama-server.exe 존재 + CUDA 동봉 시 런타임 DLL 3종 확인, 미달 시 실패
'''
def verify_wheel(wheel_path, bundle_cuda):
    with zipfile.ZipFile(wheel_path) as whl:
        names = whl.namelist()
    bin_names = [os.path.basename(n) for n in names if n.startswith('llama_cpp_binaries/bin/')]
    print(f"[INFO] 휠 항목 {len(names)}개 / bin 파일 {len(bin_names)}개")
    missing = []
    if 'llama-server.exe' not in bin_names:
        missing.append('llama-server.exe')
    # BACKEND_DL 빌드 검증 — CPU 변형 백엔드 DLL이 있어야 GPU 불가 환경에서 폴백 가능
    if not any(n.startswith('ggml-cpu') for n in bin_names):
        missing.append('ggml-cpu*.dll (CPU 백엔드 변형)')
    if bundle_cuda:
        if not any(n.startswith('ggml-cuda') for n in bin_names):
            missing.append('ggml-cuda*.dll (CUDA 백엔드)')
        # CUDA 백엔드가 동적 링크하는 런타임 3종 — 없으면 CUDA 툴킷 없는 사용자 PC에서 GPU 사용 불가
        for prefix in ['cudart64_', 'cublas64_', 'cublasLt64_']:
            if not any(n.startswith(prefix) for n in bin_names):
                missing.append(prefix + '*.dll')
    if missing:
        print(f"[ERROR] 휠에 누락된 항목: {missing}")
        return False
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='llama-server 바이너리 자체 휠 빌드 (Windows 전용)')
    parser.add_argument('--tag', default=DEFAULT_TAG, help='llama.cpp 릴리스 태그 (b####)')
    parser.add_argument('--cuda-archs', default=DEFAULT_CUDA_ARCHS, help='CMAKE_CUDA_ARCHITECTURES (고정 리스트 — 감지 없음)')
    parser.add_argument('--cpu', action='store_true', help='CPU 전용 휠 (CUDA 미포함)')
    args = parser.parse_args()

    # 0. 사전 점검 — Windows 전용(win_amd64 산출) + git 필수 + CUDA 모드면 nvcc/CUDA_PATH 필수
    if sys.platform != 'win32':
        sys.exit('[ERROR] 이 스크립트는 Windows(win_amd64 휠) 전용입니다')
    if not shutil.which('git'):
        sys.exit('[ERROR] git이 필요합니다')
    cuda_suffix = detect_cuda_suffix()  # 예: cu128 (nvcc 부재 시 None)
    if args.cpu:
        variant = 'cpu'
    else:
        if not cuda_suffix:
            sys.exit('[ERROR] nvcc를 찾지 못했습니다 — CUDA Toolkit 설치 후 "x64 Native Tools Command Prompt"에서 실행 (CPU 휠은 --cpu)')
        if not os.environ.get('CUDA_PATH'):
            sys.exit('[ERROR] CUDA_PATH 환경변수가 없습니다 — CUDA Toolkit 설치 상태 확인')
        variant = cuda_suffix
    if not shutil.which('cl'):
        print('[WARN] cl.exe가 PATH에 없습니다 — CUDA 빌드는 "x64 Native Tools Command Prompt for VS 2022"에서 실행해야 합니다')

    # 1. llama.cpp 소스 준비 (태그 고정 클론)
    prepare_source(args.tag)

    # 2. 휠 버전 결정 — llama.cpp 상류 버전 정렬: b태그의 빌드 번호(단조 증가) 그대로, 아니면 날짜 폴백
    matched = re.match(r'^b(\d+)$', args.tag)
    if matched:
        base_version = matched.group(1)
    else:
        today = datetime.date.today()
        base_version = f"{today.year}.{today.month}.{today.day}"
    version = f"{base_version}+{variant}"  # 예: 10423+cu128 — 파일명만으로 상류 버전+CUDA 변형 식별
    print(f"[INFO] 휠 버전: {version} (llama.cpp {args.tag})")

    # 3. 빌드 환경변수 구성 — setup.py가 읽는 값들 (CMAKE_ARGS/VERSION_SUFFIX/BUNDLE_CUDA + 절대경로 주입)
    env = os.environ.copy()
    env['LLAMA_WHEEL_VERSION'] = base_version
    env['VERSION_SUFFIX'] = f"+{variant}"
    env['LLAMA_CPP_SRC'] = SRC_DIR
    env['LLAMA_CPP_BUILD'] = BUILD_DIR
    if args.cpu:
        env['BUNDLE_CUDA'] = '0'
        env['CMAKE_ARGS'] = env.get('CMAKE_ARGS', '')
    else:
        env['BUNDLE_CUDA'] = '1'
        cuda_args = f"-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES={args.cuda_archs}"
        env['CMAKE_ARGS'] = (env.get('CMAKE_ARGS', '') + ' ' + cuda_args).strip()

    # 4. 휠 빌드 — pip가 격리환경에 setuptools/cmake를 자동 조달 (pip 21.3+ 로컬 폴더 제자리 빌드 전제)
    os.makedirs(DIST_DIR, exist_ok=True)
    run_cmd([sys.executable, '-m', 'pip', 'wheel', BASE_DIR, '--no-deps', '-w', DIST_DIR], env=env)

    # 5. 산출 휠 검증
    wheel_name = f"llama_cpp_binaries-{version}-py3-none-win_amd64.whl"
    wheel_path = os.path.join(DIST_DIR, wheel_name)
    if not os.path.exists(wheel_path):
        print(f"[ERROR] 기대한 휠이 없습니다: {wheel_path}")
        sys.exit(1)
    if not verify_wheel(wheel_path, not args.cpu):
        sys.exit(1)

    size_mb = os.path.getsize(wheel_path) / 1024 / 1024
    print(f"\n[OK] {wheel_path} ({size_mb:.1f}MB)")
    print(f"     설치: pip install {wheel_name} --force-reinstall")
    print('     기동 검증: python -c "import llama_cpp_binaries; print(llama_cpp_binaries.get_binary_path())" 후 <경로> --version')
