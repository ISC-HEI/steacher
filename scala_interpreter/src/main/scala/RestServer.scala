import ammonite.Main
import ammonite.util.Res
import spark.Spark._
import java.util.concurrent.{Executors, Callable, TimeUnit}

object Server extends App {
  port(sys.env.get("PORT").map(_.toInt).getOrElse(8642))
  ipAddress("0.0.0.0")

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
    val codeStr = try {
      val v = ujson.read(body)
      v.obj.get("code").map(_.str).getOrElse("")
    } catch {
      case _: Throwable => ""
    }

    // Optional per-request timeout in milliseconds via query param ?timeoutMs=...
    val timeoutMs: Long = try {
      val p = req.queryParams("timeoutMs")
      if (p == null) 2000L else p.toLong
    } catch { case _: Throwable => 2000L }

    if (containsDangerousCode(codeStr)) {
      ujson.Obj("success" -> false, "error" -> "Dangerous code detected").render()
    } else if (codeStr.trim.isEmpty) {
      ujson.Obj("success" -> true, "output" -> "").render()
    } else {
      val executor = Executors.newSingleThreadExecutor()
      try {
        val future = executor.submit(new Callable[ujson.Obj] {
          override def call(): ujson.Obj = {
            Main().instantiateInterpreter() match {
              case Right(interp) =>
                val outCapture = new java.io.ByteArrayOutputStream
                val printStream = new java.io.PrintStream(outCapture)

                var line = 0
                def nextLine(): Unit = line += 1

                val result = Console.withOut(printStream) {
                  Console.withErr(printStream) {
                    interp.processExec(codeStr, line, nextLine)
                  }
                }

                val output = outCapture.toString()

                result match {
                  case Res.Success(_) => ujson.Obj("success" -> true, "output" -> output)
                  case Res.Failure(msg) => ujson.Obj("success" -> false, "error" -> msg, "output" -> output)
                  case Res.Exception(ex, _) => ujson.Obj("success" -> false, "error" -> ex.getMessage, "output" -> output)
                  case other => ujson.Obj("success" -> false, "error" -> s"Other: $other", "output" -> output)
                }
              case Left((failing, _)) =>
                ujson.Obj("success" -> false, "error" -> s"Failed to create interpreter: $failing")
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
}
