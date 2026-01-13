# tStudio 本地开发环境启动指南

本文档详细说明如何配置 Conda 环境并启动 tStudio 的前后端服务。

## 1. 前置条件

### 1.1 系统环境变量配置
确保 Anaconda/Miniconda 已正确添加到系统的 **Path** 环境变量中。如果终端无法识别 `conda` 命令，请按以下步骤配置：

1. **打开环境变量设置**：
   - `Win + S` 搜索 "编辑系统环境变量" -> 点击 "环境变量"。
2. **编辑用户变量 Path**：
   - 选中 "用户变量" 中的 `Path` -> 点击 "编辑" -> "新建"。
3. **添加以下路径**（根据实际安装位置调整，以下为默认示例）：
   - `D:\soft\develop\anaconda3`
   - `D:\soft\develop\anaconda3\Scripts`
   - `D:\soft\develop\anaconda3\Library\bin`
   - `D:\soft\develop\anaconda3\condabin` (关键：用于初始化脚本)
4. **重启生效**：配置完成后，必须重启 IDE（如 VS Code、Trae）或终端窗口。

### 1.3 Make 工具配置 (Windows)
如果执行 `make` 报错，说明系统找不到该命令。请按以下步骤配置（只需做一次）：

1.  **确认安装路径**：通常在 `C:\ProgramData\chocolatey\bin`。
2.  **永久添加到 Path (图形界面方式 - 推荐)**：
    - 按 `Win + S`，搜索 **"编辑系统环境变量"** 并打开。
    - 点击右下角的 **"环境变量"** 按钮。
    - 在 **"用户变量"** (上面那栏) 中找到 `Path`，选中并点击 **"编辑"**。
    - 点击 **"新建"**，粘贴路径：`C:\ProgramData\chocolatey\bin`
    - 连续点击 **"确定"** 保存。
3.  **重要：重启生效**：
    - 配置完成后，**必须完全关闭并重启** Trae/VS Code 或终端窗口，新配置才会生效。

### 1.4 验证环境
在终端执行以下命令，确保输出正常：
```powershell
conda --version
# 输出示例: conda 23.x.x

node -v
# 要求: >= v18.0.0
```

---

## 2. 启动步骤 (手动模式)

请打开**两个独立的终端窗口**，分别用于启动后端和前端。

### 终端 1：后端服务 (Backend)

1. **激活虚拟环境**
   ```powershell
   # 激活名为 my_env 的环境
   conda activate my_env
   ```
   > **注意**：如果 `conda activate` 报错（如未初始化），可使用 `conda run -n my_env ...` 替代后续命令，或运行 `conda init powershell` 后重启终端。

2. **安装/更新依赖**
   ```powershell
   # 确保在项目根目录下执行
   pip install -r backend/requirements.txt
   ```

3. **启动服务**
   ```powershell
   python backend/main.py
   ```
   - **成功标志**：看到 `Uvicorn running on http://0.0.0.0:3500`。
   - **服务地址**：http://localhost:3500

### 终端 2：前端服务 (Frontend)

1. **进入前端目录**
   ```powershell
   cd frontend
   ```

2. **安装依赖**
   ```powershell
   npm install
   ```

3. **启动开发服务器**
   ```powershell
   npm start
   ```
   - **成功标志**：浏览器自动打开，显示 tStudio 界面。
   - **访问地址**：http://localhost:3000

---

## 3. 备选方案：免激活直接启动 (终极替代方案)

如果重启终端后 `conda activate` 依然无效，或者 PowerShell 报错“禁止运行脚本”，请**完全跳过激活步骤**，直接使用 `conda run` 命令来执行操作。这种方式不需要修改 Shell 状态，最稳定。

**安装后端依赖**：
```powershell
conda run -n my_env pip install -r backend/requirements.txt
```

**启动后端服务**：
```powershell
conda run -n my_env python backend/main.py
```

---

## 4. 常见问题排查

| 问题现象 | 解决方案 |
|---------|---------|
| `conda activate` 失败 | 尝试使用 `conda run -n my_env python backend/main.py` 直接运行，避开激活步骤。 |
| 端口被占用 (3500/3000) | 检查是否有旧的终端进程未关闭；或在 `backend/main.py` 和 `package.json` 中修改端口。 |
| 依赖安装慢 | 配置国内镜像源：<br>`pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple` |
| `make` 命令未找到 | Windows 下需手动安装 `make` (推荐通过 Chocolatey: `choco install make`)。安装后若仍报错，请将 `C:\ProgramData\chocolatey\bin` 添加到 Path，或在当前终端执行 `$env:Path += ";C:\ProgramData\chocolatey\bin"`。 |
