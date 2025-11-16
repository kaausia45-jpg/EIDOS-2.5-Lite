import json
import asyncio
import os
from typing import List, Tuple, Optional, Dict, Any

# [Lite] 단순화된 LLM 모듈 임포트
import lite_llm_module
# [Lite] Pro Lock이 제거된 도구 모듈 임포트
import execution_module

class EidosLiteCore:
    """
    EIDOS-Lite Core (v1.0)
    AGI의 '두뇌'를 제거하고, LLM(Gemini)을 '도구 사용 플래너'로 사용하는
    Tool-Augmented LLM Stub입니다.
    """
    def __init__(self):
        # [Lite] 감정, KB, NN 모델, 그래프 등 모든 AGI 구성 요소 제거
        print("✅ [EIDOS-Lite] Stub Core 로드됨.")
        # 샌드박스 루트 설정 (execute_task 헬퍼가 사용)
        self.project_root = os.path.abspath("eidos_files")
        print(f"🔒 [Lite Core] 샌드박스 루트: {self.project_root}")
        
        # [Lite] 사용 가능한 도구 (실제 함수) 맵
        # (execution_module에서 가져옴)
        self.tool_functions = {
            "perform_web_search": execution_module.perform_web_search,
            "calculate_math": execution_module.calculate_math,
            "read_file": execution_module.read_file,
            "write_file": execution_module.write_file,
            "write_project_files_async": execution_module.write_project_files_async,
            # 'write_text'는 LLM을 직접 호출하므로 _execute_task에서 별도 처리
        }
        
        # [Lite] LLM 프롬프트에 주입할 도구 설명 문자열
        self.available_tools_str = "\n".join(
            f"- {name}: {info['description']}" 
            for name, info in execution_module.AVAILABLE_TOOLS.items()
        )

    # --- GUI 연동을 위한 필수 메서드 (단순화) ---

    async def request_modification_suggestion_async(self, current_code: str, chat_history: List[str]) -> str:
        """ [Lite] (Worker -> Core) AI 추천 요청을 LLM 모듈로 전달 """
        return await lite_llm_module.generate_modification_suggestion_async(current_code, chat_history)

    async def request_code_modification_async(self, 
                                            current_code: str, 
                                            user_request: str, 
                                            new_file_name: Optional[str],
                                            current_file_path: Optional[str]) -> Dict[str, str]:
        """ [Lite] (Worker -> Core) 코드 수정 요청을 LLM 모듈로 전달 """
        # (Lite 버전에서는 RAG(CodeVectorDB)를 사용하지 않고, 
        #  llm_module이 코드를 잘라서 처리하는 Fallback 로직에 의존합니다)
        json_str = await lite_llm_module.modify_code_async(
            current_code, 
            user_request, 
            new_file_name,
            relevant_chunks=None # [Lite] RAG 없음
        )
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return {"filepath": "CURRENT", "code": f"[LLM 파싱 오류]\n{json_str}"}

    # --- [Lite] 핵심 process_input (단순화된 버전) ---

    async def process_input(
        self,
        text_input: str,
        image_input: Optional[bytes], # (Lite 버전에선 무시됨)
        chat_history: List[str],
        project_dir: Optional[str] = None, # (Lite 버전에선 사용됨)
        user_text_short: Optional[str] = None
    ) -> Tuple[
        None, str, None, float, bool, List,
        Optional[Dict], Optional[dict], str, str, float, dict
    ]:
        """
        EIDOS-Lite의 메인 처리 루프.
        LLM을 호출하여 도구 계획을 세우고, 실행합니다.
        """
        print(f"\n--- EIDOS-Lite Cycle Start (Input: '{text_input[:50]}...') ---")
        
        reasoning_log = ""
        natural_text = ""
        exec_task_state = None # GUI에 전달할 계획/에디터 정보

        try:
            # 1. [LLM 호출 1] 도구 사용 계획 생성
            plan_json_str = await lite_llm_module.generate_tool_use_plan_async(
                text_input, chat_history, self.available_tools_str
            )
            
            # 2. 계획/대화 분기
            if "CHAT" in plan_json_str.upper():
                # 2a. 단순 대화
                print("  [Lite Core] 'CHAT' 모드 감지. 단순 응답 생성...")
                reasoning_log = "[Lite Core] 단순 대화로 분류됨."
                natural_text = await lite_llm_module.get_llm_response_async(
                    f"사용자의 마지막 말에 대해 친근하게 대답하세요: '{text_input}'"
                )
            
            else:
                # 2b. 도구 사용
                print(f"  [Lite Core] 'TASK' 모드 감지. 계획 수신:\n{plan_json_str}")
                reasoning_log = f"[Lite Core] 도구 사용 계획 수신.\n{plan_json_str}"
                
                # [Lite] GUI가 계획을 표시하고 에디터를 열 수 있도록 exec_task_state 설정
                # (eidos_v4_0_core.py L3314의 로직과 유사하게)
                editor_type_str = "CODE" if "write_project" in plan_json_str or ".py" in plan_json_str else "DOCUMENT"
                project_dir_str = self._extract_project_dir_from_plan_helper(plan_json_str)
                
                exec_task_state = {
                    "plan_json": plan_json_str,
                    "editor_type": editor_type_str,
                    "project_dir": project_dir_str,
                    "evaluation_criteria": None # [Lite] QA 기능 없음
                }
                
                # [Lite] (중요) AGI Core와 달리, Lite는 계획을 '즉시 실행'합니다.
                # autonomous_tick_async가 없기 때문입니다.
                print("  [Lite Core] 계획을 즉시 실행합니다...")
                execution_result = await self._execute_task(
                    plan_json_str, 
                    project_dir_context=project_dir
                )
                
                # 실행 결과를 자연어 응답으로 사용
                natural_text = execution_result.replace("EVENT: ", "")
                reasoning_log += f"\n[Lite Core] 실행 완료: {natural_text}"

        except Exception as e:
            print(f"❌ [Lite Core] process_input 중 심각한 오류: {e}")
            natural_text = f"[Lite Core 오류] {e}"
            reasoning_log = f"오류 발생: {e}"

        # 3. AGI Core의 복잡한 반환값 대신, 단순화된 Stub 데이터 반환
        return (
            None,                       # graph_state (없음)
            "LITE_MODE",                # policy_state
            None,                       # emotion_state_vec (없음)
            0.0,                        # reward_state (없음)
            True,                       # is_event_state (항상 True로 처리)
            [],                         # abduction_ids_state (없음)
            exec_task_state,            # [중요] GUI가 에디터를 열도록 계획 전달
            None,                       # trigger_state (없음)
            reasoning_log,              # [중요] 추론 로그 (계획)
            natural_text,               # [중요] 자연어 응답 (실행 결과)
            1.0,                        # purity (없음)
            {}                          # complex_states (없음)
        )

    # --- eidos_v4_0_core.py에서 이식된 헬퍼 함수 2개 ---
    
    def _extract_project_dir_from_plan_helper(self, exec_task_json: str) -> Optional[str]:
        """ [Helper] JSON 계획을 파싱하여 eidos_files/ 하위의
            프로젝트 디렉토리 이름(첫 번째 폴더)을 추출합니다. (Sync)
            (eidos_v4_0_core.py L3448에서 복사)
        """
        try:
            task_list = json.loads(exec_task_json)
            if not isinstance(task_list, list): return None
            for task in task_list:
                args = task.get("args", {})
                if not args or not isinstance(args, dict): continue
                target_path = None
                if "file_structure" in args and isinstance(args["file_structure"], dict) and args["file_structure"]:
                    target_path = list(args["file_structure"].keys())[0]
                elif "filepath" in args and isinstance(args["filepath"], str):
                    target_path = args["filepath"]
                elif "path" in args and isinstance(args["path"], str):
                    target_path = args["path"]
                if target_path:
                    norm_path = os.path.normpath(target_path)
                    prefix = "eidos_files" + os.sep
                    relative_path = None
                    if norm_path.startswith(prefix):
                        relative_path = norm_path[len(prefix):]
                    elif norm_path.startswith("." + os.sep + prefix):
                        relative_path = norm_path[len("." + os.sep + prefix):]
                    else: continue 
                    parts = relative_path.split(os.sep)
                    if len(parts) > 1: return parts[0]
            return None
        except Exception:
            return None

    async def _execute_task(self, task_plan_json: str, project_dir_context: Optional[str] = None) -> str:
        """
        [Helper] EIDOS Core (v18.21)에서 이식된 도구 실행기.
        (eidos_v4_0_core.py L3683에서 복사 및 단순화)
        """
        print(f"⚙️ [Exec-Lite] 작업 계획(JSON) 수신: '{task_plan_json}'")
        
        # [Lite] 이 맵은 __init__에서 설정한 self.tool_functions를 사용
        available_tool_functions = self.tool_functions.copy()

        # [Lite] 샌드박스 경로 설정 (project_root는 __init__에서 설정됨)
        BASE_PATH = self.project_root 
        if project_dir_context:
            safe_base_path = os.path.normpath(os.path.join(BASE_PATH, project_dir_context))
        else:
            safe_base_path = BASE_PATH

        def _check_and_correct_path(rel_path: str, base_dir: str, must_exist: bool = False) -> str:
             """ (Helper) eidos_v4_0_core.py L3736에서 복사된 보안 검사 """
             abs_target = os.path.normpath(os.path.join(base_dir, rel_path))
             if os.path.commonprefix([abs_target, base_dir]) != base_dir:
                 raise PermissionError(f"Security Error: Path is outside sandbox: {rel_path}")
             if must_exist and not os.path.exists(abs_target):
                 raise FileNotFoundError(f"File not found: {rel_path}")
             return abs_target
        
        try:
            task_list = json.loads(task_plan_json)
        except Exception as e:
            return f"EVENT: 작업 계획 파싱 실패. (오류: {e})"

        previous_step_result = "" 
        final_result = ""

        for i, task in enumerate(task_list):
            try:
                tool_name = task.get("tool")
                args_dict = task.get("args", {})
                print(f"  [Exec-Lite Step {i+1}] Tool: '{tool_name}'")

                # [Lite] 'write_text'는 LLM을 직접 호출
                if tool_name == "write_text":
                    prompt = args_dict.get("prompt", "")
                    if "$PREV_STEP_RESULT" in prompt:
                        prompt = prompt.replace("$PREV_STEP_RESULT", previous_step_result)
                    print("    -> (LLM 호출 중...)")
                    current_result = await lite_llm_module.get_llm_response_async(prompt)
                    previous_step_result = current_result
                    final_result = current_result
                    print(f"  [Exec-Lite Step {i+1}] 완료 (LLM).")
                    continue

                func_to_call = available_tool_functions.get(tool_name)
                if not func_to_call:
                    final_result = f"'{tool_name}' 도구를 찾을 수 없음."
                    continue

                # [Lite] 경로 보안 검사 (Core 로직 재사용)
                if tool_name in ("write_file", "read_file", "write_project_files_async"):
                    if tool_name == "write_project_files_async":
                        original_file_dict = args_dict.get("file_structure", {})
                        corrected_file_dict = {}
                        for rel_path, content in original_file_dict.items():
                            safe_abs_path = _check_and_correct_path(rel_path, safe_base_path)
                            corrected_file_dict[safe_abs_path] = content
                        args_dict["file_structure"] = corrected_file_dict
                    
                    elif tool_name in ("write_file", "read_file"):
                        original_path = args_dict.get("filepath", args_dict.get("path"))
                        if original_path:
                            safe_abs_path = _check_and_correct_path(
                                original_path, 
                                safe_base_path, 
                                must_exist=(tool_name == "read_file")
                            )
                            args_dict["filepath"] = safe_abs_path

                # 인수(Argument) 준비 (플레이스홀더 교체)
                for key, value in args_dict.items():
                    if isinstance(value, str) and "$PREV_STEP_RESULT" in value:
                        args_dict[key] = value.replace("$PREV_STEP_RESULT", previous_step_result)

                # 도구 실행 (비동기 호출)
                current_result = await func_to_call(**args_dict)
                
                previous_step_result = current_result
                final_result = current_result 
                print(f"  [Exec-Lite Step {i+1}] 완료.")

            except Exception as e:
                print(f"❌ [Exec-Lite] '{tool_name}' 실행 중 오류: {e}")
                return f"EVENT: 작업 '{tool_name}' 실행 중 오류 발생: {e}"

        print(f"✅ [Exec-Lite] 모든 계획 실행 완료.")
        return f"EVENT: 작업 계획 실행 완료. 최종 결과: {final_result}"
