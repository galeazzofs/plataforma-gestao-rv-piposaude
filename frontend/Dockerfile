# Build stage — shadow-cljs needs JDK to compile ClojureScript
FROM node:20-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends default-jdk && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY package.json yarn.lock shadow-cljs.edn ./
RUN yarn install --frozen-lockfile
COPY . .
RUN yarn release

# Serve stage
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/resources/public /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -q --spider http://127.0.0.1/nginx-health || exit 1
