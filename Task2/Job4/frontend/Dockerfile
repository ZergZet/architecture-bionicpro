FROM node:18-alpine AS builder

WORKDIR /app

ENV NODE_OPTIONS=--openssl-legacy-provider \
    CI=false \
    GENERATE_SOURCEMAP=false \
    DISABLE_ESLINT_PLUGIN=true \
    BROWSERSLIST_IGNORE_OLD_DATA=true

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG REACT_APP_API_URL
ARG REACT_APP_KEYCLOAK_URL
ARG REACT_APP_KEYCLOAK_REALM
ARG REACT_APP_KEYCLOAK_CLIENT_ID
ENV REACT_APP_API_URL=$REACT_APP_API_URL \
    REACT_APP_KEYCLOAK_URL=$REACT_APP_KEYCLOAK_URL \
    REACT_APP_KEYCLOAK_REALM=$REACT_APP_KEYCLOAK_REALM \
    REACT_APP_KEYCLOAK_CLIENT_ID=$REACT_APP_KEYCLOAK_CLIENT_ID

RUN npm run build


FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/build /usr/share/nginx/html

EXPOSE 3000
CMD ["nginx", "-g", "daemon off;"]
