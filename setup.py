'''
llama_cpp_binaries 휠 빌드 로직 (선행 검토: MY-Little-Jarvis-Plus의 poc/jarvis-cpp-binaries 레시피)
빌드 흐름: CMake configure → llama-server 컴파일 → 산출물+CUDA 런타임 DLL을 패키지 bin/에 복사 → py3-none 휠 태그 강제
직접 실행하지 말고 build_llama_wheel.py 사용 — 소스 클론/환경변수 주입/산출 검증을 대신 수행한다
'''
import os
import shutil
import subprocess
from pathlib import Path

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext

try:
    from setuptools.command.bdist_wheel import bdist_wheel
except ImportError:
    from wheel.bdist_wheel import bdist_wheel

BASE_VERSION = os.environ.get('LLAMA_WHEEL_VERSION', '0.0.0')  # 휠 버전 — 오케스트레이터가 llama.cpp b태그 숫자를 주입 (예: 10423)
VERSION_SUFFIX = os.environ.get('VERSION_SUFFIX', '')          # 로컬 버전 태그 = CUDA 변형 (예: +cu128)


'''
소스 없는 더미 Extension — 이게 있어야 setuptools가 build_ext를 호출하고,
휠을 "순수 파이썬 아님(플랫폼 종속)"으로 취급한다
'''
class CMakeExtension(Extension):
    def __init__(self, name):
        super().__init__(name, sources=[])


'''
build_ext 가로채기: 원래 C확장을 컴파일하는 단계에서 대신 CMake를 실행
'''
class CMakeBuild(build_ext):
    def run(self):
        root_dir = Path(__file__).parent.resolve()                                        # 저장소 루트
        source_dir = Path(os.environ.get('LLAMA_CPP_SRC') or root_dir / 'work' / 'llama.cpp')  # llama.cpp 원본 (오케스트레이터가 클론)
        build_dir = Path(os.environ.get('LLAMA_CPP_BUILD') or root_dir / 'work' / 'build')     # CMake 작업 폴더

        # 소스가 없으면 즉시 안내 (클론은 오케스트레이터 담당)
        if not (source_dir / 'CMakeLists.txt').exists():
            raise RuntimeError(f'llama.cpp 소스가 없습니다: {source_dir} — build_llama_wheel.py로 실행하세요')

        # CMake 인자: 기본값 + 환경변수 CMAKE_ARGS 병합
        cmake_args = [
            '-DCMAKE_BUILD_TYPE=Release',
            '-DLLAMA_BUILD_SERVER=ON',       # 우리가 원하는 것
            '-DLLAMA_BUILD_TESTS=OFF',       # 불필요한 것들 제외 → 빌드 단축
            '-DLLAMA_BUILD_EXAMPLES=OFF',
            '-DGGML_NATIVE=OFF',             # 빌드 머신 CPU 과최적화 방지 (배포 빌드 필수)
            '-DGGML_BACKEND_DL=ON',          # 백엔드 동적 로딩 — CUDA 사용 불가 환경에서 CPU로 완전 폴백 (oobabooga/공식 배포 빌드와 동일 정책)
            '-DGGML_CPU_ALL_VARIANTS=ON',    # CPU 세대별(sandybridge~alderlake 등) 커널 DLL 전부 생성 → 런타임에 최적 변형 자동 선택
            '-DLLAMA_OPENSSL=OFF',           # 모델 URL(HTTPS) 다운로드 기능 미사용 — OpenSSL 의존 차단 (본체는 로컬 경로만 전달)
                                             # 상류가 LLAMA_CURL 을 폐기하고 LLAMA_OPENSSL(기본 ON)로 대체했다.
                                             # 옛 이름은 값이 ON 일 때만 폐기 경고가 떠서, OFF 로 주면 조용히 무시된다
                                             # (b10423 휠이 libssl-3-x64.dll 없이 배포된 원인 — 2026-08-22)
        ]
        if os.environ.get('CMAKE_ARGS'):
            cmake_args += [arg for arg in os.environ['CMAKE_ARGS'].split(' ') if arg]

        # ① configure(컴파일러 탐지+계획) → ② build(전체 빌드 — BACKEND_DL의 CPU 변형 DLL들이
        # 별도 타겟이라 llama-server 단일 타겟 빌드로는 변형 DLL이 안 만들어진다)
        subprocess.run(['cmake', '-S', str(source_dir), '-B', str(build_dir)] + cmake_args, check=True)
        subprocess.run([
            'cmake', '--build', str(build_dir), '--config', 'Release',
            '-j', str(os.cpu_count() or 4),
        ], check=True)

        # 산출물 위치 (VS 제너레이터: build/bin/Release, Ninja: build/bin)
        bin_dir = None
        for candidate in [build_dir / 'bin' / 'Release', build_dir / 'bin']:
            if list(candidate.glob('llama-server*')):
                bin_dir = candidate
                break
        if bin_dir is None:
            raise RuntimeError('llama-server 산출물을 찾지 못했습니다')

        # CUDA 런타임 DLL 수집 — exe가 동적 링크하는 3종.
        # 빌드 PC엔 CUDA 툴킷이 있어 돌지만 사용자 PC엔 없으므로 휠에 동봉해야 함
        bundle_files = []
        if os.environ.get('BUNDLE_CUDA') == '1':
            cuda_bin = Path(os.environ['CUDA_PATH']) / 'bin'
            for pattern in ['cudart64_*.dll', 'cublas64_*.dll', 'cublasLt64_*.dll']:
                bundle_files += list(cuda_bin.glob(pattern))
            if not bundle_files:
                raise RuntimeError('CUDA_PATH에서 런타임 DLL을 찾지 못했습니다: ' + str(cuda_bin))

        # 패키지 bin/으로 복사. build_lib에도 복사하는 이유: setuptools는
        # build_py(패키지 파일 수집)가 build_ext보다 먼저 돌아서, 소스 폴더에만
        # 복사하면 휠에 안 들어간다
        for dest_root in [root_dir, Path(self.build_lib)]:
            dest_dir = dest_root / 'llama_cpp_binaries' / 'bin'
            if dest_dir.exists():
                shutil.rmtree(dest_dir)
            dest_dir.mkdir(parents=True)
            # 전체 빌드 산출물 중 서버 exe + DLL만 선별 (llama-cli 등 부속 도구는 휠에서 제외)
            for item in sorted(bin_dir.iterdir()):
                if item.is_file() and (item.name.startswith('llama-server') or item.suffix.lower() == '.dll'):
                    shutil.copy2(item, dest_dir / item.name)
            for item in bundle_files:
                shutil.copy2(item, dest_dir / item.name)


'''
휠 태그를 py3-none-<플랫폼>으로 강제. 안 하면 빌드에 쓴 파이썬 버전(cp310 등)이
박혀서 다른 파이썬에 설치 불가
'''
class BinaryWheel(bdist_wheel):
    def get_tag(self):
        python_tag, abi_tag, platform_tag = super().get_tag()
        return ('py3', 'none', platform_tag)


setup(
    version=BASE_VERSION + VERSION_SUFFIX,
    ext_modules=[CMakeExtension('llama_cpp_binaries')],
    cmdclass={'build_ext': CMakeBuild, 'bdist_wheel': BinaryWheel},
)
