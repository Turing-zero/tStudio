const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = function(app) {
  // 1. API 代理 (转发到后端)
  app.use(
    '/api',
    createProxyMiddleware({
      target: 'http://localhost:8000',
      changeOrigin: true,
    })
  );

  // 2. MinIO 代理 (转发到 MinIO 服务器)
  // 将 /tree-robot-assets 开头的请求转发到内网 IP
  app.use(
    '/tree-robot-assets',
    createProxyMiddleware({
      target: 'http://10.144.144.2:30900',
      changeOrigin: true,
    })
  );
};