# syntax=docker/dockerfile:1

# ---------- build stage: full JDK + Maven, thrown away after packaging ----------
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /build

# Resolve dependencies against pom.xml alone first. This layer is cached and only
# re-runs when the pom changes, so ordinary source edits don't re-download the world.
COPY pom.xml .
RUN mvn -B --no-transfer-progress dependency:go-offline

COPY src ./src
# `package` compiles and runs the unit tests, then stops - short of `verify`, which is
# the phase pitest is bound to. The mutation gate is enforced by `legacylift verify` and
# by CI, not by every image build. Note that nothing here skips a test.
# This is also what keeps the *IT classes out of the image build: failsafe binds to
# `integration-test`/`verify`, both AFTER `package`, so nothing here tries to start a
# PostgreSQL container inside a container. That is why no -DskipTests is needed.
RUN mvn -B --no-transfer-progress package

# Normalise the artifact name so the runtime stage doesn't need the pom's
# artifactId/version. (`*.jar` matches only the boot jar; spring-boot:repackage leaves
# the pre-repackage copy as `.jar.original`, which this glob does not match.)
RUN mv target/*.jar /build/app.jar

# ---------- runtime stage: JRE only, no Maven, no JDK, no sources ----------
FROM eclipse-temurin:21-jre-alpine AS runtime
WORKDIR /app

# Nothing in the service needs privileges, so don't run as root.
RUN addgroup -S app && adduser -S -G app app

COPY --from=build --chown=app:app /build/app.jar /app/app.jar
USER app

EXPOSE 8080

# The datasource is supplied by the environment (see compose.yaml); the defaults baked
# into application.properties only cover a database on localhost.
# JAVA_OPTS is expanded by the shell; `exec` then replaces it so the JVM is PID 1 and
# receives SIGTERM directly, which lets `docker stop` shut Spring down gracefully.
ENV JAVA_OPTS=""
ENTRYPOINT ["sh", "-c", "exec java $JAVA_OPTS -jar /app/app.jar"]
