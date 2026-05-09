# 基础镜像使用官方 Nginx
FROM nginx:alpine

# 维护者信息
LABEL maintainer="tStudio Team"

# 移除 Nginx 默认配置
RUN rm /etc/nginx/conf.d/default.conf

# 挂载工作目录（可选）
VOLUME /usr/share/nginx/html

# 创建工作目录
RUN mkdir -p /usr/share/nginx/html

# 复制自定义 nginx.conf 到容器
COPY ./conf/nginx.conf /etc/nginx/nginx.conf

# 将 React 编译后的 build 文件夹内容复制到 Nginx 默认的 html 目录
# 确保在执行 docker build 前，本地已经执行过 npm run build
COPY ./build /usr/share/nginx/html

# 暴露端口
EXPOSE 80

# 启动 Nginx
CMD ["nginx", "-g", "daemon off;"]
