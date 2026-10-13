# One image for the whole app: the React interface and the Node API, with yt-dlp and ffmpeg.
FROM node:22-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.js ./
COPY src ./src
RUN npm run build

FROM node:22-bookworm-slim
ARG TARGETARCH
# yt-dlp is downloaded at build time, so every new deploy picks up its latest release
# (YouTube changes often and old versions stop working).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates curl \
    && if [ "$TARGETARCH" = "arm64" ]; then YTDLP=yt-dlp_linux_aarch64; else YTDLP=yt-dlp_linux; fi \
    && curl -fsSL -o /usr/local/bin/yt-dlp "https://github.com/yt-dlp/yt-dlp/releases/latest/download/$YTDLP" \
    && chmod +x /usr/local/bin/yt-dlp \
    && yt-dlp --version \
    && apt-get purge -y curl && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV NODE_ENV=production PORT=8000
COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force
COPY server ./server
COPY --from=build /app/dist ./dist

USER node
EXPOSE 8000
CMD ["node", "server/index.js"]
