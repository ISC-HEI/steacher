import java.util.concurrent.{Callable, Executors, TimeUnit}
import java.net.URLClassLoader
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

  // --- Worker and Pool Implementation ---
  case class InterpreterWorker(workerId: Int) {
    private val executor = Executors.newSingleThreadExecutor()

    // Dedicated classloader per worker to isolate compiled artifacts
    private val workerClassLoader: URLClassLoader = {
      val cp = System.getProperty("java.class.path")
      val urls = cp.split(java.io.File.pathSeparator).map(p => new java.io.File(p).toURI.toURL)
      new URLClassLoader(urls, this.getClass.getClassLoader)
    }

    // Persistent compiler and toolbox per worker
    private val settings: Settings = {
      val s = new Settings()
      s.usejavacp.value = true
      s.outdir.value = "/tmp"
      s
    }
    private val reporter = new StoreReporter(settings)
    private val global = new Global(settings, reporter)
    private val mirror = universe.runtimeMirror(workerClassLoader)
    private val toolbox = mirror.mkToolBox()

    def prewarm(): Unit = {
      try toolbox.eval(toolbox.parse("{ val _ = 1 + 1; () }"))
      catch { case _: Throwable => () }
    }

    private def compileCheck(codeStr: String): String = {
      reporter.reset()
      val run = new global.Run
      val source = new BatchSourceFile("(input)", s"object Main { def exec(): Unit = {\n$codeStr\n} }")
      run.compileSources(List(source))
      val errorMessages = reporter.infos.map { info =>
        if (info.severity == reporter.ERROR) {
          val pos = info.pos
          if (pos.isDefined) {
            val line = pos.line - 1
            val column = pos.column
            val originalLine = codeStr.split('\n').lift(line - 1).getOrElse("")
            s"""Error at line $line, column $column:
$originalLine
${" " * (column - 1)}^
${stripAnsi(info.msg)}"""
          } else s"Error: ${stripAnsi(info.msg)}"
        } else ""
      }.filter(_.nonEmpty).mkString("\n")
      if (errorMessages.trim.isEmpty) "Unknown compilation error" else errorMessages
    }

    def execute(codeStr: String, timeoutMs: Long): ujson.Obj = {
      val task = new Callable[ujson.Obj] {
        override def call(): ujson.Obj = {
          val outCapture = new java.io.ByteArrayOutputStream
          val errCapture = new java.io.ByteArrayOutputStream
          val outStream = new java.io.PrintStream(outCapture)
          val errStream = new java.io.PrintStream(errCapture)
          try {
            // Eval-first fast path, capture only Scala Console output
            val _ = scala.Console.withOut(outStream) {
              scala.Console.withErr(errStream) {
                toolbox.eval(toolbox.parse(s"{ $codeStr }"))
              }
            }
            val finalOutput = outCapture.toString()
            val finalErrors = errCapture.toString()
            ujson.Obj(
              "success" -> true,
              "workerId" -> workerId,
              "output" -> truncateWithNotice(stripAnsi(finalOutput)),
              "error" -> truncateWithNotice(stripAnsi(finalErrors))
            )
          } catch {
            case _: scala.tools.reflect.ToolBoxError =>
              val errors = compileCheck(codeStr)
              val finalOutput = outCapture.toString()
              ujson.Obj(
                "success" -> false,
                "workerId" -> workerId,
                "error" -> truncateWithNotice(errors),
                "output" -> truncateWithNotice(stripAnsi(finalOutput))
              )
            case ex: Throwable =>
              val sw = new java.io.StringWriter
              ex.printStackTrace(new java.io.PrintWriter(sw))
              val stack = sw.toString
              val header = s"${ex.getClass.getName}: ${Option(ex.getMessage).getOrElse("")}"
              val detailed = List(header, stack).filter(_.trim.nonEmpty).mkString("\n")
              ujson.Obj(
                "success" -> false,
                "workerId" -> workerId,
                "error" -> truncateWithNotice(detailed),
                "output" -> truncateWithNotice(stripAnsi(outCapture.toString()))
              )
          } finally {
            try { outStream.flush(); errStream.flush() } finally { outStream.close(); errStream.close() }
          }
        }
      }
      val future = executor.submit(task)
      try future.get(timeoutMs, TimeUnit.MILLISECONDS)
      catch {
        case _: java.util.concurrent.TimeoutException =>
          future.cancel(true)
          ujson.Obj("success" -> false, "workerId" -> workerId, "error" -> s"Timeout after ${timeoutMs}ms")
      }
    }

    def shutdown(): Unit = executor.shutdownNow()
  }

  class WorkerPool(size: Int) {
    private val workers: Array[InterpreterWorker] = Array.tabulate(size)(i => new InterpreterWorker(i))
    workers.foreach(_.prewarm())
    @volatile private var nextIndex: Int = 0
    private def pickWorker(): InterpreterWorker = this.synchronized {
      val w = workers(nextIndex % workers.length)
      nextIndex = (nextIndex + 1) % workers.length
      w
    }
    def execute(codeStr: String, timeoutMs: Long): ujson.Obj = pickWorker().execute(codeStr, timeoutMs)
    def shutdown(): Unit = workers.foreach(_.shutdown())
  }
  // --- End Worker and Pool Implementation ---

  // Initialize pool
  private val poolSize: Int = sys.env.get("POOL_SIZE").flatMap(s => scala.util.Try(s.toInt).toOption).getOrElse(4)
  private val pool = new WorkerPool(poolSize)


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
    println(s"incoming request timeoutMs=$timeoutMs")

    if (containsDangerousCode(codeStr)) {
      ujson.Obj("success" -> false, "error" -> "Dangerous code detected").render()
    } else if (codeStr.trim.isEmpty) {
      ujson.Obj("success" -> true, "output" -> "").render()
    } else {
      val json = pool.execute(codeStr, timeoutMs)
      json.render()
    }
  })

  // Ensure the embedded server is initialized and keep the JVM alive.
  init()
  awaitInitialization()
  while (true) {
    Thread.sleep(60 * 60 * 1000) // 1 hour sleep, effectively blocks forever
  }
}