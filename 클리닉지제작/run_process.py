from problem_generator import ProblemGenerator
from problem_validator import ProblemValidator
from common_utils import ConfigManager
from word_converter import WordConverter  # 추가된 import
import time
from pathlib import Path
from typing import Dict, Any
import sys
import shutil
import os
import logging


class ProcessRunner:
    def __init__(self):
        self.config_manager = ConfigManager()
        self.generator = ProblemGenerator()
        self.validator = ProblemValidator()
        
        # 기본 경로 설정
        base_output_dir = Path("output")
        self.paths = self.config_manager.get_paths()
        
        self.output_folders = {
            'generated_problems': self.generator.output_folder,
            'validation_results': self.validator.output_folder,
            'word_documents': base_output_dir / "word_documents"  # 기본값 설정
        }

        # word_output_folder가 config에 있으면 해당 값 사용
        if 'word_output_folder' in self.paths:
            self.output_folders['word_documents'] = Path(self.paths['word_output_folder'])

    def cleanup_log_handlers(self):
        """로그 핸들러들을 정리"""
        loggers = [
            logging.getLogger('problem_generator'),
            logging.getLogger('problem_validator')
        ]
        
        for logger in loggers:
            handlers = logger.handlers[:]
            for handler in handlers:
                handler.close()
                logger.removeHandler(handler)

    def clear_output_folders(self, force: bool = False) -> bool:
        """출력 폴더들을 정리"""
        try:
            # 폴더 내 파일 존재 여부 확인
            has_files = False
            for folder in self.output_folders.values():
                if folder.exists() and any(folder.iterdir()):
                    has_files = True
                    break
            
            if not has_files:
                return True

            if not force:
                print("\n기존 출력 파일들이 발견되었습니다.")
                response = input("출력 폴더들을 비우고 진행하시겠습니까? (y/n): ").lower().strip()
                
                if response != 'y':
                    print("프로세스를 중단합니다.")
                    return False

            # 로그 핸들러 정리
            self.cleanup_log_handlers()

            # 잠시 대기하여 파일 핸들이 완전히 해제되도록 함
            time.sleep(0.5)

            # 각 폴더 정리
            for name, folder in self.output_folders.items():
                if folder.exists():
                    try:
                        # 폴더 내 파일들 개별 삭제
                        for file_path in folder.glob('*'):
                            try:
                                if file_path.is_file():
                                    file_path.unlink()
                                elif file_path.is_dir():
                                    shutil.rmtree(file_path)
                            except Exception as e:
                                print(f"Warning: {file_path} 삭제 실패: {str(e)}")
                        
                        # 빈 폴더 삭제
                        folder.rmdir()
                    except Exception as e:
                        print(f"Warning: {folder} 폴더 삭제 실패: {str(e)}")
                
                # 폴더 재생성
                folder.mkdir(parents=True, exist_ok=True)
                print(f"{name} 폴더를 정리했습니다: {folder}")

            return True

        except Exception as e:
            print(f"폴더 정리 중 오류 발생: {str(e)}")
            return False

    def run_generator(self) -> Dict[str, Any]:
        """문제 생성 프로세스 실행"""
        print("1. 문제 생성 프로세스 시작...")
        
        # Excel 형식 검증
        if not self.generator.validate_excel_format():
            print("Error: Excel 파일 형식이 올바르지 않습니다. 로그 파일을 확인해주세요.")
            sys.exit(1)

        # 문제 생성
        start_time = time.time()
        result = self.generator.generate_draft()
        elapsed_time = time.time() - start_time

        if "error" in result:
            print(f"Error: 문제 생성 중 오류 발생: {result['error']}")
            sys.exit(1)

        print(f"\n문제 생성 완료:")
        print(f"- 총 지문 수: {result.get('total_passages', 0)}")
        print(f"- 총 문제 수: {result.get('total_problems', 0)}")
        print(f"- 소요 시간: {self.format_time(elapsed_time)}")
        
        return result

    def run_validator(self) -> Dict[str, Any]:
        """검증 프로세스 실행"""
        print("\n2. 문제 검증 프로세스 시작...")
        
        start_time = time.time()
        results = self.validator.validate_problem_set()
        elapsed_time = time.time() - start_time

        if "error" in results:
            print(f"Error: 검증 중 오류 발생: {results['error']}")
            sys.exit(1)

        print(f"\n검증 완료:")
        print(f"- 검증된 문제 수: {results.get('total_problems', 0)}")
        print(f"- 유효한 문제 수: {results.get('valid_problems', 0)}")
        print(f"- 발견된 문제점: {results.get('issues_found', 0)}")
        print(f"- 소요 시간: {self.format_time(elapsed_time)}")
        
        return results

    def run_word_converter(self) -> bool:
        """워드 문서 변환 프로세스 실행"""
        print("\n3. Word 문서 변환 프로세스 시작...")
        
        start_time = time.time()
        
        # 워드 출력 경로 설정
        json_path = self.generator.file_manager.get_json_path()
        word_output_folder = self.paths['word_output_folder']
        word_output = word_output_folder / f"{json_path.stem}.docx"
        
        converter = WordConverter(
            json_path=json_path,
            output_path=word_output,
            word_settings=self.config_manager.get_word_settings()
        )
        
        # 변환 실행
        success = converter.convert_to_word()
        elapsed_time = time.time() - start_time

        if success:
            print(f"\nWord 변환 완료:")
            print(f"- 출력 파일: {word_output}")
            print(f"- 소요 시간: {self.format_time(elapsed_time)}")
            return True
        else:
            print("Error: Word 문서 생성 실패")
            return False

    def run_full_process(self, force_clear: bool = False):
        """전체 프로세스 실행"""
        try:
            # 출력 폴더 정리
            if not self.clear_output_folders(force_clear):
                return
                
            total_start_time = time.time()
            
            print("\n클리닉지 문제 생성 및 검증 프로세스 시작\n")
            
            # 새로운 로거 설정을 위해 객체 재생성
            self.generator = ProblemGenerator()
            self.validator = ProblemValidator()
            
            # 1. 문제 생성
            generation_result = self.run_generator()
            self.print_separator()
            
            # 2. 검증
            validation_result = self.run_validator()
            self.print_separator()
            
            # 3. Word 변환
            word_result = self.run_word_converter()
            self.print_separator()
            
            # 4. 최종 요약
            total_time = time.time() - total_start_time
            print("프로세스 완료 요약:")
            print(f"- 생성된 지문 수: {generation_result.get('total_passages', 0)}")
            print(f"- 생성된 문제 수: {generation_result.get('total_problems', 0)}")
            print(f"- 유효한 문제 수: {validation_result.get('valid_problems', 0)}")
            print(f"- 발견된 문제점: {validation_result.get('issues_found', 0)}")
            print(f"- Word 변환: {'성공' if word_result else '실패'}")
            print(f"- 총 소요 시간: {self.format_time(total_time)}")
            
            # 5. 파일 위치 안내
            print(f"\n생성된 파일 위치:")
            for name, folder in self.output_folders.items():
                print(f"- {name}: {folder}")

        except KeyboardInterrupt:
            print("\n\n프로세스가 사용자에 의해 중단되었습니다.")
            sys.exit(1)
        except Exception as e:
            print(f"\n\nError: 프로세스 실행 중 오류 발생: {str(e)}")
            sys.exit(1)
        finally:
            # 프로세스 종료 시 로그 핸들러 정리
            self.cleanup_log_handlers()

    def print_separator(self):
        """구분선 출력"""
        print("\n" + "="*50 + "\n")

    def format_time(self, seconds: float) -> str:
        """시간을 보기 좋게 포맷팅"""
        if seconds < 60:
            return f"{seconds:.1f}초"
        minutes = int(seconds // 60)
        seconds = seconds % 60
        return f"{minutes}분 {seconds:.1f}초"

def main():
    try:
        # -f 또는 --force 옵션으로 강제 정리 가능
        force_clear = len(sys.argv) > 1 and sys.argv[1] in ['-f', '--force']
        
        runner = ProcessRunner()
        runner.run_full_process(force_clear)
        
    except Exception as e:
        print(f"Error in main: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()