# ===========================================
# Stage 1: Build Frontend
# ===========================================
FROM node:20-alpine AS frontend-builder

WORKDIR /app

# Copy package files first for layer caching
COPY frontend/package*.json ./

RUN npm ci

COPY frontend/ ./

RUN npm run build

# ===========================================
# Stage 2: Production NGINX (pinned version)
# ===========================================
FROM nginx:1.25.4-alpine

# Install curl for healthcheck
RUN apk add --no-cache curl

# Remove default configuration
RUN rm -f /etc/nginx/nginx.conf /etc/nginx/conf.d/default.conf

# Copy our configuration
COPY nginx/nginx.conf /etc/nginx/nginx.conf

# Copy frontend build from builder stage
COPY --from=frontend-builder /app/dist /usr/share/nginx/html

# Create log directory with correct ownership
RUN mkdir -p /var/log/nginx /var/cache/nginx && \
    chown -R nginx:nginx /var/log/nginx /var/cache/nginx /usr/share/nginx/html

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost/health || exit 1

EXPOSE 80

# Run as nginx user (non-root)
USER nginx

CMD ["nginx", "-g", "daemon off;"]
