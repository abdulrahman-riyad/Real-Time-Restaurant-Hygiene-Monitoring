FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

# This debug line is helpful and can be left in.
RUN echo "--- Contents of /app/src/lib/store.ts ---" && cat /app/src/lib/store.ts && echo "---------------------------------------"

RUN npm run build

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["npm", "start"]