FROM node:18 as build
WORKDIR /app/ui
COPY . .
RUN npm ci && npm run build

FROM nginx:1.25-alpine
# Copy built react app from build stage
COPY --from=build /app/ui/dist /usr/share/nginx/html
# Optional: Add custom Nginx config if proxying to backend is needed from Nginx
# COPY nginx.conf /etc/nginx/conf.d/default.conf 