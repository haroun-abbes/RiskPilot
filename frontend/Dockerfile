FROM node:22-alpine AS build
WORKDIR /app
# Rewrites are resolved at build time: the backend URL must be known here
ARG RISKPILOT_API_URL=http://api:8000
ENV RISKPILOT_API_URL=$RISKPILOT_API_URL
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app ./
EXPOSE 3000
CMD ["npm", "run", "start"]
