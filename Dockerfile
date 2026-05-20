FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci

COPY tsconfig.json ./
COPY src/ ./src/
RUN npm run build

# ─── Production image ─────────────────────────────────────────────────────────
FROM node:20-alpine AS runner

WORKDIR /app
COPY package*.json ./
# Install all deps including devDeps so tsx is available for scripts
RUN npm ci

COPY --from=builder /app/dist ./dist
COPY config/ ./config/
COPY data/ ./data/
COPY docs/ ./docs/
COPY openspec/ ./openspec/
COPY prompts/ ./prompts/
COPY scripts/ ./scripts/
COPY src/ ./src/
COPY .agents/ ./.agents/
COPY tsconfig.json ./
COPY *.md ./

# runs/ is volume-only at runtime; prompts/ is now baked in (volume overrides in local dev)
RUN mkdir -p /app/runs

EXPOSE 3000
EXPOSE 3001
EXPOSE 3030

CMD ["node", "dist/server.js"]
