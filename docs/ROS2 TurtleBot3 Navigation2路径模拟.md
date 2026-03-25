这是一套基于 **ROS 2 Humble** 的完整操作方案。这套方案基于提供的教程逻辑，但针对 Humble 版本进行了适配，重点在于**如何产生导航数据并在 RViz2 中清晰地订阅和可视化路径（Path）**。

### 核心方案设计

我们将使用 `TurtleBot3` 在 `Gazebo` 仿真环境中产生真实的传感器数据，运行 `Nav2` 导航栈生成路径规划数据，最后在 `RViz2` 中手动配置订阅器来查看路径。

* **数据源**：Gazebo (模拟雷达、里程计)
* **路径规划器**：Nav2 Planner Server (发布全局路径 `/plan`)
* **控制器**：Nav2 Controller Server (发布局部路径 `/local_plan`)
* **可视化**：RViz2

---

### 第一阶段：环境准备与安装

请打开终端，一次性安装所需的全部 Humble 依赖包：

```bash
sudo apt update
sudo apt install ros-humble-navigation2 ros-humble-nav2-bringup \
ros-humble-turtlebot3-gazebo ros-humble-turtlebot3-msgs \
ros-humble-turtlebot3-simulations ros-humble-rmw-cyclonedds-cpp

```

**设置环境变量**（必须执行，否则会报错）：

```bash
echo 'export TURTLEBOT3_MODEL=waffle' >> ~/.bashrc
echo 'export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp' >> ~/.bashrc
source ~/.bashrc

```

*注：这里推荐使用 `waffle` 模型，因为它在仿真中搭载的传感器配置对导航更友好。*

---

### 第二阶段：详细操作步骤

#### 步骤 1：启动仿真环境 (Gazebo)

我们需要先启动一个带有物理属性的模拟世界。

打开**第 1 个终端**：

```bash
ros2 launch turtlebot3_gazebo turtlebot3_world.launch.py

```

*此时应弹出一个 Gazebo 窗口，里面有白色的柱子和障碍物。*

#### 步骤 2：启动导航栈 (Nav2)

为了简化流程，我们使用 Nav2 自带的仿真启动文件（这比原教程的分步启动更适合 Humble 版本，因为它会自动处理地图和 TF 变换）。

打开**第 2 个终端**：

```bash
ros2 launch nav2_bringup tb3_simulation_launch.py headless:=False

```

* `headless:=False` 表示我们需要它自动启动 RViz2。
* 这个命令会自动加载一张默认的地图，并启动 AMCL定位、路径规划器和控制器。

#### 步骤 3：在 RViz2 中“订阅 Path” (关键步骤)

系统启动后，RViz2 会自动打开。默认配置通常已经包含了一些显示，但为了确保您能**根据网页内容分析数据**，我们需要手动确认并添加路径订阅：

1. **查看显示列表**：在 RViz 左侧的 "Displays" 面板中。
2. **删除干扰项**（可选）：如果看起来太乱，可以先取消勾选所有的 checkbox，只保留 `Map`。
3. **添加全局路径 (Global Path)**：
* 点击左下角的 **Add** 按钮。
* 点击 **By Topic** 标签页。
* 向下滚动找到 `/plan` -> `Path`。
* 选中它并点击 **OK**。
* **配置颜色**：在左侧列表新出现的 `Path` 下，将 `Color` 改为 **绿色 (Green)**，`Line Style` 选为 `Lines`。
* *含义：这是算法计算出的从起点到终点的理想路径。*


4. **添加局部路径 (Local Plan)**：
* 再次点击 **Add** -> **By Topic**。
* 找到 `/local_plan` -> `Path` (如果找不到，请查找 `/received_global_plan` 或者 `/controller_plan`，Humble 中通常是 `/local_plan`)。
* 选中并点击 **OK**。
* **配置颜色**：将此 `Path` 的 `Color` 改为 **蓝色 (Blue)**。
* *含义：这是机器人根据当前避障情况，即将执行的短期路径。*



#### 步骤 4：初始化与发送指令

现在我们开始产生导航数据：

1. **初始化定位 (2D Pose Estimate)**：
* 点击 RViz 顶部工具栏的 **2D Pose Estimate**。
* 参考 Gazebo 中机器人的位置，在 RViz 地图上点击并拖动箭头。
* *现象：此时地图上的激光雷达点（红色/彩色小点）应该与地图的黑色边缘重合。*


2. **发送导航目标 (Nav2 Goal)**：
* 点击 RViz 顶部工具栏的 **Nav2 Goal**。
* 在地图的任意空闲位置点击并拖动方向。



### 第三阶段：观察数据与结果

一旦您设定了目标，请立即观察 RViz 中的变化，您将看到您所需要的“导航数据”可视化：

1. **绿线 (Global Path)**：会在您松开鼠标的瞬间立即生成，连接起点和终点，绕过已知障碍物。
2. **蓝线 (Local Path)**：会很短，位于机器人前方，随着机器人的移动不断跳动和更新。
3. **机器人运动**：Gazebo 中的机器人会开始移动，RViz 中的 TF 坐标系也会跟随移动。

### 常见问题排查

* **看不到 `/plan` 话题？**
* 只有在设定了 `Nav2 Goal` **之后**，规划器才会发布这个话题。如果没有设置目标，这个话题是没有数据的，在 RViz 中会显示警告。


* **机器人不移动？**
* 检查 RViz 左侧 Displays 面板中的 `RobotModel` 是否报错。
* 确保此时 Gazebo 没有处于 "Pause" 状态。



通过以上步骤，您就完成了从网页教程理论到 Humble 实际操作的复现，并成功订阅了路径数据。