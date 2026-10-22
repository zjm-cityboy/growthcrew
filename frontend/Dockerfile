# GrowthCrew 前端镜像：多阶段构建，运行态只带 standalone 产物（约 100MB）
# NEXT_PUBLIC_API_URL 不注入时默认 http://127.0.0.1:8100/api/v1 —— 与
# docker-compose.yml 的后端宿主端口 8100 对齐，浏览器端直连（同机部署零配置）
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000
# standalone 产物不含静态资源与 public，需单独拷入
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
EXPOSE 3000
USER node
CMD ["node", "server.js"]
