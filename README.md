# 春日部的告别 - 音乐播放器

一个基于 PyQt5 开发的简洁优雅的音乐播放器，支持在线搜索、播放、下载音乐。

## 功能特点

- 🎵 在线音乐搜索和播放
- 📥 音乐下载功能
- 🎨 渐变背景和优雅界面
- 🌈 动画过渡效果
- 🎶 实时歌词显示
- 🖼️ 专辑封面旋转动画
- 🔄 循环/顺序播放模式
- 🎚️ 音量和进度控制
- 💾 智能缓存机制
- 🌈 频谱可视化效果
- 🎯 按钮悬停动画
- 🎨 毛玻璃UI设计

## 安装说明

1. 克隆项目

## 界面预览

- 优雅的渐变背景
- 半透明毛玻璃效果
- 动态歌词显示
- 专辑封面旋转动画
- 实时频谱动画
- 按钮悬停特效
- 现代化UI设计

## 使用说明

1. 搜索音乐
   - 在搜索框输入歌名或歌手
   - 点击搜索按钮或回车
   - 双击列表中的歌曲播放

2. 播放控制
   - 播放/暂停：控制音乐播放
   - 上一首/下一首：切换歌曲
   - 停止：停止播放
   - 音量滑块：调节音量
   - 进度条：调整播放进度

3. 播放模式
   - 顺序播放：播放完当前歌曲后自动播放下一首
   - 循环播放：单曲循环播放当前歌曲

4. 下载音乐
   - 播放时点击下载按钮
   - 选择保存位置
   - 等待下载完成

## API 说明

### 音乐搜索 API

```python
def search_music(keyword: str, page: int = 1) -> dict:
    """
    搜索音乐
    
    参数:
        keyword (str): 搜索关键词
        page (int): 页码，默认为1
        
    返回:
        dict: 包含搜索结果的字典
    """
```

### 音乐下载 API

```python
def download_music(song_id: str, save_path: str) -> bool:
    """
    下载音乐
    
    参数:
        song_id (str): 歌曲ID
        save_path (str): 保存路径
        
    返回:
        bool: 下载是否成功
    """
```

### 歌词获取 API

```python
def get_lyrics(song_id: str) -> dict:
    """
    获取歌词
    
    参数:
        song_id (str): 歌曲ID
        
    返回:
        dict: 包含时间轴的歌词字典
    """
```

## 技术特性

- PyQt5 构建的现代界面
- OpenGL 实现频谱动画
- 异步加载优化体验
- 智能缓存机制
- 优雅的动画效果
- 完善的错误处理

## 配置说明

程序配置文件位于 `config.json`，可以自定义以下设置：

```json
{
    "theme": "dark",
    "cache_path": "./cache",
    "download_path": "./downloads",
    "max_cache_size": 1024,
    "api_timeout": 30
}
```

## 错误处理

程序包含完善的错误处理机制：

- 网络连接失败自动重试
- 下载失败智能续传
- API 异常优雅降级
- 文件损坏自动修复

## 贡献指南

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 开源协议

本项目采用 MIT 协议开源，详见 [LICENSE](LICENSE) 文件。




