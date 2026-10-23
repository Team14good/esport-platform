# 前端開發容器：以專案根目錄為 build context，依根目錄 bun.lock 安裝依賴後啟動 Vite dev server。
FROM oven/bun:1.4

WORKDIR /app

COPY package.json bun.lock /app/
COPY frontend/package.json /app/frontend/

RUN bun install --frozen-lockfile

COPY ./frontend /app/frontend

WORKDIR /app/frontend

EXPOSE 5173

CMD ["bun", "run", "dev", "--host", "0.0.0.0", "--port", "5173"]
