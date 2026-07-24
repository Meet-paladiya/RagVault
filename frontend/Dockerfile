# Build stage
FROM node:20-alpine AS builder
WORKDIR /app

# Copy package files first for better layer caching
COPY package.json ./
# Use npm install (works without package-lock.json for first builds)
RUN npm install --legacy-peer-deps

# Copy source code and build
COPY . .
RUN npm run build

# Runtime stage — serve with Nginx
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
