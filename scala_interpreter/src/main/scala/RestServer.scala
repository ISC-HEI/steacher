import ammonite.Main
import ammonite.util.Res
import spark.Spark._
import java.util.concurrent.{Executors, Callable, TimeUnit}

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

  post("/execute", "application/json", (req, res) => {
    res.`type`("application/json")

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

    if (containsDangerousCode(codeStr)) {
      ujson.Obj("success" -> false, "error" -> "Dangerous code detected").render()
    } else if (codeStr.trim.isEmpty) {
      ujson.Obj("success" -> true, "output" -> "").render()
    } else {
      val executor = Executors.newSingleThreadExecutor()
      try {
        val future = executor.submit(new Callable[ujson.Obj] {
          override def call(): ujson.Obj = {
            // Prepare capture BEFORE interpreter creation so Ammonite binds to these streams
            val outCapture = new java.io.ByteArrayOutputStream
            val printStream = new java.io.PrintStream(outCapture)

            val originalOut = System.out
            val originalErr = System.err
            System.setOut(printStream)
            System.setErr(printStream)

            try {
              Main().instantiateInterpreter() match {
                case Right(interp) =>
                  var line = 0
                  def nextLine(): Unit = line += 1

                  val result = Console.withOut(printStream) {
                    Console.withErr(printStream) {
                      interp.processExec(codeStr, line, nextLine)
                    }
                  }

                  val output = outCapture.toString()
                  val safeOutput = truncateWithNotice(output)

                  result match {
                    case Res.Success(_) =>
                      ujson.Obj("success" -> true, "output" -> safeOutput)
                    case Res.Failure(msg) =>
                      val detailed = compressCompilerError(output).getOrElse {
                        if (output.trim.isEmpty) msg else s"$msg\n$output"
                      }
                      val safeError = truncateWithNotice(detailed)
                      ujson.Obj("success" -> false, "error" -> safeError, "output" -> safeOutput)
                    case Res.Exception(ex, _) =>
                      val sw = new java.io.StringWriter
                      ex.printStackTrace(new java.io.PrintWriter(sw))
                      val stack = sw.toString
                      val header = s"${ex.getClass.getName}: ${Option(ex.getMessage).getOrElse("")}"
                      val detailed = List(header, output, stack).filter(_.trim.nonEmpty).mkString("\n")
                      val safeError = truncateWithNotice(detailed)
                      ujson.Obj("success" -> false, "error" -> safeError, "output" -> safeOutput)
                    case other =>
                      val detailed = if (output.trim.isEmpty) s"Other: $other" else s"Other: $other\n$output"
                      val safeError = truncateWithNotice(detailed)
                      ujson.Obj("success" -> false, "error" -> safeError, "output" -> safeOutput)
                  }
                case Left((failing, _)) =>
                  ujson.Obj("success" -> false, "error" -> s"Failed to create interpreter: $failing")
              }
            } finally {
              try printStream.flush() finally printStream.close()
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
            future.cancel(true)
            ujson.Obj("success" -> false, "error" -> s"Timeout after ${timeoutMs}ms").render()
        }
      } finally {
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
