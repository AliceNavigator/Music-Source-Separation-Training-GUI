import sys
import os
import logging
import traceback
import json
import subprocess
import time
import psutil
import shutil
import pynvml
import platform
import copy
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QPushButton, QLabel, QComboBox, QCheckBox,
                             QFileDialog, QTextEdit, QMessageBox, QInputDialog,
                             QHBoxLayout, QGroupBox, QFormLayout, QLineEdit,
                             QDialog, QTableWidget, QTableWidgetItem, QHeaderView,
                             QTabWidget, QScrollArea, QToolButton, QSizePolicy)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer, QMutex, QWaitCondition, pyqtSlot, QMetaObject, Q_ARG, \
    QUrl
from PyQt5.QtGui import QFont, QIcon, QColor, QTextCharFormat, QTextCursor, QPainter, QPixmap, QDesktopServices, \
    QFontInfo
import resources_rc
from archive import archive_folders
import tempfile
import multiprocessing
from queue import Empty
import re
import shlex
from threading import Lock
import inference_standalone

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
logging.basicConfig(filename='msst_gui.log', level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CONFIG_FILE = 'model_config_zh.json'


def remove_screen_splash():
    # Use this code to signal the splash screen removal.
    logging.debug("Starting splash screen removal...")
    if "NUITKA_ONEFILE_PARENT" in os.environ:
        logging.debug(f"NUITKA_ONEFILE_PARENT: {os.environ['NUITKA_ONEFILE_PARENT']}")
        splash_filename = os.path.join(
            tempfile.gettempdir(),
            f"onefile_{int(os.environ['NUITKA_ONEFILE_PARENT'])}_splash_feedback.tmp"
        )
        logging.debug(f"Splash filename: {splash_filename}")
        if os.path.exists(splash_filename):
            try:
                os.unlink(splash_filename)
                logging.debug("Splash file removed successfully")
            except Exception as e:
                logging.error(f"Error removing splash file: {e}")
        else:
            logging.debug("Splash file does not exist")
    else:
        logging.debug("NUITKA_ONEFILE_PARENT not in environment variables")

    logging.debug("Splash screen removal complete")


def load_or_create_config():
    if not os.path.exists(CONFIG_FILE):
        initial_config = {
            "vocal_models": {
                "None": "禁用人声分离模块",
                "MelBandRoformer_kim.ckpt": "【推荐】，SDR基本等于1297和1296但用时减半",
                "model_bs_roformer_ep_317_sdr_12.9755.ckpt": "注：1297的SDR稍高，但有反馈指出可能引入极高频上的噪音",
                "model_bs_roformer_ep_368_sdr_12.9628.ckpt": "1296的SDR略低，但没有极高频上的噪音"
            },
            "kara_models": {
                "None": "禁用和声分离模块",
                "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt": "激进，但性能比UVR现有模型都要好非常多，若剥残人声可考虑禁用该模块而依靠混响和声模块去和声"
            },
            "reverb_models": {
                "None": "禁用混响和声分离模块",
                "dereverb_mel_band_roformer_anvuew_sdr_19.1729.ckpt": "【推荐】目前SDR得分最高",
                "dereverb_mel_band_roformer_less_aggressive_anvuew_sdr_18.8050.ckpt": "【推荐】比1917保守，若有剥残情况下选用",
                "deverb_bs_roformer_8_384dim_10depth.ckpt": "使用了更多数据训练的新bs模型，SDR更高，在和声分离上比mel系的要保守",
                "deverb_bs_roformer_8_256dim_8depth.ckpt": "旧的bs模型",
                "deverb_mel_band_roformer_8_256dim_6depth.ckpt": "非常激进的去混响，视曲目不同可能会把人声剥残，但更激进也在一些场合有更好的效果",
                "deverb_mel_band_roformer_8_512dim_12depth.ckpt": "比8_256_6更大的网络带来稍高的SDR的同时消耗3倍以上推理时间",
                "deverb_mel_band_roformer_ep_27_sdr_10.4567.ckpt": "最初版模型，在去混响和去和声上有不错的平衡"
            },
            "other_models": {
                "None": "禁用其他模块",
                "denoise_mel_band_roformer_aufr33_sdr_27.9959.ckpt": "【降噪】使用SDR 27.9959的通常版模型",
                "denoise_mel_band_roformer_aufr33_aggr_sdr_27.9768.ckpt": "【降噪】使用SDR 27.9768的激进版模型",
                "Apollo_LQ_MP3_restoration.ckpt": "【修复】用于修复mp3音质的模型，修复至44.1 kHz",
                "aspiration_mel_band_roformer_sdr_18.9845.ckpt": "【气声】用于分离各种气口的气声，例如说吸气声",
                "aspiration_mel_band_roformer_less_aggr_sdr_18.1201.ckpt": "【气声】保守一些版本的气声分离",
                "mel_band_roformer_crowd_aufr33_viperx_sdr_8.7144.ckpt": "【降噪】用于分离背景嘈杂说话声的模型，但对音质影响很大"
            },
            "config_paths": {
                "MelBandRoformer_kim.ckpt": [
                    "configs/config_vocals_mel_band_roformer_kim.yaml",
                    "configs/config_vocals_mel_band_roformer_kim-fast.yaml"
                ],
                "model_bs_roformer_ep_317_sdr_12.9755.ckpt": [
                    "configs/model_bs_roformer_ep_317_sdr_12.9755.yaml",
                    "configs/model_bs_roformer_ep_317_sdr_12.9755-fast.yaml"
                ],
                "model_bs_roformer_ep_368_sdr_12.9628.ckpt": [
                    "configs/model_bs_roformer_ep_368_sdr_12.9628.yaml",
                    "configs/model_bs_roformer_ep_368_sdr_12.9628-fast.yaml"
                ],
                "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt": [
                    "configs/config_mel_band_roformer_karaoke.yaml",
                    "configs/config_mel_band_roformer_karaoke-fast.yaml"
                ],
                "dereverb_mel_band_roformer_anvuew_sdr_19.1729.ckpt": [
                    "configs/dereverb_mel_band_roformer_anvuew.yaml",
                    "configs/dereverb_mel_band_roformer_anvuew-fast.yaml"
                ],
                "dereverb_mel_band_roformer_less_aggressive_anvuew_sdr_18.8050.ckpt": [
                    "configs/dereverb_mel_band_roformer_anvuew.yaml",
                    "configs/dereverb_mel_band_roformer_anvuew-fast.yaml"
                ],
                "deverb_bs_roformer_8_384dim_10depth.ckpt": [
                    "configs/deverb_bs_roformer_8_384dim_10depth.yaml",
                    "configs/deverb_bs_roformer_8_384dim_10depth-fast.yaml"
                ],
                "deverb_bs_roformer_8_256dim_8depth.ckpt": [
                    "configs/deverb_bs_roformer_8_256dim_8depth.yaml",
                    "configs/deverb_bs_roformer_8_256dim_8depth-fast.yaml"
                ],
                "deverb_mel_band_roformer_8_256dim_6depth.ckpt": [
                    "configs/8_256_6_deverb_mel_band_roformer_8_256dim_6depth.yaml",
                    "configs/8_256_6_deverb_mel_band_roformer_8_256dim_6depth-fast.yaml"
                ],
                "deverb_mel_band_roformer_8_512dim_12depth.ckpt": [
                    "configs/8_512_12_deverb_mel_band_roformer_8_512dim_12depth.yaml",
                    "configs/8_512_12_deverb_mel_band_roformer_8_512dim_12depth-fast.yaml"
                ],
                "deverb_mel_band_roformer_ep_27_sdr_10.4567.ckpt": [
                    "configs/deverb_mel_band_roformer.yaml",
                    "configs/deverb_mel_band_roformer-fast.yaml"
                ],
                "denoise_mel_band_roformer_aufr33_sdr_27.9959.ckpt": [
                    "configs/model_mel_band_roformer_denoise.yaml",
                    "configs/model_mel_band_roformer_denoise-fast.yaml"
                ],
                "denoise_mel_band_roformer_aufr33_aggr_sdr_27.9768.ckpt": [
                    "configs/model_mel_band_roformer_denoise.yaml",
                    "configs/model_mel_band_roformer_denoise-fast.yaml"
                ],
                "Apollo_LQ_MP3_restoration.ckpt": [
                    "configs/config_apollo_LQ_MP3_restoration.yaml",
                    "configs/config_apollo_LQ_MP3_restoration-fast.yaml"
                ],
                "aspiration_mel_band_roformer_sdr_18.9845.ckpt": [
                    "configs/config_aspiration_mel_band_roformer.yaml",
                    "configs/config_aspiration_mel_band_roformer-fast.yaml"
                ],
                "aspiration_mel_band_roformer_less_aggr_sdr_18.1201.ckpt": [
                    "configs/config_aspiration_mel_band_roformer.yaml",
                    "configs/config_aspiration_mel_band_roformer-fast.yaml"
                ],
                "mel_band_roformer_crowd_aufr33_viperx_sdr_8.7144.ckpt": [
                    "configs/model_mel_band_roformer_crowd_aufr33_viperx.yaml",
                    "configs/model_mel_band_roformer_crowd_aufr33_viperx-fast.yaml"
                ]
            },
            "model_types": {
                "MelBandRoformer_kim.ckpt": "mel_band_roformer",
                "model_bs_roformer_ep_317_sdr_12.9755.ckpt": "bs_roformer",
                "model_bs_roformer_ep_368_sdr_12.9628.ckpt": "bs_roformer",
                "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt": "mel_band_roformer",
                "dereverb_mel_band_roformer_anvuew_sdr_19.1729.ckpt": "mel_band_roformer",
                "dereverb_mel_band_roformer_less_aggressive_anvuew_sdr_18.8050.ckpt": "mel_band_roformer",
                "deverb_bs_roformer_8_384dim_10depth.ckpt": "bs_roformer",
                "deverb_bs_roformer_8_256dim_8depth.ckpt": "bs_roformer",
                "deverb_mel_band_roformer_8_256dim_6depth.ckpt": "mel_band_roformer",
                "deverb_mel_band_roformer_8_512dim_12depth.ckpt": "mel_band_roformer",
                "deverb_mel_band_roformer_ep_27_sdr_10.4567.ckpt": "mel_band_roformer",
                "denoise_mel_band_roformer_aufr33_sdr_27.9959.ckpt": "mel_band_roformer",
                "denoise_mel_band_roformer_aufr33_aggr_sdr_27.9768.ckpt": "mel_band_roformer",
                "Apollo_LQ_MP3_restoration.ckpt": "apollo",
                "aspiration_mel_band_roformer_sdr_18.9845.ckpt": "mel_band_roformer",
                "aspiration_mel_band_roformer_less_aggr_sdr_18.1201.ckpt": "mel_band_roformer",
                "mel_band_roformer_crowd_aufr33_viperx_sdr_8.7144.ckpt": "mel_band_roformer"
            },
            "inference_env": ".\\env\\python.exe"
        }
        with open(CONFIG_FILE, 'w') as f:
            json.dump(initial_config, f, indent=4)

    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)


class SystemInfoThread(QThread):
    info_signal = pyqtSignal(str, str, bool, bool, bool)

    def __init__(self):
        super().__init__()
        self.mutex = QMutex()
        self.condition = QWaitCondition()
        self.text_queue = []
        self.is_running = True

    def run(self):
        self.get_system_info()
        while self.is_running:
            self.mutex.lock()
            if not self.text_queue:
                self.condition.wait(self.mutex)
            if self.text_queue:
                text, color, bold, italic, auto_newline, delay = self.text_queue.pop(0)
                self.mutex.unlock()
                for char in text:
                    if not self.is_running:
                        return
                    self.info_signal.emit(char, color, bold, italic, False)
                    self.msleep(delay)
                if auto_newline:
                    self.info_signal.emit('\n', color, False, False, False)
            else:
                self.mutex.unlock()

    @staticmethod
    def get_cpu_info():
        if platform.system() == "Windows":
            try:
                output = subprocess.check_output("wmic cpu get name", shell=True).decode('utf-8').strip()
                lines = output.split('\n')
                if len(lines) > 1:
                    return lines[1]  # The first line is the header, the second line is the CPU name
            except subprocess.CalledProcessError as e:
                logger.error(f"Error executing WMIC command: {str(e)}")
            except Exception as e:
                logger.error(f"Error getting CPU info: {str(e)}")
        return platform.processor()

    def get_system_info(self):
        self.print_with_delay("系统信息:", color='gray', bold=True)
        self.print_with_delay("=" * 50, color='gray')

        cpu_info = self.get_cpu_info()
        cpu_info_str = f"CPU: {cpu_info}"
        self.print_with_delay(cpu_info_str, color='#ffc0cb')

        ram = psutil.virtual_memory()
        ram_total_gb = ram.total / (1024 ** 3)
        ram_info = f"内存: {ram.total / (1024 ** 3):.2f} GB (已用: {ram.percent}%)"
        self.print_with_delay(ram_info, color='#ffc0cb')

        if ram_total_gb < 16:
            ram_warning = "警告：可用内存小于16GB，请考虑开启虚拟内存以避免资源不足"
        else:
            ram_warning = "可用内存满足推理需求"

        gpu_info = "显卡: 未检测到或不受支持"
        gpu_warning = ""

        try:
            pynvml.nvmlInit()
            deviceCount = pynvml.nvmlDeviceGetCount()
            if deviceCount > 0:
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)

                gpu_name = pynvml.nvmlDeviceGetName(handle)
                if isinstance(gpu_name, bytes):
                    gpu_name = gpu_name.decode('utf-8')

                memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                total_memory = memory_info.total / (1024 * 1024)
                used_memory = memory_info.used / (1024 * 1024)
                free_memory = memory_info.free / (1024 * 1024)

                driver_version = pynvml.nvmlSystemGetDriverVersion()
                if isinstance(driver_version, bytes):
                    driver_version = driver_version.decode('utf-8')

                gpu_info = (
                    f"显卡: {gpu_name}\n"
                    f"显存: {total_memory:.0f} MB (已用: {used_memory:.0f} MB)\n"
                    f"驱动版本: {driver_version}"
                )

                if free_memory < 2000:
                    gpu_warning = "警告：可用显存低于2GB，不满足推理需求，请开启CPU推理"
                elif free_memory < 4000:
                    gpu_warning = "警告：可用显存低于4GB，这可能导致OOM，推荐开启快速推理"
                else:
                    gpu_warning = "可用显存满足推理需求"
            else:
                gpu_warning = "没有检测到可用的NVIDIA显卡，请开启CPU推理"

            pynvml.nvmlShutdown()
        except Exception as e:
            gpu_warning = f"检测显卡时出错: {str(e)}. \n请开启CPU推理"

        self.print_with_delay(gpu_info, color='#ffc0cb')
        self.print_with_delay("=" * 50, color='gray')
        self.print_with_delay(gpu_warning, color='#ffa500')
        self.print_with_delay(ram_warning, color='#ffa500')
        self.print_with_delay("=" * 50, color='gray')
        self.print_with_delay("Github: https://github.com/AliceNavigator/Music-Source-Separation-Training-GUI",
                              color='green', auto_newline=False)

    @pyqtSlot(str, str, bool, bool, bool, int)
    def print_with_delay(self, text, color='white', bold=False, italic=False, auto_newline=True, delay=10):
        self.mutex.lock()
        self.text_queue.append((text, color, bold, italic, auto_newline, delay))
        self.condition.wakeOne()
        self.mutex.unlock()

    def stop(self):
        self.is_running = False
        self.condition.wakeOne()


class CustomComboBox(QComboBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setPen(QColor("#4CAF50"))
        painter.drawText(self.rect().adjusted(0, 0, -5, 0), Qt.AlignRight | Qt.AlignVCenter, "▼")


class InferenceThread(QThread):
    update_signal = pyqtSignal(str, bool)
    finished_signal = pyqtSignal(dict)
    file_organization_signal = pyqtSignal(int, float)

    def __init__(self, commands, input_folder):
        super().__init__()
        self.commands = commands
        self.input_folder = input_folder
        self.is_running = True
        self.process = None
        self.process_lock = Lock()
        self.queue = multiprocessing.Queue()

    def run(self):
        start_time = time.time()
        summary = {
            "total_files": 0,
            "modules": [],
            "errors": 0,
            "status": "completed"
        }

        module_names = {
            "separation_results": "人声分离",
            "karaoke_results": "和声分离",
            "deverb_results": "混响和声分离",
            "other_results": "其他"
        }

        try:
            total_files = sum(len(files) for _, _, files in os.walk(self.input_folder))
            summary["total_files"] = total_files
            logger.info(f"Total files in input folder: {total_files}")

            for args, store_dir in self.commands:
                if not self.is_running:
                    summary["status"] = "stopped"
                    break

                logger.info(f"Starting inference with args: {args}")
                self.update_signal.emit(f"使用模块: {module_names[store_dir]}", False)
                self.update_signal.emit(f"参数: {args}", False)

                with self.process_lock:
                    self.process = multiprocessing.Process(target=self.run_inference, args=(args, self.queue))
                    self.process.start()

                while self.is_running:
                    with self.process_lock:
                        if self.process is None or not self.process.is_alive():
                            break
                    try:
                        output, is_progress = self.queue.get(timeout=0.1)
                        self.update_signal.emit(output, is_progress)
                    except Empty:
                        continue

                with self.process_lock:
                    if self.process:
                        if self.process.is_alive():
                            self.process.terminate()
                            self.process.join(timeout=5)
                            if self.process.is_alive():
                                self.process.kill()
                                self.process.join()

                        if self.process.exitcode != 0:
                            logger.error(f"Inference process for {store_dir} exited with code {self.process.exitcode}")
                            summary["errors"] += 1
                        else:
                            summary["modules"].append((module_names[store_dir], store_dir))
                            logger.info(f"Module {store_dir} completed successfully")

                        self.process = None

                moved_files, time_taken = self.organize_instrumental_files(store_dir)
                self.file_organization_signal.emit(moved_files, time_taken)

        except Exception as e:
            logger.error(f"Error in inference thread: {str(e)}")
            logger.error(traceback.format_exc())
            summary["status"] = "error"
            summary["error_message"] = str(e)
        finally:
            if summary["status"] == "completed" and not self.is_running:
                summary["status"] = "stopped"
            summary["total_time"] = time.time() - start_time
            logger.info(
                f"Inference completed. Status: {summary['status']}, Total files: {summary['total_files']}, Time: {summary['total_time']:.2f} seconds")
            self.finished_signal.emit(summary)

    @staticmethod
    def run_inference(args, queue):
        sys.stdout = sys.stderr = OutputRedirector(queue)
        logger.info(f"Starting inference in subprocess with args: {args}")
        try:
            inference_standalone.proc_folder(args)
            logger.info("Inference subprocess completed successfully")
        except Exception as e:
            logger.error(f"Error in inference subprocess: {str(e)}")
            logger.error(traceback.format_exc())
        finally:
            logger.info("Inference subprocess finished")

    def stop(self):
        logger.info("Stopping inference thread")
        self.is_running = False
        self.terminate_process()
        if not self.wait(5000):  # 等待5秒
            logger.warning("Inference thread did not finish in time, forcing termination")
            self.terminate()

    def terminate_process(self):
        logger.info("Terminating inference process")
        with self.process_lock:
            if self.process:
                try:
                    if self.process.is_alive():
                        self.process.terminate()
                        self.process.join(timeout=5)
                        if self.process.is_alive():
                            self.process.kill()
                            self.process.join()
                except Exception as e:
                    logger.error(f"Error while terminating process: {str(e)}")
                finally:
                    self.process = None

    @staticmethod
    def organize_instrumental_files(store_dir):
        instrumental_dir = os.path.join(store_dir, "instrumental")
        if not os.path.exists(instrumental_dir):
            os.makedirs(instrumental_dir)

        moved_files = 0
        start_time = time.time()
        inst_lower = ['_instrumental', '_aspiration']

        for filename in os.listdir(store_dir):
            for lower in inst_lower:
                if lower in filename.lower():
                    src_path = os.path.join(store_dir, filename)
                    dst_path = os.path.join(instrumental_dir, filename)
                    shutil.move(src_path, dst_path)
                    moved_files += 1

        end_time = time.time()
        logger.info(f"Organized {moved_files} instrumental files in {store_dir}")
        logger.info(f"Time taken to organize files: {end_time - start_time:.2f} seconds")

        return moved_files, end_time - start_time


class OutputRedirector:
    def __init__(self, queue):
        self.queue = queue

    def write(self, msg):
        if msg.strip():
            is_progress = msg.startswith('\r') and ('it/s]' in msg or '% Complete' in msg)
            self.queue.put((msg.strip(), is_progress))

    def flush(self):
        pass


class ModelEditDialog(QDialog):
    def __init__(self, model_name, model_info, config, parent=None):
        super().__init__(parent)
        self.cancel_button = None
        self.save_button = None
        self.model_type_edit = None
        self.fast_config_path_edit = None
        self.config_path_edit = None
        self.description_edit = None
        self.model_name = model_name
        self.model_info = model_info
        self.config = config
        self.setWindowTitle(f"Edit Model: {model_name}")
        self.setGeometry(100, 100, 800, 500)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)

        title_label = QLabel(f"编辑模型: {self.model_name}")
        title_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #333;")
        layout.addWidget(title_label)

        form_layout = QFormLayout()
        form_layout.setSpacing(15)

        self.description_edit = QTextEdit(self.model_info)
        self.description_edit.setFixedHeight(100)
        form_layout.addRow(self.create_label("简述:"), self.description_edit)

        self.config_path_edit = QLineEdit(self.config.get("config_paths", {}).get(self.model_name, ["", ""])[0])
        form_layout.addRow(self.create_label("配置文件路径:"), self.config_path_edit)

        self.fast_config_path_edit = QLineEdit(self.config.get("config_paths", {}).get(self.model_name, ["", ""])[1])
        form_layout.addRow(self.create_label("快速配置文件路径:"), self.fast_config_path_edit)

        self.model_type_edit = QLineEdit(self.config.get("model_types", {}).get(self.model_name, ""))
        form_layout.addRow(self.create_label("模型类型:"), self.model_type_edit)

        layout.addLayout(form_layout)

        explanation_text = """
        <b>简述:</b> 设置一个简短的描述，介绍模型的特点和效果.<br>
        <b>配置文件路径:</b> 推理时使用的配置文件路径.<br>
        <b>快速配置文件路径:</b> 开启快速推理模式时使用的配置文件路径，通常设置较低的推理参数.<br>
        <b>模型类型:</b> 使用的模型的类型 (例： mel_band_roformer, bs_roformer).
        """
        explanation_label = QLabel(explanation_text)
        explanation_label.setWordWrap(True)
        explanation_label.setStyleSheet("background-color: #f0f4f8; padding: 15px; border-radius: 10px; color: #333;")
        layout.addWidget(explanation_label)

        # save cancel button
        button_widget = QWidget()
        button_layout = QHBoxLayout(button_widget)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(10)

        self.save_button = self.create_styled_button("保存")
        self.cancel_button = self.create_styled_button("取消")
        self.save_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)

        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)

        layout.addWidget(button_widget, 0, Qt.AlignRight | Qt.AlignBottom)

        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
                border-radius: 10px;
            }
            QLabel {
                font-size: 14px;
                color: #333;
            }
            QLineEdit, QTextEdit {
                border: 1px solid #ddd;
                border-radius: 5px;
                padding: 8px;
                background-color: #f9f9f9;
                font-size: 14px;
            }
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                padding: 10px 20px;
                text-align: center;
                text-decoration: none;
                font-size: 14px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #357abd;
            }
        """)

    @staticmethod
    def create_label(text):
        label = QLabel(text)
        label.setStyleSheet("font-weight: bold; color: #333;")
        return label

    @staticmethod
    def create_styled_button(text):
        button = QPushButton(text)
        button.setStyleSheet("""
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                padding: 8px 16px;
                text-align: center;
                text-decoration: none;
                font-size: 14px;
                border-radius: 4px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #357abd;
            }
            QPushButton:pressed {
                background-color: #2a5d8b;
            }
        """)
        return button

    def get_updated_info(self):
        return {
            "description": self.description_edit.toPlainText(),
            "config_path": self.config_path_edit.text(),
            "fast_config_path": self.fast_config_path_edit.text(),
            "model_type": self.model_type_edit.text()
        }


class ConfigEditorDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.cancel_button = None
        self.save_button = None
        self.tabs = None
        self.background_label = None
        self.original_config = config
        self.working_config = copy.deepcopy(self.original_config)
        self.working_config = self.validate_config(self.working_config)
        self.setWindowTitle("模型配置文件编辑器")
        self.setGeometry(100, 100, 1000, 600)
        self.setup_ui()

    @staticmethod
    def validate_config(config):
        model_types = ["vocal_models", "kara_models", "reverb_models", "other_models"]
        for model_type in model_types:
            if model_type not in config:
                config[model_type] = {}
        if "config_paths" not in config:
            config["config_paths"] = {}
        if "model_types" not in config:
            config["model_types"] = {}
        return config

    def setup_ui(self):
        try:
            layout = QVBoxLayout()
            self.tabs = QTabWidget()

            self.setLayout(layout)
            self.set_background_image()
            self.apply_styles()

            for model_type in ["vocal_models", "kara_models", "reverb_models", "other_models"]:
                tab = QWidget()
                tab_layout = QVBoxLayout(tab)
                table = QTableWidget()
                table.setObjectName(model_type)
                self.setup_table(table, model_type)

                add_button = QPushButton("添加新模型")
                add_button.setFixedHeight(40)
                add_button.clicked.connect(lambda checked, t=table, mt=model_type: self.add_new_model(t, mt))

                tab_layout.addWidget(table)
                tab_layout.addWidget(add_button)
                tab_layout.addWidget(table)
                tab_layout.addWidget(add_button)
                if model_type == "vocal_models":
                    self.tabs.addTab(tab, "人声分离模型")
                if model_type == "kara_models":
                    self.tabs.addTab(tab, "和声分离模型")
                if model_type == "reverb_models":
                    self.tabs.addTab(tab, "混响和声分离模型")
                if model_type == "other_models":
                    self.tabs.addTab(tab, "其他模型")

            layout.addWidget(self.tabs)

            # save cancel button
            button_widget = QWidget()
            button_layout = QHBoxLayout(button_widget)
            button_layout.setContentsMargins(0, 0, 0, 0)
            button_layout.setSpacing(10)

            self.save_button = self.create_styled_button("保存改动")
            self.cancel_button = self.create_styled_button("取消改动")
            self.save_button.clicked.connect(self.save_config)
            self.cancel_button.clicked.connect(self.reject)

            button_layout.addWidget(self.save_button)
            button_layout.addWidget(self.cancel_button)

            layout.addWidget(button_widget, 0, Qt.AlignRight | Qt.AlignBottom)

        except Exception as e:
            logger.error(f"Error in setup_ui: {str(e)}")
            logger.error(traceback.format_exc())
            QMessageBox.critical(self, "错误", f"初始化UI时发生错误: {str(e)}")

    def setup_table(self, table, model_type):
        try:
            table.setColumnCount(5)
            table.setHorizontalHeaderLabels(["模型名称", "简述", "移动", "编辑", "删除"])
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
            table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
            table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
            table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
            table.setColumnWidth(2, 80)
            table.setColumnWidth(3, 70)
            table.setColumnWidth(4, 70)
            table.verticalHeader().setDefaultSectionSize(40)

            for model, desc in self.working_config[model_type].items():
                self.add_row_to_table(table, model, desc, model_type)
        except Exception as e:
            logger.error(f"Error in setup_table for {model_type}: {str(e)}")
            logger.error(traceback.format_exc())
            QMessageBox.critical(self, "错误", f"初始化选项页时发生错误: {str(e)}")

    def add_row_to_table(self, table, model, desc, model_type):
        try:
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(model))
            desc_item = QTableWidgetItem(desc)
            desc_item.setToolTip(desc)
            table.setItem(row, 1, desc_item)

            if model != "None":
                move_widget = QWidget()
                move_layout = QHBoxLayout(move_widget)
                move_layout.setContentsMargins(0, 0, 0, 0)
                move_layout.setSpacing(2)

                up_button = self.create_tool_button("▲", "上移")
                down_button = self.create_tool_button("▼", "下移")
                up_button.clicked.connect(lambda checked, t=table, r=row, mt=model_type: self.move_row(t, r, mt, -1))
                down_button.clicked.connect(lambda checked, t=table, r=row, mt=model_type: self.move_row(t, r, mt, 1))
                move_layout.addWidget(up_button)
                move_layout.addWidget(down_button)
                table.setCellWidget(row, 2, move_widget)

                edit_button = self.create_tool_button("编辑", "编辑详细的模型配置")
                edit_button.clicked.connect(lambda checked, t=table, r=row, mt=model_type: self.edit_model(t, r, mt))
                table.setCellWidget(row, 3, edit_button)

                delete_button = self.create_tool_button("删除", "删除该模型配置（不会删除文件）")
                delete_button.clicked.connect(
                    lambda checked, t=table, r=row, mt=model_type: self.delete_model(t, r, mt))
                table.setCellWidget(row, 4, delete_button)
        except Exception as e:
            logger.error(f"Error in add_row_to_table: {str(e)}")
            logger.error(traceback.format_exc())
            QMessageBox.critical(self, "错误", f"添加模型时发生错误: {str(e)}")

    @staticmethod
    def create_tool_button(text, tooltip):
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tooltip)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return button

    @staticmethod
    def create_styled_button(text):
        button = QPushButton(text)
        button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 16px;
                text-align: center;
                text-decoration: none;
                font-size: 14px;
                border-radius: 4px;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b3d;
            }
        """)
        return button

    def move_row(self, table, row, model_type, direction):
        try:
            new_row = row + direction
            if direction == -1 and new_row <= 0:
                logger.info(f"Cannot move row {row} above the first row in {model_type}")
                return
            if 0 < new_row < table.rowCount():
                # Store the data of the rows
                data_row1 = [table.item(row, col).text() if table.item(row, col) else "" for col in range(2)]
                data_row2 = [table.item(new_row, col).text() if table.item(new_row, col) else "" for col in range(2)]

                # Swap the data
                for col in range(2):
                    table.setItem(row, col, QTableWidgetItem(data_row2[col]))
                    table.setItem(new_row, col, QTableWidgetItem(data_row1[col]))

                # Update the config
                self.update_config_from_table(table, model_type)

                logger.info(f"Moved row {row} to {new_row} in {model_type}")
        except Exception as e:
            logger.error(f"Error in move_row: {str(e)}")
            logger.error(traceback.format_exc())
            QMessageBox.critical(self, "错误", f"移动模型时发生错误: {str(e)}")

    def update_config_from_table(self, table, model_type):
        try:
            new_order = {}
            for row in range(table.rowCount()):
                model_name = table.item(row, 0).text()
                description = table.item(row, 1).text()
                new_order[model_name] = description
            self.working_config[model_type] = new_order
            logger.info(f"Updated working config for {model_type}")
        except Exception as e:
            logger.error(f"Error in update_config_from_table: {str(e)}")
            logger.error(traceback.format_exc())
            QMessageBox.critical(self, "错误", f"更新配置文件时发生错误: {str(e)}")

    def edit_model(self, table, row, model_type):
        try:
            model_name = table.item(row, 0).text()
            model_info = table.item(row, 1).text()
            dialog = ModelEditDialog(model_name, model_info, self.working_config, self)
            if dialog.exec_():
                updated_info = dialog.get_updated_info()
                self.working_config[model_type][model_name] = updated_info["description"]
                if "config_paths" not in self.working_config:
                    self.working_config["config_paths"] = {}
                self.working_config["config_paths"][model_name] = [updated_info["config_path"],
                                                                   updated_info["fast_config_path"]]
                if "model_types" not in self.working_config:
                    self.working_config["model_types"] = {}
                self.working_config["model_types"][model_name] = updated_info["model_type"]
                table.setItem(row, 1, QTableWidgetItem(updated_info["description"]))
                logger.info(f"Edited model {model_name} in {model_type}")
        except Exception as e:
            logger.error(f"Error in edit_model: {str(e)}")
            logger.error(traceback.format_exc())
            QMessageBox.critical(self, "错误", f"编辑模型时发生错误: {str(e)}")

    def delete_model(self, table, row, model_type):
        try:
            model_name = table.item(row, 0).text()
            reply = QMessageBox.question(self, '删除模型',
                                         f"你确定要删除 '{model_name}'吗?\n（注：这不会删除你的模型和配置文件）",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                del self.working_config[model_type][model_name]
                if "config_paths" in self.working_config and model_name in self.working_config["config_paths"]:
                    del self.working_config["config_paths"][model_name]
                if "model_types" in self.working_config and model_name in self.working_config["model_types"]:
                    del self.working_config["model_types"][model_name]
                table.removeRow(row)
                self.update_config_from_table(table, model_type)
                logger.info(f"Deleted model {model_name} from {model_type}")
        except Exception as e:
            logger.error(f"Error in delete_model: {str(e)}")
            logger.error(traceback.format_exc())
            QMessageBox.critical(self, "错误", f"删除模型时发生错误: {str(e)}")

    def add_new_model(self, table, model_type):
        try:
            model_name, ok = QInputDialog.getText(self, "添加新模型", "请输入模型名称（放入pretrain）:")
            if ok and model_name and model_name != "None":
                dialog = ModelEditDialog(model_name, "", self.working_config, self)
                if dialog.exec_():
                    updated_info = dialog.get_updated_info()
                    self.working_config[model_type][model_name] = updated_info["description"]
                    if "config_paths" not in self.working_config:
                        self.working_config["config_paths"] = {}
                    self.working_config["config_paths"][model_name] = [updated_info["config_path"],
                                                                       updated_info["fast_config_path"]]
                    if "model_types" not in self.working_config:
                        self.working_config["model_types"] = {}
                    self.working_config["model_types"][model_name] = updated_info["model_type"]
                    self.add_row_to_table(table, model_name, updated_info["description"], model_type)
                    self.update_config_from_table(table, model_type)
                    logger.info(f"Added new model {model_name} to {model_type}")
            elif model_name == "None":
                QMessageBox.warning(self, "无效的模型名称", "你不能添加名为'None'的模型.")
        except Exception as e:
            logger.error(f"Error in add_new_model: {str(e)}")
            logger.error(traceback.format_exc())
            QMessageBox.critical(self, "错误", f"添加新模型时发生错误: {str(e)}")

    def save_config(self):
        try:
            self.original_config.clear()
            self.original_config.update(copy.deepcopy(self.working_config))
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.original_config, f, indent=4)
            logger.info("Configuration saved successfully")
            self.accept()
        except Exception as e:
            logger.error(f"Error in save_config: {str(e)}")
            logger.error(traceback.format_exc())
            QMessageBox.critical(self, "错误", f"保存配置文件时发生错误: {str(e)}")

    def set_background_image(self):
        background = QPixmap(":/images/background2.png")
        if background.isNull():
            print("Failed to load background image")
            return

        overlay = QPixmap(background.size())
        overlay.fill(QColor(255, 255, 255, 128))

        painter = QPainter(background)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.drawPixmap(0, 0, overlay)
        painter.end()

        self.background_label = QLabel(self)
        self.background_label.setPixmap(background)
        self.background_label.setScaledContents(True)
        self.background_label.resize(self.size())
        self.background_label.lower()
        self.setAttribute(Qt.WA_StyledBackground, True)

    def apply_styles(self):
        self.setStyleSheet("""
            QDialog { background-color: #ffffff; }
            QTabWidget::tab-bar { left: 5px; }
            QTabWidget::pane {
            border: 1px solid #cccccc;
            background-color: rgba(255, 255, 255, 200);
            }
            QTabBar::tab {
                background-color: #f0f0f0;
                border: 1px solid #cccccc;
                padding: 5px 10px;
                margin-right: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                border-bottom-color: #ffffff;
            }
            QTableWidget {
                background-color: rgba(255, 255, 255, 100);
                border: 1px solid #cccccc;
                gridline-color: #ececec;
            }
            QTableWidget::item { padding: 5px; }
            QHeaderView::section {
                background-color: #d0f0c0;
                padding: 5px;
                border: 1px solid #cccccc;
                font-weight: bold;
            }
            QPushButton, QToolButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 5px 10px;
                text-align: center;
                text-decoration: none;
                font-size: 12px;
                border-radius: 3px;
            }
            QPushButton:hover, QToolButton:hover { background-color: #45a049; }
        """)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.background_label = None
        self.inference_thread = None
        self.setWindowTitle("MSST GUI Standalone version v1.3.1     by 领航员未鸟")
        self.setGeometry(100, 100, 800, 810)
        self.setWindowIcon(QIcon(":/images/msst-icon.ico"))
        self.setFont(QApplication.font())
        if sys.platform == 'win32':
            import ctypes
            myappid = 'AliceNavigator.msst-GUI-Standalone.v1.3.1'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

        self.config = load_or_create_config()

        # Create SystemInfoThread and connect its signals
        self.system_info_thread = SystemInfoThread()
        self.system_info_thread.info_signal.connect(self.update_output)
        QTimer.singleShot(100, self.print_system_info)

        # Set default input folder
        self.input_folder = os.path.join(os.getcwd(), 'input')
        if not os.path.exists(self.input_folder):
            os.makedirs(self.input_folder)

        if not os.path.exists('pretrain'):
            os.makedirs('pretrain')

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Preset management
        preset_layout = QHBoxLayout()
        self.preset_combo = CustomComboBox()
        self.load_presets()
        preset_layout.addWidget(QLabel("预设文件:"))
        preset_layout.addWidget(self.preset_combo, 1)
        self.preset_combo.currentIndexChanged.connect(self.load_preset_from_combo)

        self.save_preset_button = QPushButton("保存预设")
        self.save_preset_button.clicked.connect(self.save_preset)
        preset_layout.addWidget(self.save_preset_button)
        main_layout.addLayout(preset_layout)

        # Model selection
        model_group = QGroupBox("模块选择")
        model_layout = QVBoxLayout()
        model_group.setLayout(model_layout)

        self.vocal_model_combo = self.create_model_combo(self.config["vocal_models"])
        self.vocal_model_tooltip = self.create_tooltip_label()
        model_layout.addLayout(
            self.create_model_section("人声分离模块:", self.vocal_model_combo, self.vocal_model_tooltip))

        self.kara_model_combo = self.create_model_combo(self.config["kara_models"])
        self.kara_model_tooltip = self.create_tooltip_label()
        model_layout.addLayout(
            self.create_model_section("和声分离模块:", self.kara_model_combo, self.kara_model_tooltip))

        self.reverb_model_combo = self.create_model_combo(self.config["reverb_models"])
        self.reverb_model_tooltip = self.create_tooltip_label()
        model_layout.addLayout(
            self.create_model_section("混响和声分离模块:", self.reverb_model_combo, self.reverb_model_tooltip))

        self.other_model_combo = self.create_model_combo(self.config["other_models"])
        self.other_model_tooltip = self.create_tooltip_label()
        model_layout.addLayout(
            self.create_model_section("其他模块:", self.other_model_combo, self.other_model_tooltip))

        self.update_model_combos()
        main_layout.addWidget(model_group)

        # Inference options and inference env input
        options_layout = QHBoxLayout()
        options_layout.setSpacing(20)  # Increase overall spacing between main elements

        left_options = QHBoxLayout()
        left_options.setSpacing(60)  # Increase spacing between checkboxes

        self.fast_inference_checkbox = QCheckBox("快速推理模式")
        self.fast_inference_checkbox.setToolTip(
            "将以更低的推理参数进行推理，以SDR稍低的代价换来3-4倍的速度提升，适合配置不高或者大批量推理的场合")
        left_options.addWidget(self.fast_inference_checkbox)

        self.force_cpu_checkbox = QCheckBox("CPU推理")
        self.force_cpu_checkbox.setToolTip("即使CUDA可用也强制使用CPU推理")
        left_options.addWidget(self.force_cpu_checkbox)

        self.use_tta_checkbox = QCheckBox("使用TTA")
        self.use_tta_checkbox.setToolTip(
            "使用test time augmentation(TTA). 消耗三倍推理时间，但略微提高推理质量")
        left_options.addWidget(self.use_tta_checkbox)

        options_layout.addLayout(left_options)

        options_layout.addStretch(1)  # Add stretch to push the following elements to the right

        right_options = QHBoxLayout()
        right_options.setSpacing(5)  # Kept the reduced spacing between elements on the right

        # env_input_label = QLabel("Built-in environment")
        # right_options.addWidget(env_input_label)

        options_layout.addLayout(right_options)

        main_layout.addLayout(options_layout)

        # Input folder selection
        folder_layout = QHBoxLayout()
        self.input_folder_button = QPushButton("选择输入文件夹")
        self.input_folder_button.clicked.connect(self.select_input_folder)
        folder_layout.addWidget(self.input_folder_button)

        self.input_folder_display = QLineEdit(self.input_folder)
        self.input_folder_display.setReadOnly(True)
        self.input_folder_display.setToolTip(self.input_folder)
        folder_layout.addWidget(self.input_folder_display, 1)

        main_layout.addLayout(folder_layout)

        # button to open the input folder
        self.open_folder_button = QToolButton()
        self.open_folder_button.setIcon(QIcon(":/images/folder-open.png"))
        self.open_folder_button.setIconSize(QSize(24, 24))
        self.open_folder_button.setToolTip("打开输入文件夹")
        self.open_folder_button.clicked.connect(self.open_input_folder)
        self.open_folder_button.setStyleSheet("""
            QToolButton {
                padding-left: 1px;
            }
        """)
        folder_layout.addWidget(self.open_folder_button)

        # button to open the archive folder
        self.open_archive_button = QToolButton()
        self.open_archive_button.setIcon(QIcon(":/images/document-folder.png"))
        self.open_archive_button.setIconSize(QSize(24, 24))
        self.open_archive_button.setToolTip("打开归档文件夹")
        self.open_archive_button.clicked.connect(self.open_archive_folder)
        self.open_archive_button.setStyleSheet("""
                    QToolButton {
                        padding-left: 1px;
                    }
                """)
        folder_layout.addWidget(self.open_archive_button)

        main_layout.addLayout(folder_layout)

        # Action buttons
        action_layout = QHBoxLayout()
        self.run_button = QPushButton("开始推理")
        self.run_button.clicked.connect(self.run_inference)
        action_layout.addWidget(self.run_button)
        self.archive_button = QPushButton("归档结果")
        self.archive_button.clicked.connect(self.run_archive)
        action_layout.addWidget(self.archive_button)

        # Add Config Editor button
        self.config_editor_button = QPushButton("模型配置编辑器")
        self.config_editor_button.clicked.connect(self.open_config_editor)
        action_layout.addWidget(self.config_editor_button)

        main_layout.addLayout(action_layout)

        # Output console
        self.output_console = QTextEdit()
        self.output_console.setReadOnly(True)
        self.output_console.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #ffffff;
                font-family: 'Courier New', monospace;
                font-size: 12px;
                border: 1px solid #3a3a3a;
            }
        """)
        self.set_background_image()
        font = QFont("Microsoft YaHei Mono", 10)
        if not QFontInfo(font).fixedPitch():
            font = QFont("Noto Sans Mono CJK SC", 10)

        if not QFontInfo(font).fixedPitch():
            # use sys default font if cant find any
            font = QFont()
            font.setStyleHint(QFont.Monospace)
            font.setFixedPitch(True)

        self.output_console.setFont(font)
        main_layout.addWidget(self.output_console)

        # Connect signals
        self.vocal_model_combo.currentIndexChanged.connect(
            lambda: self.update_tooltip(self.vocal_model_combo, self.vocal_model_tooltip))
        self.kara_model_combo.currentIndexChanged.connect(
            lambda: self.update_tooltip(self.kara_model_combo, self.kara_model_tooltip))
        self.reverb_model_combo.currentIndexChanged.connect(
            lambda: self.update_tooltip(self.reverb_model_combo, self.reverb_model_tooltip))
        self.other_model_combo.currentIndexChanged.connect(
            lambda: self.update_tooltip(self.other_model_combo, self.other_model_tooltip))

        # Initial tooltip update
        self.update_tooltip(self.vocal_model_combo, self.vocal_model_tooltip)
        self.update_tooltip(self.kara_model_combo, self.kara_model_tooltip)
        self.update_tooltip(self.reverb_model_combo, self.reverb_model_tooltip)
        self.update_tooltip(self.other_model_combo, self.other_model_tooltip)

        # Set styles
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f0f0;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #cccccc;
                border-radius: 5px;
                margin-top: 1ex;
                padding: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
            }
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 16px;
                text-align: center;
                text-decoration: none;
                font-size: 14px;
                margin: 4px 2px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3e8e41;
                padding-top: 10px;
                padding-bottom: 6px;
            }
            QComboBox {
                padding: 5px;
                border: 1px solid #cccccc;
                border-radius: 3px;
                background-color: white;
                min-width: 6em;
                font-size: 10pt;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left-width: 1px;
                border-left-color: #cccccc;
                border-left-style: solid;
                border-top-right-radius: 3px;
                border-bottom-right-radius: 3px;
                font-size: 10pt;
            }
            QComboBox::down-arrow {
                width: 14px;
                height: 14px;
            }
            QComboBox::down-arrow:on {
                top: 1px;
                left: 1px;
            }
            QCheckBox {
                spacing: 5px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 1px solid #cccccc;
                border-radius: 3px;
            }
            QCheckBox::indicator:unchecked {
                background-color: white;
            }
            QCheckBox::indicator:checked {
                background-color: #4CAF50;
            }
            QTextEdit {
            background-color: rgba(30, 30, 30, 220);
            }
            QGroupBox, QComboBox, QLineEdit {
            background-color: rgba(255, 255, 255, 220);
            }
            QLineEdit {
                padding: 2px 5px;
                border: 1px solid #cccccc;
                border-radius: 3px;
                background-color: white;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #4CAF50;
            }
            QToolButton {
                border: 1px solid #cccccc;
                border-radius: 3px;
            }
            QToolButton:hover {
                border: 1px solid #cccccc;
                border-radius: 3px;
                background-color: #e0e0e0;
            }
            QToolButton:pressed {
                background-color: #d0d0d0;
            }
            QLabel {
                font-size: 12px;
            }
            QCheckBox {
                font-size: 12px;
            }
        """)

        logger.info("MainWindow initialization completed")

    @staticmethod
    def create_model_combo(options):
        combo = CustomComboBox()
        combo.addItems(options.keys())
        for i, (option, tooltip) in enumerate(options.items()):
            combo.setItemData(i, tooltip, Qt.ToolTipRole)
        return combo

    @staticmethod
    def create_tooltip_label():
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMaximumHeight(25)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        label = QLabel()
        label.setWordWrap(True)
        label.setStyleSheet("""
            QLabel {
                background-color: #d0f0c0;
                border: 1px solid #cccccc;
                border-radius: 5px;
                padding: 5px;
                font-size: 11px;
                color: #333333;
            }
        """)

        scroll_area.setWidget(label)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
        """)

        return scroll_area

    @staticmethod
    def create_model_section(label_text, combo, tooltip_label):
        layout = QVBoxLayout()
        label = QLabel(label_text)
        label.setStyleSheet("font-size: 10pt;")
        layout.addWidget(label)
        layout.addWidget(combo)
        layout.addWidget(tooltip_label)
        layout.addSpacing(10)  # Add some space between sections
        return layout

    @staticmethod
    def update_tooltip(combo, tooltip_scroll_area):
        current_index = combo.currentIndex()
        tooltip = combo.itemData(current_index, Qt.ToolTipRole)
        label = tooltip_scroll_area.widget()
        label.setText(tooltip)
        tooltip_scroll_area.setVisible(bool(tooltip))

    def set_background_image(self):
        background = QPixmap(":/images/background3.png")
        if background.isNull():
            print("Failed to load background image")
            return

        overlay = QPixmap(background.size())
        overlay.fill(QColor(255, 255, 255, 128))

        painter = QPainter(background)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.drawPixmap(0, 0, overlay)
        painter.end()

        self.background_label = QLabel(self)
        self.background_label.setPixmap(background)
        self.background_label.setScaledContents(True)
        self.background_label.resize(self.size())
        self.background_label.lower()
        self.setAttribute(Qt.WA_StyledBackground, True)

    def select_input_folder(self):
        logger.info("Selecting input folder")
        folder = QFileDialog.getExistingDirectory(self, "Select Input Folder", self.input_folder)
        if folder:
            self.input_folder = folder
            self.update_input_folder_display()
            logger.info(f"Selected input folder: {folder}")

    def update_input_folder_display(self):
        self.input_folder_display.setText(self.input_folder)
        self.input_folder_display.setToolTip(self.input_folder)
        self.input_folder_display.setCursorPosition(0)

    def open_input_folder(self):
        if os.path.exists(self.input_folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.input_folder))
        else:
            QMessageBox.warning(self, "错误", "输入文件夹不存在")

    def open_archive_folder(self):
        archive_folder = os.path.join(os.getcwd(), 'archive')
        if os.path.exists(archive_folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(archive_folder))
        else:
            QMessageBox.warning(self, "错误", "归档文件夹不存在")

    def load_presets(self):
        logger.info("Loading presets")
        if not os.path.exists('presets'):
            os.makedirs('presets')
            logger.info("Created presets directory")
        preset_files = [f for f in os.listdir('presets') if f.endswith('.json')]
        current_preset = self.preset_combo.currentText()
        self.preset_combo.clear()
        self.preset_combo.addItem("Select a preset")  # Default option
        preset_names = [os.path.splitext(f)[0] for f in preset_files]
        self.preset_combo.addItems(preset_names)
        index = self.preset_combo.findText(current_preset)
        if index >= 0:
            self.preset_combo.setCurrentIndex(index)
        logger.debug(f"Loaded presets: {preset_names}")

    def load_preset_from_combo(self, index):
        preset_name = self.preset_combo.itemText(index)
        if preset_name and preset_name != "Select a preset":
            self.load_preset(preset_name)

    @staticmethod
    def convert_none_to_false(value):
        return False if value == "None" else value

    @staticmethod
    def convert_false_to_none(value):
        return "None" if value is False else value

    def load_preset(self, preset_name):
        if not preset_name:
            logger.warning("Attempted to load preset with empty name")
            return

        logger.info(f"Loading preset: {preset_name}")
        try:
            with open(f"presets/{preset_name}.json", "r") as f:
                preset = json.load(f)
            self.vocal_model_combo.setCurrentText(self.convert_false_to_none(preset["vocal_model_name"]))
            self.kara_model_combo.setCurrentText(self.convert_false_to_none(preset["kara_model_name"]))
            self.reverb_model_combo.setCurrentText(self.convert_false_to_none(preset["reverb_model_name"]))
            self.other_model_combo.setCurrentText(self.convert_false_to_none(preset["other_model_name"]))
            self.fast_inference_checkbox.setChecked(preset.get("if_fast", True))
            self.force_cpu_checkbox.setChecked(preset.get("force_cpu", False))
            self.use_tta_checkbox.setChecked(preset.get("use_tta", False))
            logger.info(f"Preset loaded successfully: {preset_name}")
        except FileNotFoundError:
            logger.error(f"Preset file not found: {preset_name}")
            QMessageBox.warning(self, "错误", f"预设文件 '{preset_name}' 不存在")
        except Exception as e:
            logger.error(f"Failed to load preset: {str(e)}", exc_info=True)
            QMessageBox.warning(self, "错误", f"读取配置文件失败: {str(e)}")

    def save_preset(self):
        logger.info("Saving preset")
        name, ok = QInputDialog.getText(self, "保存预设", "请输入预设名:")
        if ok:
            if name.strip():
                preset = {
                    "vocal_model_name": self.convert_none_to_false(self.vocal_model_combo.currentText()),
                    "kara_model_name": self.convert_none_to_false(self.kara_model_combo.currentText()),
                    "reverb_model_name": self.convert_none_to_false(self.reverb_model_combo.currentText()),
                    "other_model_name": self.convert_none_to_false(self.other_model_combo.currentText()),
                    "if_fast": self.fast_inference_checkbox.isChecked(),
                    "force_cpu": self.force_cpu_checkbox.isChecked(),
                    "use_tta": self.use_tta_checkbox.isChecked(),
                    "preset_name": name
                }
                if not os.path.exists('presets'):
                    os.makedirs('presets')
                    logger.info("Created presets directory")
                with open(f"presets/{name}.json", "w") as f:
                    json.dump(preset, f, indent=4)
                self.load_presets()
                index = self.preset_combo.findText(name)
                if index >= 0:
                    self.preset_combo.setCurrentIndex(index)
                QMessageBox.information(self, "预设已保存", f"已将现有配置保存为预设：'{name}'")
                logger.info(f"Preset saved: {name}")
            else:
                logger.warning("Empty preset name provided")
                QMessageBox.warning(self, "保存失败", "预设名不能为空！")
        else:
            logger.info("Preset save cancelled")

    def get_config_path(self, model, is_fast):
        config_paths = self.config["config_paths"].get(model, [None, None])
        return config_paths[1] if is_fast else config_paths[0]

    def get_model_type(self, model):
        return self.config["model_types"].get(model, "unknown")

    @staticmethod
    def safe_path(path):
        path = path.strip("'\"")
        path = os.path.normpath(path)
        return shlex.quote(path) if ' ' in path else path

    def run_inference(self):
        logger.info("Starting inference process")

        if not os.path.exists(self.input_folder):
            logger.warning("Input folder does not exist")
            QMessageBox.warning(self, "错误", "输入文件夹不存在，请确认路径是否正确")
            return

        if not os.listdir(self.input_folder):
            QMessageBox.warning(self, "错误",
                                "输入文件夹是空的，请先添加需处理的音频文件！")
            return

        fast_inference = self.fast_inference_checkbox.isChecked()
        force_cpu = self.force_cpu_checkbox.isChecked()
        use_tta = self.use_tta_checkbox.isChecked()
        commands = []
        current_input_folder = self.safe_path(self.input_folder)

        def add_command(model, store_dir):
            nonlocal current_input_folder
            if model != "None":
                config_path = self.get_config_path(model, fast_inference)
                model_type = self.get_model_type(model)
                model_path = f"pretrain/{model}"

                if config_path and model_type != "unknown":
                    args = [
                        "--start_check_point", self.safe_path(os.path.join("pretrain", model)),
                        "--model_type", model_type,
                        "--config_path", self.safe_path(config_path),
                        "--input_folder", current_input_folder,
                        "--store_dir", store_dir,
                        "--extract_instrumental"
                    ]

                    if force_cpu:
                        args.append("--force_cpu")
                    if use_tta:
                        args.append("--use_tta")

                    commands.append((args, store_dir))
                    current_input_folder = store_dir
                    logger.info(f"Added command for {model}: {args}")
                else:
                    logger.warning(f"No config file or unknown model type for model: {model}")

        add_command(self.vocal_model_combo.currentText(), "separation_results")
        add_command(self.kara_model_combo.currentText(), "karaoke_results")
        add_command(self.reverb_model_combo.currentText(), "deverb_results")
        add_command(self.other_model_combo.currentText(), "other_results")

        logger.info(f"Inference commands: {commands}")

        self.output_console.clear()
        self.update_output("启动推理.........", color='cyan')

        self.inference_thread = InferenceThread(commands, self.input_folder)
        self.inference_thread.update_signal.connect(self.process_inference_output)
        self.inference_thread.finished_signal.connect(self.inference_finished)
        self.inference_thread.file_organization_signal.connect(self.file_organization_completed)
        self.inference_thread.start()

        self.run_button.setText("终止推理")
        self.run_button.setStyleSheet("""
            QPushButton {
                background-color: #FF4136;
                color: white;
                border: none;
                padding: 8px 16px;
                text-align: center;
                text-decoration: none;
                font-size: 14px;
                margin: 4px 2px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #E02F26;
            }
            QPushButton:pressed {
                background-color: #C7291F;
                padding-top: 10px;
                padding-bottom: 6px;
            }
        """)
        self.run_button.clicked.disconnect()
        self.run_button.clicked.connect(self.stop_inference)

    def file_organization_completed(self, moved_files, time_taken):
        self.update_output(f"Organized {moved_files} instrumental files in {time_taken:.2f} seconds", color='green')

    def stop_inference(self):
        if hasattr(self, 'inference_thread') and self.inference_thread.isRunning():
            logger.info("Stopping inference process")
            self.update_output("\n正在强制终止推理进程，请稍后...", color='yellow')
            self.inference_thread.stop()
        self.reset_run_button()

    def reset_run_button(self):
        self.run_button.setText("开始推理")
        self.run_button.setStyleSheet("")  # This will reset to the default style defined in setStyleSheet
        self.run_button.clicked.disconnect()
        self.run_button.clicked.connect(self.run_inference)

    def process_inference_output(self, text, is_progress_update):
        cursor = self.output_console.textCursor()
        cursor.movePosition(QTextCursor.End)

        if is_progress_update:
            console_width = self.output_console.width() // 8
            percentage_match = re.search(r'(\d+)%', text)
            percentage = int(percentage_match.group(1)) if percentage_match else 0

            bar_length = console_width - 45  # Adjust display length
            filled_length = int(bar_length * percentage / 100)
            bar = "█" * filled_length + "-" * (bar_length - filled_length)

            iterations_match = re.search(r'(\d+)/(\d+)', text)
            iterations_info = f"{iterations_match.group(1)}/{iterations_match.group(2)}" if iterations_match else ""

            speed_match = re.search(r'(\d+\.\d+)it/s', text)
            speed = speed_match.group(0) if speed_match else ""

            new_text = f"\rProcessing: |{bar}| {percentage:3d}% {iterations_info} {speed}"
            strip_text = new_text.strip()

            cursor.movePosition(QTextCursor.StartOfLine, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
            self.update_output(strip_text, color='#ffa500', auto_newline=False)

            if iterations_info == '':
                new_text = f"\rProcessing: |" + "█" * bar_length + f"| 100% {speed} Complete!"
                strip_text = new_text.strip()
                cursor.movePosition(QTextCursor.StartOfLine, QTextCursor.KeepAnchor)
                cursor.removeSelectedText()
                self.update_output(strip_text, color='#ffa500', auto_newline=False)
                self.update_output("\n", auto_newline=False)

        else:
            if text.startswith("使用模块:"):
                self.print_separator(char='=')
                self.update_output(text, color='#6e71ff', bold=True)
            elif text.startswith("参数:"):
                self.update_output(text, color='yellow', italic=True)
                self.print_separator(char='-')
            elif "error" in text.lower():
                self.update_output(text, color='red')
            elif "warning" in text.lower():
                self.update_output(text, color='orange')
            elif text.startswith("Starting processing track:"):
                self.update_output("\n" + text, color='#00ff00')
            else:
                self.update_output(text)

        self.output_console.setTextCursor(cursor)
        self.output_console.ensureCursorVisible()

    def inference_finished(self, summary):
        self.reset_run_button()
        self.print_separator(char='=')
        if summary["status"] == "completed":
            self.update_output("推理完成!", color='green', bold=True)
        elif summary["status"] == "stopped":
            self.update_output("推理进程已由用户强制终止", color='yellow', bold=True)
        elif summary["status"] == "error":
            self.update_output("推理失败！", color='red', bold=True)
            self.update_output(f"错误: {summary.get('error_message', 'Unknown error')}", color='red')
        else:
            self.update_output("推理进程已结束，但回报 unknown 状态", color='orange', bold=True)

        self.print_separator(char='=')
        # self.update_output("总结:", color='#6e71ff', bold=True)
        self.update_output(f"总计处理文件: {summary['total_files']} 个", color='#6e71ff')
        self.update_output(f"总计消耗时间: {summary['total_time']:.2f} 秒", color='#6e71ff')
        self.update_output("使用的模块及其保存目录:", color='#6e71ff')
        for module_name, store_dir in summary['modules']:
            self.update_output(f"- {module_name}: {store_dir} ", color='#6e71ff')
        if summary['errors'] > 0:
            self.update_output(f"发生错误计数: {summary['errors']}", color='red')
        # self.print_separator(char='=')
        logger.info(f"Inference summary displayed. Status: {summary['status']}, Total files: {summary['total_files']}")

    def update_output(self, text, color='white', bold=False, italic=False, auto_newline=True):
        cursor = self.output_console.textCursor()
        format = QTextCharFormat()
        format.setForeground(QColor(color))
        if bold:
            format.setFontWeight(QFont.Bold)
        if italic:
            format.setFontItalic(True)
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text + ('\n' if auto_newline and not text.startswith("\r") else ''), format)
        self.output_console.setTextCursor(cursor)
        self.output_console.ensureCursorVisible()

    def print_separator(self, char='-'):
        self.update_output(char * 80, color='gray')

    def run_archive(self):
        logger.info("Starting archive process")

        self.output_console.clear()
        self.update_output("开始进行归档处理...", color='green')
        self.print_separator()

        def archive_output_callback(text):
            self.update_output(text, color='#6e71ff')

        archive_folders(output_callback=archive_output_callback)

        logger.info("Archive process completed")
        self.print_separator()
        self.update_output("归档完成！", color='green')
        self.print_separator()

    def open_config_editor(self):
        dialog = ConfigEditorDialog(self.config, self)
        if dialog.exec_():
            self.config = load_or_create_config()  # Reload the config from file
            self.update_model_combos()

    def update_model_combos(self):
        self.update_single_combo(self.vocal_model_combo, self.vocal_model_tooltip, self.config["vocal_models"])
        self.update_single_combo(self.kara_model_combo, self.kara_model_tooltip, self.config["kara_models"])
        self.update_single_combo(self.reverb_model_combo, self.reverb_model_tooltip, self.config["reverb_models"])
        self.update_single_combo(self.other_model_combo, self.other_model_tooltip, self.config["other_models"])

    def update_single_combo(self, combo, tooltip_label, options):
        current_text = combo.currentText()
        combo.clear()
        combo.addItems(options.keys())
        for i, (option, tooltip) in enumerate(options.items()):
            combo.setItemData(i, tooltip, Qt.ToolTipRole)
        index = combo.findText(current_text)
        if index >= 0:
            combo.setCurrentIndex(index)
        self.update_tooltip(combo, tooltip_label)

    def print_system_info(self):
        self.output_console.clear()
        self.system_info_thread.start()

    def print_with_delay(self, text, color='white', bold=False, italic=False, auto_newline=True, delay=10):
        QMetaObject.invokeMethod(self.system_info_thread, 'print_with_delay',
                                 Qt.QueuedConnection,
                                 Q_ARG(str, text),
                                 Q_ARG(str, color),
                                 Q_ARG(bool, bold),
                                 Q_ARG(bool, italic),
                                 Q_ARG(bool, auto_newline),
                                 Q_ARG(int, delay))


if __name__ == "__main__":
    logger.info("Starting application")
    app = QApplication(sys.argv)
    remove_screen_splash()
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
