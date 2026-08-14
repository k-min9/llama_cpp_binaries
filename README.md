# llama_cpp_binaries

[ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp)의 `llama-server`를 빌드해 파이썬 휠로 배포하는 저장소 (Windows x64).

## 설치

```
pip install https://github.com/k-min9/llama_cpp_binaries/releases/download/b10423/llama_cpp_binaries-10423+cu128-py3-none-win_amd64.whl
```

## 사용

```python
import llama_cpp_binaries

exe = llama_cpp_binaries.get_binary_path()  # llama-server.exe 절대경로
```

exe를 subprocess로 기동하고 HTTP(`/completion`, `/health` 등 llama-server 표준 API)로 통신한다.
oobabooga/llama-cpp-binaries와 패키지명·인터페이스가 동일해 서로 교체 설치할 수 있다.

## 휠 사양

- 휠 태그 `py3-none-win_amd64` — 내용물이 exe+DLL뿐(libpython 링크 없음)이라 파이썬 3.9+ 어디에나 설치된다
- 휠 버전 = llama.cpp 릴리스 태그의 빌드 번호 (`b10423` → `10423`). CUDA 변형은 로컬 태그(`+cu128` / `+cpu`)
- CUDA 런타임 DLL(cudart/cublas/cublasLt) 동봉 — 사용자 PC에 CUDA Toolkit 설치 불필요
- GPU/드라이버가 없으면 CPU 백엔드로 폴백 — `GGML_BACKEND_DL` + CPU 세대별 커널 DLL 동봉, `GGML_NATIVE=off`
- CUDA 아키텍처: `61;70;75;80;86;89;120` (Pascal~RTX50)

## 새 버전 릴리스 (GitHub Actions)

1. Actions → `build-llama-wheel` → **Run workflow** — tag를 비우면 llama.cpp 최신 릴리스 태그를 자동 조회한다 (특정 버전 재현 시에만 `b####` 입력)
2. 러너가 빌드 → 휠 검증(설치 + import + `--version` 기동) → 같은 b태그로 Release 생성·휠 첨부. 소요 1.5~3시간
3. 릴리스 이후:
   - GPU 장비에서 새 휠 설치 후 실제 모델 추론 1회 확인 — 러너에는 GPU가 없어 이 단계만 자동 검증이 안 된다
   - 소비 프로젝트의 requirements/문서에서 휠 URL을 새 버전으로 교체

러너에는 CUDA 툴킷이 없으므로 워크플로우가 설치하며(Jimver/cuda-toolkit), GPU 없이 컴파일된다 (아키텍처는 위 고정 리스트).

## 로컬 빌드 (선택)

MSVC와 CUDA Toolkit(nvcc)이 필요하고 "x64 Native Tools Command Prompt for VS 2022"에서 실행한다.
CMake/Ninja는 pip 빌드 격리환경에 자동 조달된다 (제너레이터는 Ninja 고정).

```
python build_llama_wheel.py                    # 최신 릴리스 태그 자동 조회
python build_llama_wheel.py --tag b10423       # 태그 고정 (재현 빌드)
python build_llama_wheel.py --cuda-archs "86"  # 아키텍처 축소 (빌드 시간 단축)
python build_llama_wheel.py --cpu              # CPU 전용 휠 (CUDA 불필요)
```

산출: `dist/llama_cpp_binaries-<버전>+<변형>-py3-none-win_amd64.whl`

## 구성

| 파일 | 역할 |
|---|---|
| `build_llama_wheel.py` | 태그 결정(자동 조회/지정) → llama.cpp 클론 → `pip wheel` → 산출 휠 검증 |
| `setup.py` | CMake 빌드, 산출물+CUDA 런타임 DLL 복사, `py3-none` 휠 태그 |
| `pyproject.toml` | 패키지 메타데이터, 빌드 도구(cmake/ninja) 자동 조달 |
| `llama_cpp_binaries/__init__.py` | `get_binary_path()` |
| `.github/workflows/build_wheel.yml` | 빌드 → Release 업로드 자동화 |

## 라이선스

- llama.cpp: MIT — 바이너리는 원본 소스를 그대로 빌드한 것
- 이 저장소의 포장 코드: MIT
