# Robot Edge Model Watcher

该工具运行在植树机器人的边缘侧工控机上，负责监听 URDF/STL 文件的变更，并自动打包推送到云端调度系统，实现数字孪生模型的“热更新”。

## 1. 环境要求

- **OS**: Linux (Ubuntu 20.04/22.04 推荐) 或 Windows (测试环境)
- **Python**: 3.8+
- **网络**: 需能访问调度服务器的 HTTP 接口 (默认 8000 端口)

## 2. 安装部署

### 2.0 传输文件 (关键步骤)

**注意**：你**不需要**拷贝整个项目或 `backend` 目录。仅需将 `scripts/robot_edge` 文件夹拷贝到机器人即可。

**方法 A：使用 SCP (推荐)**
在你的开发机（Windows/Mac）上运行：
```bash
# 假设机器人 IP 为 10.144.144.2，用户名为 david (或者是 root)
# 将本地的 robot_edge 目录拷贝到机器人的 home 目录并重命名为 model_watcher
scp -r scripts/robot_edge david@10.144.144.2:~/model_watcher
```

**方法 B：使用 U 盘**
将 `scripts/robot_edge` 文件夹复制到 U 盘，插入机器人工控机，拷贝到 `~/model_watcher`。

**方法 C：使用 SSH + SFTP 组合操作 (通用)**

**步骤 1：本地打包**
在您的开发机上，将 `scripts/robot_edge` 文件夹压缩为 `robot_edge.zip` 或 `robot_edge.tar.gz`。

**步骤 2：机器人端准备目录 (SSH)**
登录到机器人终端：
```bash
ssh david@10.144.144.2
```
在 SSH 中执行：
```bash
# 确保在主目录
cd ~
# 创建部署目录（如果不存在）
mkdir -p ~/model_watcher
```

**步骤 3：上传文件 (SFTP)**
使用您的 SFTP 工具（如 MobaXterm 左侧栏或 FileZilla）连接到 `10.144.144.2`。
1. 导航到远程目录 `/home/david/model_watcher`。
2. 将本地的压缩包（如 `robot_edge.zip`）上传到该目录。

**步骤 4：解压与整理 (SSH)**
回到 SSH 终端，执行解压：
```bash
cd ~/model_watcher

# 如果是 zip 包
unzip robot_edge.zip
# 此时文件可能在子目录 robot_edge 中，将其移动出来
mv robot_edge/* .
rmdir robot_edge
rm robot_edge.zip

# 如果是 tar.gz 包
# tar -xzvf robot_edge.tar.gz --strip-components=1
```
*最终确保 `watcher.py` 和 `requirements.txt` 直接位于 `~/model_watcher` 目录下。*

### 2.1 安装依赖

SSH 登录到机器人，进入刚才拷贝的目录，创建虚拟环境并安装依赖：

```bash
ssh david@10.144.144.2
cd ~/model_watcher

# 创建并激活虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖 (仅需 requests 和 watchdog)
pip install -r requirements.txt
```

### 2.2 运行测试

假设你的机器人描述包位于 `~/ros2_ws/src/tree_robot_description`，服务器 IP 为 `10.144.144.2`。

运行以下命令启动监听：

```bash
python watcher.py \
  --dir ~/ros2_ws/src/tree_robot_description \
  --url http://10.144.144.10:8000/api/model/upload-zip \
  --type tree_planter
```

### 2.3 TurtleBot3 测试示例 (强烈推荐)

如果你安装了 ROS 2 Humble，可以使用系统自带的 TurtleBot3 模型进行测试。

1. **拷贝模型副本** (避免修改系统只读目录)：
   ```bash
   cp -r /opt/ros/humble/share/turtlebot3_description ~/turtlebot3_test
   ```

2. **启动监听**：
   ```bash
   python watcher.py \
     --dir ~/turtlebot3_test \
     --url http://10.144.144.10:3500/api/model/upload-zip \
     --type turtlebot3
   ```

3. **触发更新**：
   打开一个新的终端，修改副本中的 URDF 文件：
   ```bash
   echo '<!-- test update -->' >> ~/turtlebot3_test/urdf/turtlebot3_burger.urdf
   ```
   此时 watcher 应会检测到变更并自动上传。

启动后，当你修改该目录下的任意 `.urdf` 或 `.stl` 文件并保存时，脚本会在 2 秒后自动触发打包上传。

## 3. 生产环境部署 (Systemd)

在 Linux 生产环境中，建议将其配置为 Systemd 服务实现开机自启。以下步骤需在机器人终端执行。

### 3.1 创建服务文件

使用 vim 编辑器创建服务配置：
```bash
sudo vim /etc/systemd/system/model-watcher.service
```

按 `i` 键进入插入模式，将以下内容粘贴进去（**注意修改 `User` 和路径**）：

```ini
[Unit]
Description=Robot Model Auto-Sync Watcher
After=network.target

[Service]
Type=simple
# ！！！修改为你的实际用户名（如 ubuntu, pi, david）！！！
User=david
# ！！！修改为 watcher.py 所在的实际目录！！！
WorkingDirectory=/home/david/model_watcher

# 启动命令：使用虚拟环境中的 python 解释器
# 参数说明：
# --dir: 监听的机器人描述包路径 (URDF/STL所在)
# --url: 调度服务器上传接口地址
# --type: 机器人唯一标识
ExecStart=/home/david/model_watcher/venv/bin/python watcher.py \
    --dir /home/david/ros2_ws/src/tree_robot_description \
    --url http://10.144.144.10:3500/api/model/upload-zip \
    --type tree_planter

# 如果是 TurtleBot3 测试环境，请注释上方，解注下方：
# ExecStart=/home/david/model_watcher/venv/bin/python watcher.py \
#   --dir /home/david/turtlebot3_test \
#   --url http://10.144.144.10:3500/api/model/upload-zip \
#   --type turtlebot3

# 自动重启策略：挂掉后 10 秒重启
Restart=always
RestartSec=10

# 日志输出到系统日志
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```
*按 `Esc` 退出编辑模式，输入 `:wq` 并回车保存退出。*

### 3.2 启用服务

```bash
# 1. 重载系统服务配置
sudo systemctl daemon-reload

# 2. 设置开机自启
sudo systemctl enable model-watcher

# 3. 立即启动服务
sudo systemctl start model-watcher
```

### 3.3 验证与排查

检查服务状态：
```bash
sudo systemctl status model-watcher
```
*正常情况下应显示绿色圆点 `● active (running)`*

查看实时运行日志：
```bash
# -u 指定服务名, -f 持续跟踪最新日志
sudo journalctl -u model-watcher -f
```

停止或重启服务：
```bash
sudo systemctl stop model-watcher
sudo systemctl restart model-watcher
```

## 5. 高级特性 (v1.1 更新)

### 5.1 自动失败重试
如果上传过程中发生网络中断，脚本会自动进行最多 5 次重试，等待时间分别为 2s, 4s, 8s, 16s, 32s。无需人工干预。

### 5.2 定期全量同步
除了文件修改触发外，脚本内置了一个后台定时器，**每隔 1 小时**会自动执行一次一致性检查。如果发现本地内容指纹与上一次成功上传的不同（例如上次重试全部失败），会自动触发全量同步。

## 6. 模拟测试方法

如果你没有物理机器人，可以在本地模拟：

1. 创建一个测试目录：
   ```bash
   mkdir -p temp_robot_desc/urdf
   echo "<robot name='test'></robot>" > temp_robot_desc/urdf/robot.urdf
   ```

2. 启动 watcher (假设服务器在 localhost):
   ```bash
   python watcher.py --dir ./temp_robot_desc
   ```

3. 修改文件触发上传：
   ```bash
   echo "<!-- modified -->" >> temp_robot_desc/urdf/robot.urdf
   ```

4. 观察控制台输出，应显示 `Detected change` -> `Debounce finished` -> `Upload SUCCESS`。
