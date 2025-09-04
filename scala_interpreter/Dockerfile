ARG BUILD_PLATFORM=linux/amd64
# Stage 1: Build staged distribution
FROM --platform=${BUILD_PLATFORM} hseeberger/scala-sbt:11.0.11_1.5.5_2.13.6 AS builder

WORKDIR /app

# Copy sbt plugins and build definition
COPY project/plugins.sbt /app/project/
COPY build.sbt /app/

# Pre-fetch dependencies
RUN sbt update

# Copy source
COPY src /app/src

# Stage the application (creates ./target/universal/stage)
RUN sbt stage

# Stage 2: Runtime image
FROM openjdk:11-jre-slim

WORKDIR /opt/app

# Install curl for healthchecks
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy staged distribution
COPY --from=builder /app/target/universal/stage /opt/app

EXPOSE 8642

# Container healthcheck: perform a real Scala computation via /execute
HEALTHCHECK --interval=30s --timeout=8s --retries=3 --start-period=15s \
  CMD sh -c "res=$(curl -sf -X POST -H 'Content-Type: application/json' -d '{\"code\":\"println(1+1)\"}' http://localhost:8642/execute); echo \"$res\" | grep -q '\"success\":true' && echo \"$res\" | grep -q '\"output\":\"2' || exit 1"

# Run cask server via generated script
CMD ["./bin/scala_interpreter"]
