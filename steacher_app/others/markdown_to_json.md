I want you to create a json file with the "template/export/course.json" structure, using the content of the "AlLin" directory. The name of the course will be "AlLin Serie", each "Serie x.md" file is a module and you need to split the exercises in the file into individual exercises. There should be text in german and french, those are the same exercises in two different languages and should be treated as such in the json, with the json language handling like this: "fr":[french exercise], "de":[german exercise]. For exemple with "Série 1.md", You have the first exercise in german:
1.  Gegeben sind $g: y = \frac{1}{2}x - 1$ und $P = (1, -4)$.
	(a) Geben Sie die Gleichung der senkrechten Geraden zu $g$ durch $P$ (Lotgerade).
	(b) Welcher Punkt von $g$ liegt dem Punkt $P$ am nächsten (Lotfusspunkt)?

the first exercise in french:
1.  On considère la droite $g: y = \frac{1}{2}x - 1$ et le point $P = (1, -4)$.
	(a) Donner l'équation de la droite normale (c.-à-d. perpendiculaire) à $g$ passant par $P$.
	(b) Quel point de $g$ est le plus proche de $P$ ?

And the solutions to these exercises:
1.  (a) $2x + y = -2$
	(b) $(x, y) = \left(-\frac{2}{5}, -\frac{6}{5}\right)$

there will sometimes be solutions in both german and french, you must always take the french version.
The end result must be stored in "course_allin_series.json".