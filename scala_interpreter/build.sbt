
name := "scala_interpreter"

scalaVersion := "2.13.16"

resolvers += "Sonatype OSS Releases" at "https://oss.sonatype.org/content/repositories/releases/"

val ammoniteVersion = "3.0.2"
val ujsonVersion = "4.1.0"

enablePlugins(JavaAppPackaging)

dependencyOverrides ++= Seq(
  "com.lihaoyi" %% "upickle" % ujsonVersion,
  "com.lihaoyi" %% "ujson" % ujsonVersion
)

libraryDependencies ++= Seq(
  "com.lihaoyi" % "ammonite_2.13.16" % ammoniteVersion,
  "com.lihaoyi" %% "ujson" % ujsonVersion,
  "com.sparkjava" % "spark-core" % "2.9.4"
)

Compile / mainClass := Some("Server")
