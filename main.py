import sys
import random
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QPushButton, QListWidget, QListWidgetItem, QLabel, 
                            QFileDialog, QMessageBox, QLineEdit, QSlider, QScrollArea)
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent, QAudioProbe
from PyQt5.QtCore import QUrl, Qt, QThread, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve, QPoint, QSize, QRect, pyqtProperty, QTimerEvent
from PyQt5.QtGui import QPixmap, QIcon, QPainter, QLinearGradient, QColor, QPalette, QTransform
from PyQt5.QtOpenGL import QGLWidget
import requests
from io import BytesIO
import threading
import queue
import time
from functools import partial
import urllib3
import warnings
from requests.packages.urllib3.exceptions import InsecureRequestWarning
import numpy as np
from scipy.fft import fft
import struct
from OpenGL.GL import *
from OpenGL.GLU import *

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.simplefilter('ignore', InsecureRequestWarning)

# 添加自定义的旋转标签类
class RotateLabel(QLabel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._rotation = 0
        self._pixmap = None

    @pyqtProperty(float)
    def rotation(self):
        return self._rotation

    @rotation.setter
    def rotation(self, angle):
        self._rotation = angle
        self.update()

    def setPixmap(self, pixmap):
        self._pixmap = pixmap
        super().setPixmap(self._pixmap)

    def paintEvent(self, event):
        if self._pixmap:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            
            # 设置旋转中心点
            center = self.rect().center()
            painter.translate(center)
            painter.rotate(self._rotation)
            painter.translate(-center)
            
            # 绘制图片
            super().paintEvent(event)
        else:
            super().paintEvent(event)

class Cache:
    def __init__(self):
        self.lyrics_cache = {}
        self.cover_cache = {}
        self.max_size = 20  # 最大缓存数量

    def add_lyrics(self, url, lyrics):
        if len(self.lyrics_cache) >= self.max_size:
            self.lyrics_cache.pop(next(iter(self.lyrics_cache)))
        self.lyrics_cache[url] = lyrics

    def add_cover(self, url, pixmap):
        if len(self.cover_cache) >= self.max_size:
            self.cover_cache.pop(next(iter(self.cover_cache)))
        self.cover_cache[url] = pixmap

    def get_lyrics(self, url):
        return self.lyrics_cache.get(url)

    def get_cover(self, url):
        return self.cover_cache.get(url)

class AsyncLoader(QThread):
    lyrics_loaded = pyqtSignal(str, list)  # 歌词加载信号
    cover_loaded = pyqtSignal(str, QPixmap)  # 封面加载信号
    
    def __init__(self, cache):
        super().__init__()
        self.cache = cache
        self.queue = queue.Queue()
        self.running = True

    def parse_lyrics(self, lrc_text):  # 添加歌词解析方法
        lyrics = []
        lines = lrc_text.split('\n')
        for line in lines:
            if '[' in line and ']' in line:
                time_str = line[line.find('[') + 1:line.find(']')]
                try:
                    if '.' in time_str:
                        m, s = time_str.split(':')
                        s, ms = s.split('.')
                        time = int(m) * 60000 + int(s) * 1000 + int(ms) * 10
                    else:
                        m, s = time_str.split(':')
                        time = int(m) * 60000 + int(s) * 1000
                    text = line[line.find(']') + 1:].strip()
                    if text:
                        lyrics.append((time, text))
                except:
                    continue
        return sorted(lyrics)

    def run(self):
        while self.running:
            try:
                task = self.queue.get(timeout=1)
                if task:
                    task_type, url = task
                    if task_type == 'lyrics':
                        self.load_lyrics(url)
                    elif task_type == 'cover':
                        self.load_cover(url)
            except queue.Empty:
                continue

    def load_lyrics(self, url):
        try:
            # 添加重试机制和超时设置
            session = requests.Session()
            retries = 3
            while retries > 0:
                try:
                    response = session.get(url, timeout=5, verify=False)  # 禁用SSL验证
                    if response.status_code == 200:
                        lyrics = self.parse_lyrics(response.text)
                        self.cache.add_lyrics(url, lyrics)
                        self.lyrics_loaded.emit(url, lyrics)
                        break
                except requests.RequestException:
                    retries -= 1
                    if retries == 0:
                        print(f"加载歌词失败，已重试3次：{url}")
                    time.sleep(1)  # 等待1秒后重试
        except Exception as e:
            print(f"加载歌词失败：{str(e)}")

    def load_cover(self, url):
        try:
            session = requests.Session()
            retries = 3
            while retries > 0:
                try:
                    response = session.get(url, timeout=5, verify=False)
                    if response.status_code == 200:
                        image_data = BytesIO(response.content)
                        pixmap = QPixmap()
                        pixmap.loadFromData(image_data.getvalue())
                        scaled_pixmap = pixmap.scaled(300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        self.cache.add_cover(url, scaled_pixmap)
                        self.cover_loaded.emit(url, scaled_pixmap)
                        break
                except requests.RequestException:
                    retries -= 1
                    if retries == 0:
                        print(f"加载封面失败，已重试3次：{url}")
                    time.sleep(1)  # 等待1秒后重试
        except Exception as e:
            print(f"加载封面失：{str(e)}")

    def add_task(self, task_type, url):
        self.queue.put((task_type, url))

    def stop(self):
        self.running = False

# 修改 AudioVisualizer 类
class AudioVisualizer(QGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(100)
        self.bars = 64  # 频谱条数
        self.spectrum_data = np.zeros(self.bars)
        self.prev_spectrum = np.zeros(self.bars)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(16)  # 约60fps
        
    def initializeGL(self):
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glClearColor(0.0, 0.0, 0.0, 0.0)
        
    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, w, h, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        
    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        
        width = self.width()
        height = self.height()
        bar_width = width / self.bars
        bar_spacing = 2
        
        for i in range(self.bars):
            # 添加一些随机波动
            value = self.spectrum_data[i] * (0.95 + 0.1 * np.random.random())
            bar_height = value * height * 0.8
            
            # 计算渐变色
            hue = (i / self.bars) * 0.3 + 0.5
            color = QColor.fromHsvF(hue, 0.8, 0.9)
            
            x = i * bar_width + bar_spacing
            
            # 绘制频谱条
            glBegin(GL_QUADS)
            glColor4f(color.redF(), color.greenF(), color.blueF(), 0.8)
            glVertex2f(x, height)
            glVertex2f(x + bar_width - bar_spacing * 2, height)
            glVertex2f(x + bar_width - bar_spacing * 2, height - bar_height)
            glVertex2f(x, height - bar_height)
            
            # 绘制顶部光晕
            glow_height = 5
            glColor4f(color.redF(), color.greenF(), color.blueF(), 0.3)
            glVertex2f(x, height - bar_height - glow_height)
            glVertex2f(x + bar_width - bar_spacing * 2, height - bar_height - glow_height)
            glVertex2f(x + bar_width - bar_spacing * 2, height - bar_height)
            glVertex2f(x, height - bar_height)
            glEnd()
    
    def update_spectrum(self, data):
        try:
            # 生成模拟频谱数据
            target = np.abs(np.random.normal(0, 0.3, self.bars))
            target = np.clip(target, 0, 1)
            
            # 平滑过渡
            smooth_factor = 0.3
            self.spectrum_data = self.spectrum_data * (1 - smooth_factor) + target * smooth_factor
            
            # 确保数据范围在0-1之间
            self.spectrum_data = np.clip(self.spectrum_data, 0, 1)
            
        except Exception as e:
            print(f"频谱更新错误: {str(e)}")

class MusicPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.player = QMediaPlayer()
        self.current_lyrics = []
        self.current_lyric_index = -1
        self.current_music_url = None
        
        # 创建所有控件
        self.search_input = QLineEdit()
        self.search_btn = QPushButton('搜索')
        self.online_list = QListWidget()
        self.lyrics_label = QLabel()
        self.playing_status = QLabel()
        self.time_label = QLabel('00:00/00:00')
        self.progress_slider = QSlider(Qt.Horizontal)
        self.volume_slider = QSlider(Qt.Horizontal)
        self.prev_btn = QPushButton('上一首')
        self.play_btn = QPushButton('播放/暂停')
        self.stop_btn = QPushButton('停止')
        self.next_btn = QPushButton('下一首')
        self.download_btn = QPushButton('下载')
        self.mode_btn = QPushButton('顺序播放')
        self.status_label = QLabel()
        
        # 创建自定义的旋转标签
        self.cover_mask = RotateLabel()
        self.cover_mask.setObjectName("coverMask")
        self.cover_mask.setFixedSize(300, 300)
        
        # 创建旋转动画
        self.cover_animation = QPropertyAnimation(self.cover_mask, b"rotation")
        self.cover_animation.setDuration(20000)  # 20秒转一圈
        self.cover_animation.setStartValue(0)
        self.cover_animation.setEndValue(360)
        self.cover_animation.setLoopCount(-1)  # 无限循环
        
        # 添加缓存和异步加载器
        self.cache = Cache()
        self.loader = AsyncLoader(self.cache)
        self.loader.lyrics_loaded.connect(self.on_lyrics_loaded)
        self.loader.cover_loaded.connect(self.on_cover_loaded)
        self.loader.start()
        
        # 添加防抖动计时器
        self.lyrics_update_timer = QTimer()
        self.lyrics_update_timer.setSingleShot(True)
        self.lyrics_update_timer.timeout.connect(lambda: self.update_lyrics_display(self.player.position()))

        self.play_mode = 'sequence'
        
        # 创建音频探针
        self.audio_probe = QAudioProbe()
        self.audio_probe.audioBufferProbed.connect(self.process_audio)
        
        # 创建可视化组件
        self.visualizer = AudioVisualizer()
        
        # 初始化UI
        self.init_ui()
        self.show()

    def init_ui(self):
        # 设置窗口背景渐变
        self.setAutoFillBackground(True)
        palette = self.palette()
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0.0, QColor('#1a2a6c'))
        gradient.setColorAt(0.5, QColor('#b21f1f'))
        gradient.setColorAt(1.0, QColor('#fdbb2d'))
        palette.setBrush(QPalette.Window, gradient)
        self.setPalette(palette)

        # 设置音量滑块的范围和初始值
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(50)
        self.player.setVolume(50)

        # 设置封面标签的固定大小
        self.cover_mask.setFixedSize(300, 300)
        self.cover_mask.setAlignment(Qt.AlignCenter)

        # 布局使用更大的边距和间距
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(30)
        
        # 左侧面板（搜索和列表）- 占据30%宽度
        left_panel = QWidget()
        left_panel.setObjectName("leftPanel")
        left_panel.setFixedWidth(300)  # 固定宽度
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(15, 15, 15, 15)
        left_layout.setSpacing(15)
        
        # 搜索区域美化
        search_widget = QWidget()
        search_widget.setObjectName("searchWidget")
        search_layout = QHBoxLayout(search_widget)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(10)
        
        self.search_input.setPlaceholderText('🔍 搜索音乐...')
        self.search_input.setObjectName("searchInput")
        self.search_btn.setObjectName("searchButton")
        self.search_btn.setCursor(Qt.PointingHandCursor)  # 鼠标悬停显示手型
        
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_btn)
        
        # 音乐列表美化
        self.online_list.setObjectName("musicList")
        self.online_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # 隐藏滚动条
        
        left_layout.addWidget(search_widget)
        left_layout.addWidget(self.online_list, 1)  # 列表占据剩余空间
        
        # 右侧面板 - 占据70%宽度
        right_panel = QWidget()
        right_panel.setObjectName("rightPanel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(20)
        
        # 上部分：封面和歌词并排显示
        upper_widget = QWidget()
        upper_layout = QHBoxLayout(upper_widget)
        upper_layout.setContentsMargins(0, 0, 0, 0)
        upper_layout.setSpacing(30)  # 增加间距
        
        # 封面部分（左侧）
        cover_container = QWidget()
        cover_container.setObjectName("coverContainer")
        cover_layout = QVBoxLayout(cover_container)
        cover_layout.setContentsMargins(10, 10, 10, 10)
        cover_layout.addWidget(self.cover_mask, 0, Qt.AlignCenter)
        
        # 歌词部分（右侧）
        lyrics_container = QWidget()
        lyrics_container.setObjectName("lyricsContainer")
        lyrics_layout = QVBoxLayout(lyrics_container)
        lyrics_layout.setContentsMargins(15, 15, 15, 15)
        self.lyrics_label.setAlignment(Qt.AlignCenter)
        lyrics_layout.addWidget(self.lyrics_label)
        
        upper_layout.addWidget(cover_container, 4)  # 4:6 的比例
        upper_layout.addWidget(lyrics_container, 6)
        
        # 控制面板
        control_panel = QWidget()
        control_panel.setObjectName("controlPanel")
        control_layout = QVBoxLayout(control_panel)
        control_layout.setSpacing(15)
        
        # 播放状态和进度条
        status_progress = QVBoxLayout()
        status_progress.addWidget(self.playing_status)
        
        # 进度条
        progress_container = QWidget()
        progress_container.setObjectName("progressContainer")
        progress_layout = QHBoxLayout(progress_container)
        progress_layout.setContentsMargins(10, 5, 10, 5)
        progress_layout.addWidget(self.time_label)
        progress_layout.addWidget(self.progress_slider)
        
        status_progress.addWidget(progress_container)
        
        # 频谱显示器
        visualizer_container = QWidget()
        visualizer_container.setObjectName("visualizerContainer")
        visualizer_layout = QVBoxLayout(visualizer_container)
        visualizer_layout.setContentsMargins(5, 5, 5, 5)
        visualizer_layout.addWidget(self.visualizer)
        
        # 创建按钮容器
        buttons_container = QWidget()
        buttons_container.setObjectName("buttonsContainer")
        buttons_main_layout = QVBoxLayout(buttons_container)
        buttons_main_layout.setSpacing(15)

        # 主控制按钮（上一首、播放、下一首）
        main_buttons = QHBoxLayout()
        main_buttons.setSpacing(25)  # 增加间距
        main_buttons.setAlignment(Qt.AlignCenter)
        
        # 调整主控制按钮尺寸
        self.prev_btn.setFixedSize(120, 45)  # 增加宽度和高度
        self.play_btn.setFixedSize(140, 45)  # 播放按钮稍大
        self.next_btn.setFixedSize(120, 45)
        
        # 设置按钮文本
        self.prev_btn.setText('⏮ 上一首')
        self.play_btn.setText('▶ 播放')
        self.next_btn.setText('下一首 ⏭')
        
        main_buttons.addWidget(self.prev_btn)
        main_buttons.addWidget(self.play_btn)
        main_buttons.addWidget(self.next_btn)

        # 功能按钮（停止、下载、播放模式）
        function_buttons = QHBoxLayout()
        function_buttons.setSpacing(20)  # 增加间距
        function_buttons.setAlignment(Qt.AlignCenter)
        
        # 设置功能按钮文本和图标
        self.stop_btn.setText('⏹ 停止')
        self.download_btn.setText('💾 下载')
        self.mode_btn.setText('🔁 顺序播放')
        
        # 调整功能按钮尺寸
        for btn in [self.stop_btn, self.download_btn, self.mode_btn]:
            btn.setFixedSize(130, 40)  # 增加宽度
            function_buttons.addWidget(btn)

        # 添加到按钮布局
        buttons_main_layout.addLayout(main_buttons)
        buttons_main_layout.addLayout(function_buttons)

        # 为所有按钮添加动画效果
        for btn in [self.prev_btn, self.play_btn, self.next_btn, 
                    self.stop_btn, self.download_btn, self.mode_btn]:
            btn.setObjectName("controlButton")
            btn.setCursor(Qt.PointingHandCursor)
            self.create_button_animation(btn)
        
        # 音量控制
        volume_widget = QWidget()
        volume_widget.setObjectName("volumeWidget")
        volume_layout = QHBoxLayout(volume_widget)
        volume_layout.setContentsMargins(10, 0, 10, 0)
        
        # 音量图标和标签
        volume_label = QLabel("🔊")
        volume_label.setObjectName("volumeLabel")
        
        # 修改音量滑块
        self.volume_slider.setFixedWidth(100)  # 设置固定宽度
        self.volume_slider.setOrientation(Qt.Horizontal)
        
        # 音量数值显示
        self.volume_value = QLabel("50%")
        self.volume_value.setObjectName("volumeValue")
        
        volume_layout.addWidget(volume_label)
        volume_layout.addWidget(self.volume_slider)
        volume_layout.addWidget(self.volume_value)
        volume_layout.addStretch()  # 添加弹性空间
        
        # 添加到控制布局
        control_layout.addLayout(status_progress)
        control_layout.addWidget(visualizer_container)
        control_layout.addWidget(buttons_container)
        control_layout.addWidget(volume_widget)
        
        # 组装右侧面板
        right_layout.addWidget(upper_widget)
        right_layout.addWidget(control_panel)
        
        # 将左右面板添加到主布局
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)
        
        # 设置主窗口
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)
        
        # 设置窗口属性
        self.setWindowTitle('春日部的告别')
        self.setMinimumSize(1200, 800)  # 设置最小窗口大小
        
        # 应用样式
        self.apply_style()

        # 绑定事
        self.search_btn.clicked.connect(self.search_music)
        self.search_input.returnPressed.connect(self.search_music)  # 添加回车搜索
        self.play_btn.clicked.connect(self.toggle_play_pause)
        self.stop_btn.clicked.connect(self.stop_music)
        self.prev_btn.clicked.connect(self.play_previous)
        self.next_btn.clicked.connect(self.play_next)
        self.online_list.itemDoubleClicked.connect(self.play_online_music)
        self.progress_slider.sliderMoved.connect(self.set_position)
        self.volume_slider.valueChanged.connect(self.set_volume)
        self.player.positionChanged.connect(self.update_position)
        self.player.durationChanged.connect(self.update_duration)
        self.mode_btn.clicked.connect(self.toggle_play_mode)
        self.player.mediaStatusChanged.connect(self.on_media_status_changed)
        self.download_btn.clicked.connect(self.download_current_music)
        
        # 加载推荐音乐
        self.load_recommended_music()

    def apply_style(self):
        self.setStyleSheet("""
            /* 主窗口背景 */
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                          stop:0 #2c3e50, stop:0.5 #3498db, stop:1 #2980b9);
            }
            
            /* 左侧面板 */
            #leftPanel {
                background: rgba(44, 62, 80, 0.7);
                border-radius: 20px;
                border: 1px solid rgba(255, 255, 255, 0.1);
                padding: 10px;
                margin: 5px;
            }
            
            /* 搜索框 */
            #searchInput {
                background: rgba(255, 255, 255, 0.1);
                border: 2px solid rgba(255, 255, 255, 0.1);
                border-radius: 25px;
                padding: 12px 20px;
                color: white;
                font-size: 14px;
                font-weight: bold;
            }
            
            #searchInput:focus {
                background: rgba(255, 255, 255, 0.15);
                border: 2px solid rgba(52, 152, 219, 0.5);
            }
            
            /* 搜索按钮 */
            #searchButton {
                background: #3498db;
                border: none;
                border-radius: 25px;
                padding: 12px 25px;
                color: white;
                font-weight: bold;
                font-size: 14px;
                min-width: 100px;
            }
            
            #searchButton:hover {
                background: #2980b9;
                transform: translateY(-2px);
            }
            
            /* 音乐列表 */
            #musicList {
                background: transparent;
                border: none;
                padding: 10px;
            }
            
            #musicList::item {
                background: rgba(255, 255, 255, 0.05);
                border-radius: 12px;
                padding: 15px;
                margin: 5px 0;
                color: white;
                font-size: 14px;
            }
            
            #musicList::item:selected {
                background: rgba(52, 152, 219, 0.3);
                border: 1px solid rgba(52, 152, 219, 0.5);
            }
            
            #musicList::item:hover {
                background: rgba(255, 255, 255, 0.1);
                transform: translateX(5px);
            }
            
            /* 右侧面板 */
            #rightPanel {
                background: rgba(44, 62, 80, 0.7);
                border-radius: 20px;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
            
            /* 封面容器 */
            #coverContainer {
                background: rgba(0, 0, 0, 0.2);
                border-radius: 20px;
                padding: 20px;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
            
            /* 歌词容器 */
            #lyricsContainer {
                background: rgba(0, 0, 0, 0.2);
                border-radius: 20px;
                padding: 20px;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
            
            /* 控制面板 */
            #controlPanel {
                background: rgba(0, 0, 0, 0.2);
                border-radius: 20px;
                padding: 20px;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
            
            /* 进度条容器 */
            #progressContainer {
                background: rgba(255, 255, 255, 0.05);
                border-radius: 15px;
                padding: 10px;
                margin: 10px 0;
            }
            
            /* 进度条 */
            QSlider::groove:horizontal {
                height: 8px;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 4px;
            }
            
            QSlider::handle:horizontal {
                background: #3498db;
                border: 2px solid white;
                width: 16px;
                height: 16px;
                margin: -4px 0;
                border-radius: 8px;
            }
            
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                          stop:0 #3498db, stop:1 #2ecc71);
                border-radius: 4px;
            }
            
            /* 控制按钮 */
            #controlButton {
                background: rgba(52, 152, 219, 0.8);
                border: none;
                border-radius: 22px;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 5px 15px;
                margin: 5px;
                text-align: center;
                min-width: 120px;
                letter-spacing: 1px;  /* 增加字间距 */
            }
            
            #controlButton:hover {
                background: rgba(41, 128, 185, 0.9);
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2);
            }
            
            /* 播放状态 */
            #playingStatus {
                color: white;
                font-size: 16px;
                font-weight: bold;
                padding: 10px;
                text-align: center;
            }
            
            /* 时间标签 */
            #timeLabel {
                color: white;
                font-size: 12px;
                min-width: 80px;
                padding: 0 10px;
            }
            
            /* 音量控制 */
            #volumeWidget {
                background: rgba(255, 255, 255, 0.05);
                border-radius: 20px;
                padding: 5px 15px;
                margin: 5px 0;
            }
            
            #volumeLabel {
                color: white;
                font-size: 16px;
                padding: 0 5px;
            }
            
            #volumeValue {
                color: white;
                font-size: 12px;
                min-width: 40px;
                padding: 0 5px;
            }
            
            /* 音量滑块样式 */
            #volumeWidget QSlider::groove:horizontal {
                height: 4px;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 2px;
            }
            
            #volumeWidget QSlider::handle:horizontal {
                background: #3498db;
                border: 2px solid white;
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 7px;
            }
            
            #volumeWidget QSlider::sub-page:horizontal {
                background: #3498db;
                border-radius: 2px;
            }
            
            /* 频谱显示器 */
            #visualizerContainer {
                background: rgba(0, 0, 0, 0.3);
                border-radius: 15px;
                padding: 10px;
                margin: 10px 0;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
            
            /* 滚动条 */
            QScrollBar:vertical {
                border: none;
                background: rgba(255, 255, 255, 0.05);
                width: 10px;
                border-radius: 5px;
                margin: 0;
            }
            
            QScrollBar::handle:vertical {
                background: rgba(52, 152, 219, 0.5);
                border-radius: 5px;
                min-height: 30px;
            }
            
            QScrollBar::handle:vertical:hover {
                background: rgba(52, 152, 219, 0.8);
            }
            
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            
            /* 工具提示 */
            QToolTip {
                background: rgba(44, 62, 80, 0.95);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 5px;
                padding: 5px;
            }
            
            /* 播放按钮特殊样式 */
            QPushButton#play_btn {
                background: rgba(46, 204, 113, 0.8);
                font-size: 15px;
                font-weight: bold;
            }
            
            QPushButton#play_btn:hover {
                background: rgba(39, 174, 96, 0.9);
            }
            
            /* 功能按钮样式 */
            QPushButton#stop_btn {
                background: rgba(231, 76, 60, 0.8);
            }
            
            QPushButton#stop_btn:hover {
                background: rgba(192, 57, 43, 0.9);
            }
            
            QPushButton#download_btn {
                background: rgba(155, 89, 182, 0.8);
            }
            
            QPushButton#download_btn:hover {
                background: rgba(142, 68, 173, 0.9);
            }
            
            QPushButton#mode_btn {
                background: rgba(52, 73, 94, 0.8);
            }
            
            QPushButton#mode_btn:hover {
                background: rgba(44, 62, 80, 0.9);
            }
        """)

    def search_music(self):
        keyword = self.search_input.text()
        if not keyword:
            QMessageBox.warning(self, '提示', '请输入搜索关键词！')
            return
            
        try:
            url = f'https://api.cenguigui.cn/api/mg_music/?msg={keyword}&type=json'
            response = requests.get(url)
            text_response = response.text
            
            self.online_list.clear()
            
            if text_response.startswith('1.'):
                songs = text_response.strip().split('\n')
                for i, song in enumerate(songs, 1):
                    if ' -- ' in song:
                        song_info = song.split('.', 1)[1].strip()
                        title, singer = song_info.split(' -- ')
                        
                        item = QListWidgetItem(f"{title} - {singer}")
                        item.setData(Qt.UserRole, i)
                        self.online_list.addItem(item)
                
                if self.online_list.count() > 0:
                    self.status_label.setText('搜索完成')
                else:
                    self.status_label.setText('未找到相关音乐')
            else:
                QMessageBox.warning(self, '错误', '搜索失败，请稍后重试！')
                
        except Exception as e:
            QMessageBox.warning(self, '错误', f'搜索出错：{str(e)}')
            print("搜索错误详情:", str(e))

    def play_online_music(self, item):
        try:
            self.online_list.setCurrentItem(item)
            song_number = item.data(Qt.UserRole)
            song_text = item.text()
            title = song_text.split(' - ')[0]
            
            url = f'https://api.cenguigui.cn/api/mg_music/?msg={title}&n={song_number}&type=json'
            response = requests.get(url, verify=False)  # 禁用SSL验证
            
            if response.status_code != 200:
                raise Exception(f"API请求失败: {response.status_code}")
            
            data = response.json()
            
            if data.get('code') != 200:
                raise Exception(f"API返回错误: {data.get('msg', '未知错误')}")
            
            song_data = data.get('data')
            if not song_data:
                raise Exception("未获取到歌曲数据")
            
            music_url = song_data.get('music_url')
            if not music_url:
                raise Exception("未获取到音URL")
            
            self.current_music_url = music_url
            
            # 播放音乐
            media_content = QMediaContent(QUrl(music_url))
            self.player.setMedia(media_content)
            
            # 设置音频探针
            self.audio_probe.setSource(None)  # 先清除之前的源
            self.audio_probe.setSource(self.player)  # 设置新的源
            
            self.player.play()
            
            # 更新界面
            self.playing_status.setText(f'正在播放: {song_text}')
            self.status_label.setText('播放中')
            
            # 加载歌词和封面
            lrc_url = song_data.get('lrc_url')
            if lrc_url:
                self.update_lyrics_text(lrc_url)
            
            cover_url = song_data.get('cover')
            if cover_url:
                self.update_cover(cover_url)
            
            # 播放音乐时重启旋转动画
            self.cover_animation.start()
            
        except Exception as e:
            error_msg = f"播放失败: {str(e)}"
            QMessageBox.warning(self, '错误', error_msg)
            print("播放错误详情:", error_msg)

    def update_lyrics_text(self, lrc_url):
        self.loader.add_task('lyrics', lrc_url)

    def update_cover(self, cover_url):
        self.loader.add_task('cover', cover_url)

    def on_lyrics_loaded(self, url, lyrics):
        self.current_lyrics = lyrics
        self.current_lyric_index = -1
        self.update_lyrics_display(0)

    def on_cover_loaded(self, url, pixmap):
        """修改封面加载法，使其显示为圆形"""
        # 创建圆形遮罩
        mask = QPixmap(300, 300)
        mask.fill(Qt.transparent)
        painter = QPainter(mask)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(Qt.white)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, 300, 300)
        painter.end()
        
        # 将原图缩放并裁剪成圆形
        scaled_pixmap = pixmap.scaled(300, 300, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        
        # 居中裁剪
        if scaled_pixmap.width() > 300:
            x = (scaled_pixmap.width() - 300) // 2
            scaled_pixmap = scaled_pixmap.copy(x, 0, 300, 300)
        if scaled_pixmap.height() > 300:
            y = (scaled_pixmap.height() - 300) // 2
            scaled_pixmap = scaled_pixmap.copy(0, y, 300, 300)
        
        # 应用圆形遮罩
        result = QPixmap(300, 300)
        result.fill(Qt.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.drawPixmap(0, 0, mask)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.drawPixmap(0, 0, scaled_pixmap)
        painter.end()
        
        # 设置图片到旋转标签
        self.cover_mask.setPixmap(result)
        
        # 开始旋转动画
        self.cover_animation.start()

    def update_lyrics_display(self, current_time=None):
        if current_time is None:
            current_time = self.player.position()
        
        if not self.current_lyrics:
            return
        
        # 查找当前时间对应的歌词
        index = -1
        for i, (time, _) in enumerate(self.current_lyrics):
            if time > current_time:
                break
            index = i
        
        # 如果歌词索引发生变化，更新显示
        if index != self.current_lyric_index:
            self.current_lyric_index = index
            
            # 构建显示文本
            display_lyrics = []
            start_index = max(0, index - 2)  # 显示当前歌词的前两行
            end_index = min(len(self.current_lyrics), index + 3)  # 显示当前歌词的后两行
            
            for i in range(start_index, end_index):
                lyric = self.current_lyrics[i][1]
                if i == index:
                    # 当前播放的歌词 - 更大字体、高亮显示、添加动画效果
                    display_lyrics.append(f'''
                        <p style="
                            color: #ffffff;
                            font-size: 22px;
                            font-weight: bold;
                            margin: 15px 0;
                            text-shadow: 0 0 10px rgba(52, 152, 219, 0.8);
                            background: linear-gradient(45deg, #3498db, #2ecc71);
                            -webkit-background-clip: text;
                            padding: 5px 10px;
                            border-radius: 5px;
                            transition: all 0.3s ease;
                        ">{lyric}</p>
                    ''')
                else:
                    # 其他歌词 - 半透明效果
                    opacity = 0.6 if abs(i - index) == 1 else 0.4  # 距离当前歌词越远越透明
                    display_lyrics.append(f'''
                        <p style="
                            color: rgba(255, 255, 255, {opacity});
                            font-size: 16px;
                            margin: 10px 0;
                            text-align: center;
                            transition: all 0.3s ease;
                        ">{lyric}</p>
                    ''')
            
            # 更新歌词显示
            self.lyrics_label.setText('''
                <div style="
                    background: rgba(0, 0, 0, 0.3);
                    border-radius: 15px;
                    padding: 20px;
                    text-align: center;
                ">
                    %s
                </div>
            ''' % ''.join(display_lyrics))

    def stop_music(self):
        self.player.stop()
        self.cover_animation.stop()  # 停止旋转动画
        
    def set_position(self, position):
        self.player.setPosition(position)
    
    def set_volume(self, volume):
        self.player.setVolume(volume)
        self.volume_value.setText(f"{volume}%")
    
    def update_position(self, position):
        self.progress_slider.setValue(position)
        current_time = position // 1000
        total_time = self.player.duration() // 1000
        self.time_label.setText(f'{self.format_time(current_time)}/{self.format_time(total_time)}')
        
        # 更新歌词显示
        self.update_lyrics_display(position)
    
    def update_duration(self, duration):
        self.progress_slider.setRange(0, duration)
    
    def format_time(self, seconds):
        minutes = seconds // 60
        seconds = seconds % 60
        return f'{minutes:02d}:{seconds:02d}'

    def toggle_play_pause(self):
        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.play_btn.setText('▶ 播放')
            self.cover_animation.pause()
        else:
            self.player.play()
            self.play_btn.setText('⏸ 暂停')
            self.cover_animation.resume()

    def play_previous(self):
        current_row = self.online_list.currentRow()
        if current_row > 0:
            self.online_list.setCurrentRow(current_row - 1)
            self.play_online_music(self.online_list.currentItem())

    def play_next(self):
        current_row = self.online_list.currentRow()
        if current_row < self.online_list.count() - 1:
            self.online_list.setCurrentRow(current_row + 1)
            self.play_online_music(self.online_list.currentItem())

    def load_recommended_music(self):
        keywords = ['周杰伦', '林俊杰', '邓紫棋', '薛之谦', '张学友']
        try:
            keyword = random.choice(keywords)
            url = f'https://api.cenguigui.cn/api/mg_music/?msg={keyword}&type=json'
            response = requests.get(url)
            text_response = response.text
            
            if text_response.startswith('1.'):
                songs = text_response.strip().split('\n')
                for i, song in enumerate(songs, 1):
                    if ' -- ' in song:
                        song_info = song.split('.', 1)[1].strip()
                        title, singer = song_info.split(' -- ')
                        
                        item = QListWidgetItem(f"{title} - {singer}")
                        item.setData(Qt.UserRole, i)
                        self.online_list.addItem(item)
                
                if self.online_list.count() > 0:
                    self.status_label.setText('推荐音乐加载完成')
                else:
                    self.status_label.setText('未找到荐音乐')
            else:
                self.status_label.setText('加载推荐音乐失败')
                
        except Exception as e:
            print(f"加载推荐音乐失败：{str(e)}")
            self.status_label.setText('加载推荐音乐失败')

    def closeEvent(self, event):
        self.loader.stop()
        self.loader.wait()
        event.accept()

    def download_current_music(self):
        if not self.current_music_url:
            QMessageBox.warning(self, '提示', '请先选择要下载的音乐！')
            return
        
        try:
            # 获取保存路径
            file_name = self.playing_status.text().replace('正在播放: ', '').replace('/', '_') + '.mp3'
            save_path, _ = QFileDialog.getSaveFileName(
                self, 
                '保存音乐', 
                file_name,
                'MP3 文件 (*.mp3)'
            )
            
            if save_path:
                # 开始下载
                response = requests.get(self.current_music_url, stream=True, verify=False)
                total_size = int(response.headers.get('content-length', 0))
                
                if response.status_code == 200:
                    with open(save_path, 'wb') as file:
                        if total_size == 0:
                            file.write(response.content)
                        else:
                            downloaded = 0
                            for data in response.iter_content(chunk_size=4096):
                                downloaded += len(data)
                                file.write(data)
                                # 新状态
                                progress = (downloaded / total_size) * 100
                                self.status_label.setText(f'下载进度: {progress:.1f}%')
                                
                    QMessageBox.information(self, '成功', '音乐下载完成！')
                    self.status_label.setText('下载完成')
                else:
                    raise Exception('下载失败')
                
        except Exception as e:
            QMessageBox.warning(self, '错误', f'下载失败：{str(e)}')
            self.status_label.setText('下载失败')

    def toggle_play_mode(self):
        if self.play_mode == 'sequence':
            self.play_mode = 'loop'
            self.mode_btn.setText('🔂 循环播放')
        else:
            self.play_mode = 'sequence'
            self.mode_btn.setText('🔁 顺序播放')

    def on_media_status_changed(self, status):
        if status == QMediaPlayer.EndOfMedia:
            if self.play_mode == 'loop':
                # 循环播放模式：播放当前歌曲
                self.player.setPosition(0)
                self.player.play()
            else:
                # 顺序播放模式：播放下一首
                current_row = self.online_list.currentRow()
                if current_row < self.online_list.count() - 1:
                    self.online_list.setCurrentRow(current_row + 1)
                    self.play_online_music(self.online_list.currentItem())
                else:
                    # 已经是最后一首，停止播放
                    self.player.stop()
                    self.play_btn.setText('播放')

    def button_hover_effect(self, event, button, entering):
        """按钮悬停动画效果"""
        geometry = button.geometry()
        if entering:
            new_geometry = geometry.adjusted(-2, -2, 2, 2)
        else:
            new_geometry = geometry.adjusted(2, 2, -2, -2)
        
        button.animation.setStartValue(geometry)
        button.animation.setEndValue(new_geometry)
        button.animation.start()

    def create_button_animation(self, button):
        """创建按钮动画效果"""
        # 创建动画对象
        animation = QPropertyAnimation(button, b"geometry", self)
        animation.setDuration(100)
        animation.setEasingCurve(QEasingCurve.OutQuad)
        button.animation = animation  # 保存动画对象到按钮

        # 添加鼠标事件
        def enterEvent(event):
            rect = button.geometry()
            center = rect.center()
            target_width = int(rect.width() * 1.05)  # 减小放大比例
            target_height = int(rect.height() * 1.05)
            new_rect = QRect(0, 0, target_width, target_height)
            new_rect.moveCenter(center)
            animation.setEndValue(new_rect)
            animation.start()
        
        def leaveEvent(event):
            rect = button.geometry()
            center = rect.center()
            original_width = int(rect.width() / 1.05)
            original_height = int(rect.height() / 1.05)
            new_rect = QRect(0, 0, original_width, original_height)
            new_rect.moveCenter(center)
            animation.setEndValue(new_rect)
            animation.start()
        
        # 替换按钮的事件处理器
        button.enterEvent = enterEvent
        button.leaveEvent = leaveEvent

    def process_audio(self, buffer):
        try:
            if buffer.isValid():
                self.visualizer.update_spectrum(buffer)
        except Exception as e:
            print(f"音频处理错误: {str(e)}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    player = MusicPlayer()
    sys.exit(app.exec_()) 