# EIDOS-2.5-Lite
이것은 EIDOS AGI 프로젝트의 'Lite' 버전입니다.
이 버전은 AGI의 자율성, 감정, 인과 추론 엔진을 제거하고, **LLM(Gemini)이 파일 시스템, 웹 검색, 코드 생성 등의 도구를 활용하는 'Tool-Augmented LLM'**의 기능을 시연합니다.

## 🚀 실행 방법

1.  **필수 라이브러리 설치**
    ```bash
    pip install -r requirements.txt
    ```

2.  **API 키 설정**
    * `config.py` 파일을 열어 본인의 Google Gemini API 키를 입력합니다.

3.  **EIDOS-Lite 실행**
    ```bash
    python eidos_chat_gui.py
    ```

## 🌟 주요 기능 (Lite)

* **대화형 인터페이스**: PySide6로 제작된 GUI
* **파일 시스템 제어**: `read_file`, `write_file`, `write_project_files_async` 도구를 통한 프로젝트 생성 및 수정
* **RAG (검색 증강 생성)**: `perform_web_search` 도구를 통한 실시간 웹 정보 검색
* **코드 생성**: 'EIDOS Code Editor'와 연동된 AI 코드 수정 및 생성 (`modify_code_async`)
* **수학 계산**: `calculate_math` 도구를 통한 SymPy 연산
