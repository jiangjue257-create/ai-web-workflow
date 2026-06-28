# AI Web Workflow

本地浏览器图片和视频生成工作台。

它会在本机启动一个网页工具，用中转站 API 生成图片或视频，并把结果保存到本地
`outputs` 目录。

## 主要功能

- 文生图、图生图。
- 文生视频、参考图生视频。
- 自动轮询任务进度，完成后在网页里预览图片或视频。
- 参考图生视频会自动把图片处理成接口支持的比例尺寸。
- API key 只保存在本机 `config.local.json`。

## 新电脑使用

先安装 Python 3.13 或较新的 Python 3 版本。

然后打开 Windows PowerShell，一行一行运行：

```powershell
cd D:\你的路径\ai-web-workflow
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8765
```

看到服务启动后，打开浏览器访问：

```text
http://127.0.0.1:8765
```

第一次使用时，点击页面右上角“打开设置”，填写：

- `API Base URL`：一般填 `https://api.hellobabygo.com`
- `API Key`：填写你的中转站 key
- `输出目录`：默认 `outputs` 即可

## 本地配置

真实 API key 保存在 `config.local.json`。不要把这个文件上传到 GitHub。

仓库里只保留 `config.example.json` 作为示例。新电脑上如果想手动创建配置，可以复制它：

```powershell
Copy-Item config.example.json config.local.json
```

然后打开 `config.local.json`，把 `api_key` 填成自己的 key。

## 常用命令

检查中转站模型列表：

```powershell
.\.venv\Scripts\python scripts\check-models.py
```

真实调用参考图生视频，会消耗额度：

```powershell
.\.venv\Scripts\python scripts\real-reference-video-test.py --image "C:\path\to\image.jpg" --prompt "提示词" --aspect-ratio 9:16 --yes
```

运行本地测试：

```powershell
.\.venv\Scripts\python -m pytest
```

## GitHub 上传提醒

可以上传的主要内容是代码、脚本、静态网页、测试和说明文件。

不要上传：

- `config.local.json`：里面有真实 API key。
- `.venv/`：本机 Python 环境，体积大，换电脑后重新安装即可。
- `outputs/`：生成的图片、视频和参考图，体积大，也可能是私人素材。
- `*.log`、`*.err.log`：本地运行日志。
