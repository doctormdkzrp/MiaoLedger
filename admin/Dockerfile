# ---------- 构建阶段 ----------
FROM node:22-alpine AS build

WORKDIR /app

# 先只拷依赖清单，利用镜像层缓存
COPY package.json pnpm-lock.yaml ./

RUN corepack enable \
    && corepack prepare pnpm@10.34.9 --activate \
    && pnpm install --frozen-lockfile

COPY . .

RUN pnpm build

# ---------- 运行阶段 ----------
FROM nginx:alpine

# 去掉默认站点，换成本项目的配置
RUN rm -f /etc/nginx/conf.d/default.conf

COPY nginx.conf /etc/nginx/conf.d/miao.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
