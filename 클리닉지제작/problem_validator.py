from typing import Dict, Any, List, Tuple
import json
import logging
from openai import OpenAI
import os
from pathlib import Path
from common_utils import ConfigManager, FileNameManager, PathManager

class ProblemValidator:
    def __init__(self, config_path: str = None):
        self.path_manager = PathManager()
        self.config_manager = ConfigManager(config_path)
        self.file_manager = FileNameManager(self.config_manager)
        self.gpt_settings = self.config_manager.get_gpt_settings('validation')
        self.validation_prompt = self.config_manager.get_prompt('answer_validation')
        self.correction_prompt = self.config_manager.get_prompt('english_correction')
        
        self.paths = self.config_manager.get_paths()
        self.output_folder = self.paths['validation_results_folder']
        
        self.api_key = self.config_manager.get_api_key()
        self.client = OpenAI(api_key=self.api_key)
        self.logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger('problem_validator')
        logger.setLevel(logging.INFO)
        
        # 로그 파일을 validation_results_folder에 저장
        log_file = self.output_folder / 'problem_validator.log'
        os.makedirs(log_file.parent, exist_ok=True)
        
        file_handler = logging.FileHandler(
            str(log_file),
            encoding='utf-8'
        )
        file_handler.setLevel(logging.INFO)
        
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        return logger

    def validate_answer(self, passage: str, question: str, options: List[str], answer: str) -> Dict[str, Any]:
        try:
            # 검증 프롬프트에 JSON 형식 명시 추가
            prompt = (
                self.validation_prompt.format(
                    본문=passage,
                    문제=question,
                    선지='\n'.join(f"{i+1}. {opt}" for i, opt in enumerate(options)),
                    정답=answer
                ) +
                "\n응답은 반드시 다음과 같은 JSON 형식으로 제공해주세요: "
                '{"is_valid": true/false, '
                '"reason": "문제가 있다면 그 이유를, 없다면 \'적절함\'을 작성", '
                '"suggested_correction": "문제가 있을 경우 수정 제안"}'
            )
            
            self.logger.info(f"Validating question: {question[:50]}...")
            
            response = self.client.chat.completions.create(
                model=self.gpt_settings['model'],
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=float(self.gpt_settings['temperature']),
                max_tokens=int(self.gpt_settings['max_tokens']),
                top_p=float(self.gpt_settings['top_p']),
                frequency_penalty=float(self.gpt_settings['frequency_penalty']),
                presence_penalty=float(self.gpt_settings['presence_penalty']),
                response_format={"type": "json_object"}
            )
            
            validation_result = json.loads(response.choices[0].message.content.strip())
            self.logger.info(f"Validation result: {validation_result.get('is_valid', False)}")
            
            return validation_result
            
        except Exception as e:
            error_msg = f"Error in validate_answer: {str(e)}"
            self.logger.error(error_msg)
            return {
                "error": error_msg,
                "is_valid": False,
                "reason": "Validation process failed",
                "suggested_correction": None
            }
        
    def correct_english(self, passage: str, question: str, options: List[str], indices: List[int]) -> Dict[str, Any]:
        try:
            # 영어 교정 프롬프트에도 JSON 형식 명시 추가
            prompt = (
                self.correction_prompt.format(
                    본문=passage,
                    문제=question,
                    선지='\n'.join(f"{i+1}. {opt}" for i, opt in enumerate(options)),
                    indices=', '.join(map(str, indices))
                ) +
                "\n응답은 반드시 다음과 같은 JSON 형식으로 제공해주세요: "
                '{"corrected_options": ["수정된 선지1", "수정된 선지2", ...]}'
            )
            
            self.logger.info(f"Correcting English for options: {indices}")
            
            response = self.client.chat.completions.create(
                model=self.gpt_settings['model'],
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=float(self.gpt_settings['temperature']),
                max_tokens=int(self.gpt_settings['max_tokens']),
                top_p=float(self.gpt_settings['top_p']),
                frequency_penalty=float(self.gpt_settings['frequency_penalty']),
                presence_penalty=float(self.gpt_settings['presence_penalty']),
                response_format={"type": "json_object"}
            )
            
            correction_result = json.loads(response.choices[0].message.content.strip())
            self.logger.info("English correction completed")
            
            return correction_result
            
        except Exception as e:
            error_msg = f"Error in correct_english: {str(e)}"
            self.logger.error(error_msg)
            return {
                "error": error_msg,
                "corrected_options": []
            }

    def find_non_english_options(self, options: List[str]) -> List[int]:
        """영어가 아닌 선지 찾기"""
        non_english = []
        for i, option in enumerate(options, 1):
            # 한글이 포함된 선지 찾기 (유니코드 범위 사용)
            if any(ord('가') <= ord(char) <= ord('힣') for char in option):
                non_english.append(i)
        return non_english

    def process_single_problem(self, passage: str, problem: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """단일 문제 처리 (검증 및 영어 교정)"""
        validation_result = self.validate_answer(
            passage=passage,
            question=problem['문제'],
            options=problem['선지'],
            answer=problem.get('정답', '')
        )
        
        # 영어 교정이 필요한 선지 찾기
        non_english_indices = self.find_non_english_options(problem['선지'])
        correction_result = None
        
        if non_english_indices:
            correction_result = self.correct_english(
                passage=passage,
                question=problem['문제'],
                options=problem['선지'],
                indices=non_english_indices
            )
        
        return validation_result, correction_result

    def create_merged_results(self, problem_set: List[Dict[str, Any]], 
                            validation_results: List[Dict[str, Any]], 
                            correction_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """검증 결과와 교정 결과를 병합"""
        merged_results = []
        
        for problem, validation, correction in zip(problem_set, validation_results, correction_results):
            merged_item = {
                "본문번호": problem["본문번호"],
                "본문": problem["본문"],
                "문제들": []
            }
            
            for q_idx, q in enumerate(problem["문제들"]):
                merged_problem = {
                    "문제번호": q["문제번호"],
                    "문제": q["문제"],
                    "원본_선지": q["선지"],
                    "정답": problem.get("정답", ""),
                    "검증_결과": validation[q_idx] if validation else {},
                    "교정_결과": correction[q_idx] if correction else {}
                }
                merged_item["문제들"].append(merged_problem)
            
            merged_results.append(merged_item)
        
        return merged_results

    def validate_problem_set(self) -> Dict[str, Any]:
        try:
            json_path = self.file_manager.get_json_path()
            
            if not json_path.exists():
                error_msg = f"Problem set file not found: {json_path}"
                self.logger.error(error_msg)
                return {"error": error_msg}
            
            with open(json_path, 'r', encoding='utf-8') as f:
                problem_set = json.load(f)

            validation_results = []
            correction_results = []
            total_problems = 0
            valid_problems = 0
            
            # Process each problem
            for problem in problem_set:
                passage = problem['본문']
                problem_validations = []
                problem_corrections = []
                
                for q in problem['문제들']:
                    total_problems += 1
                    
                    # Validate and correct each problem
                    validation_result, correction_result = self.process_single_problem(
                        passage=passage,
                        problem=q
                    )
                    
                    if validation_result.get('is_valid', False):
                        valid_problems += 1
                    
                    problem_validations.append(validation_result)
                    problem_corrections.append(correction_result)
                
                validation_results.append(problem_validations)
                correction_results.append(problem_corrections)

            # Merge results
            merged_results = self.create_merged_results(
                problem_set, validation_results, correction_results
            )

            # Save validation results
            output_path = self.file_manager.get_validation_path()
            os.makedirs(output_path.parent, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(merged_results, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"Validation results saved to {output_path}")
            
            return {
                "total_problems": total_problems,
                "valid_problems": valid_problems,
                "issues_found": total_problems - valid_problems,
                "validation_results": merged_results
            }
            
        except Exception as e:
            error_msg = f"Error in validate_problem_set: {str(e)}"
            self.logger.error(error_msg)
            return {"error": error_msg}

def main():
    try:
        # 설정 파일 경로를 자동으로 찾음
        validator = ProblemValidator()
        results = validator.validate_problem_set()
        
        if "error" not in results:
            print(f"\nValidation Summary:")
            print(f"Total Problems: {results['total_problems']}")
            print(f"Valid Problems: {results['valid_problems']}")
            print(f"Issues Found: {results['issues_found']}")
        else:
            print(f"Error: {results['error']}")
        
    except Exception as e:
        print(f"Error in main: {str(e)}")

if __name__ == "__main__":
    main()