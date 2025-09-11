
name := "scala_interpreter"

scalaVersion := "2.13.16"

resolvers += "Sonatype OSS Releases" at "https://oss.sonatype.org/content/repositories/releases/"

val ujsonVersion = "4.1.0"

enablePlugins(JavaAppPackaging)

dependencyOverrides ++= Seq(
  "com.lihaoyi" %% "upickle" % ujsonVersion,
  "com.lihaoyi" %% "ujson" % ujsonVersion
)

libraryDependencies ++= Seq(
  "com.lihaoyi" %% "ujson" % "3.1.3",
  "org.scala-lang" % "scala-compiler" % scalaVersion.value,
  "org.scala-lang" % "scala-reflect" % scalaVersion.value,
  "com.sparkjava" % "spark-core" % "2.9.4"
)

Compile / mainClass := Some("Server")
