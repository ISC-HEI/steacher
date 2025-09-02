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

# Copy staged distribution
COPY --from=builder /app/target/universal/stage /opt/app

EXPOSE 8080

# Run cask server via generated script
CMD ["./bin/scala_interpreter"]
