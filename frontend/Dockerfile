FROM node:22-alpine

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend /app/frontend

RUN npm run build

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
