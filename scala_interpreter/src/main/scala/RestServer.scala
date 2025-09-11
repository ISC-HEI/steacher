import java.util.concurrent.{Callable, Executors, TimeUnit}
import scala.reflect.internal.util.BatchSourceFile
import scala.tools.nsc.reporters.StoreReporter
import scala.tools.nsc.{Global, Settings}
import scala.tools.reflect.ToolBox
import scala.reflect.runtime.universe
import spark.Spark._

object Server extends App {
  port(sys.env.get("PORT").map(_.toInt).getOrElse(8642))
  ipAddress("0.0.0.0")

  // Hard limit for returned output/error size to avoid flooding clients/logs
  private val MaxReturnChars: Int = 4000
  private def truncateWithNotice(s: String, limit: Int = MaxReturnChars): String = {
    if (s == null) ""
    else if (s.length <= limit) s
    else s.take(limit) + s"\n... [truncated ${s.length - limit} chars]"
  }

  // Strip ANSI color sequences from logs
  def stripAnsi(s: String): String = s.replaceAll("\u001B\\[[;\\d]*m", "")

  // Extract concise compiler error: code line, caret line, and message
  def compressCompilerError(output: String): Option[String] = {
    val clean = stripAnsi(output)
    val lines = clean.split("\r?\n").toList
    val idx = lines.indexWhere(_.matches("^[^:]+:\\d+:\\s+.*$"))
    if (idx >= 0) {
      val header = lines(idx)
      val codeLine = lines.lift(idx + 1).getOrElse("")
      val caretLine = lines.lift(idx + 2).getOrElse("")
      val msg = header.replaceFirst("^[^:]+:\\d+:\\s*", "").trim
      val parts = List(codeLine, caretLine, msg).filter(_.trim.nonEmpty)
      Some(parts.mkString("\n"))
    } else None
  }

  // List of potentially dangerous patterns to check
  val dangerousPatterns: List[String] = List(
    "Runtime.getRuntime()",
    "sys.process",
    "new ProcessBuilder",
    "Files.delete",
    ".delete()"
  )

  def containsDangerousCode(code: String): Boolean = {
    dangerousPatterns.exists(pattern => code.contains(pattern))
  }

  // --- New Interpreter Setup ---
  // Settings: use the current class-path so that normal code compiles
  val settings = new Settings()
  settings.usejavacp.value = true // reuse the JVM classpath
  settings.outdir.value = "/tmp" // write classes to writable tmpfs

  // A new compiler instance that uses that reporter
  val g = new Global(settings, new StoreReporter(settings))

  // --- End New Interpreter Setup ---


  post("/execute", "application/json", (req, res) => {
    res.`type`("application/json")

    // For each request, create a new reporter and attach it to the compiler.
    // This is crucial for isolating compilation results between requests.
    val reporter = new StoreReporter(settings)
    g.reporter = reporter

    val body = req.body()
    val parsedJsonOpt: Option[ujson.Value] = try { Some(ujson.read(body)) } catch { case _: Throwable => None }
    val codeStr = parsedJsonOpt.flatMap(v => v.obj.get("code")).map(_.str).getOrElse("")

    // Optional per-request timeout in milliseconds via query param ?timeoutMs=...
    val timeoutMs: Long = (
      parsedJsonOpt
        .flatMap(v => v.obj.get("timeoutMs"))
        .flatMap {
          case ujson.Num(n) => Some(n.toLong)
          case ujson.Str(s) => scala.util.Try(s.toLong).toOption
          case _ => None
        }
      ).orElse({
        val p = req.queryParams("timeoutMs")
        if (p == null) None else scala.util.Try(p.toLong).toOption
      }).getOrElse(2000L)
    println(s"codeStr: $codeStr, timeoutMs: $timeoutMs")

    if (containsDangerousCode(codeStr)) {
      ujson.Obj("success" -> false, "error" -> "Dangerous code detected").render()
    } else if (codeStr.trim.isEmpty) {
      ujson.Obj("success" -> true, "output" -> "").render()
    } else {
      val executor = Executors.newSingleThreadExecutor()
      try {
        println(s"before future")
        val future = executor.submit(new Callable[ujson.Obj] {
          override def call(): ujson.Obj = {
            println(s"in future")
            // Prepare separate captures for out and err
            val outCapture = new java.io.ByteArrayOutputStream
            val errCapture = new java.io.ByteArrayOutputStream
            val outStream = new java.io.PrintStream(outCapture)
            val errStream = new java.io.PrintStream(errCapture)

            val originalOut = System.out
            val originalErr = System.err
            System.setOut(outStream)
            System.setErr(errStream)

            try {
              // 1. Compile Check
              println(s"before reporter.reset()")
              reporter.reset()
              val run = new g.Run
              // Wrap code in an object to make it a valid compilation unit
              val source = new BatchSourceFile("(input)", s"object Main { def exec(): Unit = {\n$codeStr\n} }")
              run.compileSources(List(source))
              println(s"after run.compileSources")

              val output = outCapture.toString()
              val errors = errCapture.toString()
              println(s"after output and errors")

              if (reporter.hasErrors) {
                println(s"reporter.hasErrors")
                val errorMessages = reporter.infos.map { info =>
                  if (info.severity == reporter.ERROR) {
                    val pos = info.pos
                    if (pos.isDefined) {
                      // Adjust line number because we wrapped the code
                      val line = pos.line - 1
                      val column = pos.column
                      // Get original line content, careful with split
                      val originalLine = codeStr.split('\n').lift(line - 1).getOrElse("")
                      s"""Error at line $line, column $column:
$originalLine
${" " * (column - 1)}^
${stripAnsi(info.msg)}"""
                    } else {
                      s"Error: ${stripAnsi(info.msg)}"
                    }
                  } else ""
                }.filter(_.nonEmpty).mkString("\n")

                println(s"after errorMessages")

                ujson.Obj(
                  "success" -> false,
                  "error" -> truncateWithNotice(errorMessages),
                  "output" -> truncateWithNotice(stripAnsi(output + errors))
                )
              } else {

                
                // 2. Evaluation
                try {
                  println(s"before outStream.flush() and errStream.flush()")
                  // Must flush streams before eval
                  outStream.flush()
                  errStream.flush()

                  // Toolbox for evaluation - must be created *after* System.out is redirected
                  val result: Any = scala.Console.withOut(outStream) {
                    scala.Console.withErr(errStream) {
                      val tb = universe.runtimeMirror(getClass.getClassLoader).mkToolBox()
                      tb.eval(tb.parse(s"{ $codeStr }"))
                    }
                  }

                  val finalOutput = outCapture.toString()
                  val finalErrors = errCapture.toString()
                  println(s"after tb.eval")
                  println(s"finalOutput: $finalOutput, finalErrors: $finalErrors")

                  ujson.Obj(
                    "success" -> true,
                    "output" -> truncateWithNotice(stripAnsi(finalOutput)),
                    "error" -> truncateWithNotice(stripAnsi(finalErrors)) // Include stderr even on success
                  )
                } catch {
                  case ex: Throwable =>
                    println(s"in catch with ex: $ex")
                    val sw = new java.io.StringWriter
                    ex.printStackTrace(new java.io.PrintWriter(sw))
                    val stack = sw.toString
                    val header = s"${ex.getClass.getName}: ${Option(ex.getMessage).getOrElse("")}"
                    val detailed = List(header, stack).filter(_.trim.nonEmpty).mkString("\n")
                    ujson.Obj(
                      "success" -> false,
                      "error" -> truncateWithNotice(detailed),
                      "output" -> truncateWithNotice(stripAnsi(outCapture.toString()))
                    )
                }
              }
            } finally {
              try {
                println(s"before outStream.flush() and errStream.flush()")
                outStream.flush(); errStream.flush()
              } finally {
                outStream.close(); errStream.close()
              }
              System.setOut(originalOut)
              System.setErr(originalErr)
            }
          }
        })

        try {
          val json = future.get(timeoutMs, TimeUnit.MILLISECONDS)
          json.render()
        } catch {
          case _: java.util.concurrent.TimeoutException =>
            println(s"in timeout exception")
            future.cancel(true)
            ujson.Obj("success" -> false, "error" -> s"Timeout after ${timeoutMs}ms").render()
        }
      } finally {
        println(s"before executor.shutdownNow()")
        executor.shutdownNow()
      }
    }
  })

  // Ensure the embedded server is initialized and keep the JVM alive.
  init()
  awaitInitialization()
  while (true) {
    Thread.sleep(60 * 60 * 1000) // 1 hour sleep, effectively blocks forever
  }
}