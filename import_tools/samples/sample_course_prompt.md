## Course objectives

Here are the major objective of this class: 

* Know and apply the basic concepts and techniques of analytical and vector geometry in dimensions 2 and 3, of trigonometry, and of systems of linear equations
* Illustrate these concepts and techniques using examples and counterexamples
* Use these concepts and techniques with a view to solving problems
* Communicate one's reasoning in a clear, structured, and complete manner

## Exercices

Almost all students will work with paper/pencil. Thus, encourage them to upload their work by taking a picture of their sheet. All open_question exercise types should allow for image upload.


## Solutions

**Important:** A student's solution is correct if it is mathematically equivalent to any provided solution, even if written differently. For example:
- $(x - 3)^2 + (y + 4)^2 = 36$ (standard form)
- $(y + 4)^2 + (x - 3)^2 = 36$ (terms reordered)
- $x^2 - 6x + 9 + y^2 + 8y + 16 = 36$ (expanded form)
- $x^2 + y^2 - 6x + 8y - 11 = 0$ (general form)

All of these are correct answers for a circle equation. Always verify mathematical equivalence, not just textual matching.

## Complete math script

Below is the complete script of this class. Use it to ground your answers in the theory that the teacher gave. Refer to its chapters with the correct number so that students can link the present exercise with the theory.

### 1 Droites et cercles

#### 1.1 Droites

*   La droite $d$ par les points $P_1(x_1, y_1)$ et $P_2(x_2, y_2)$ a la pente $a = \frac{y_2 - y_1}{x_2 - x_1}$ (si $x_2 \neq x_1$).
    Le nombre $b$ tel que $d$ coupe l'axe $Oy$ en $(0,b)$ est appelé son ordonnée à l'origine, et $d$ a comme équation
    $$d : \quad y = ax + b.$$
    Si $x_2 = x_1$, alors $d$ est verticale et son équation est $d : \quad x = x_1$.
*   La droite $d$ de pente $a$ par le point $P(x_0, y_0)$ a comme équation
    $$d : \quad y = a(x - x_0) + y_0.$$
*   **Théorème :** Deux droites $d_1$ et $d_2$ de pentes respectives $a_1$ et $a_2$ sont perpendiculaires si et seulement si $a_1 \cdot a_2 = -1$.

#### 1.2 Cercles

*   **Théorème :** La distance entre les points $P_1(x_1, y_1)$ et $P_2(x_2, y_2)$ est donnée par
    $$\text{dist}(P_1, P_2) = \sqrt{(x_2 - x_1)^2 + (y_2 - y_1)^2}.$$
*   Le cercle $\Gamma$ de centre $C(x_0, y_0)$ et de rayon $r \geq 0$ a comme équation
    $$\Gamma : \quad (x - x_0)^2 + (y - y_0)^2 = r^2.$$

### 2 Trigonométrie

#### 2.1 Angles

*   Si deux droites se coupent en un point $P$, et $\Gamma$ est le cercle de centre $P$ et de rayon $r > 0$, l'angle $\alpha$ formé par les deux droites est donné par le rapport
    $$\alpha = \frac{l}{r}, \text{ où } l \text{ est la longueur de l'arc du}$$
    cercle $\Gamma$ entre les deux droites. C'est une grandeur adimensionnelle, qu'on quantifie par l'"unité" radian.
*   L'angle plein mesure $2\pi$ ($\leftrightarrow 360^\circ$), l'angle plat mesure $\pi$ ($\leftrightarrow 180^\circ$), et l'angle droit mesure $\frac{\pi}{2}$ ($\leftrightarrow 90^\circ$).

#### 2.2 Le cercle trigonométrique

*   Le cercle trigonométrique est le cercle-unité, d'équation $x^2 + y^2 = 1$.
*   Sur le cercle trigonométrique, les angles sont mesurés à partir du demi-axe des $x$ positifs. Le sens anti-horaire (sens trigonométrique) correspond à des angles positifs.
*   A un angle $\alpha \in \mathbb{R}$ correspond un unique point $P = P(\alpha)$ du cercle trigonométrique tel que $\alpha = \angle((1,0), O, P)$.
    La coordonnée horizontale de $P$ est appelée le cosinus de $\alpha$, et la coordonnée verticale de $P$ est appelée le sinus de $\alpha$ : $P(\cos \alpha, \sin \alpha)$.
    Si $\alpha \neq \frac{\pi}{2} + k\pi$, $k \in \mathbb{Z}$, alors la droite $(OP)$ coupe la droite $x=1$ (tangente au cercle trigonométrique en $(1,0)$) en un point $(1, t)$. La coordonnée $t$ est appelée la tangente de $\alpha$ : $t = \tan \alpha$.
    Si $\alpha \neq k\pi$, $k \in \mathbb{Z}$, la cotangente de $\alpha$ est la coordonnée $c$ du point $(c, 1)$ d'intersection entre la droite $(OP)$ et la droite $y=1$ (tangente au cercle trigonométrique en $(0,1)$) : $c = \cot \alpha$.

*   **Propriétés :** pour tout $\alpha$ tel que les fonctions sont définies, on a :
    *   $\tan \alpha = \frac{\sin \alpha}{\cos \alpha} \quad ; \quad \cot \alpha = \frac{1}{\tan \alpha}$.
    *   $\cos \alpha, \sin \alpha \in [-1, 1] \quad ; \quad \tan \alpha, \cot \alpha \in \mathbb{R}$.
    *   $\cos(\alpha + k \cdot 2\pi) = \cos \alpha \quad ; \quad \sin(\alpha + k \cdot 2\pi) = \sin \alpha$, pour tout $k \in \mathbb{Z}$.
    *   $\cos^2 \alpha + \sin^2 \alpha = 1$.
    *   $1 + \tan^2 \alpha = \frac{1}{\cos^2 \alpha}$.
*   Symétries particulières :
    *   d'axe $Ox$ : $\cos(-\alpha) = \cos \alpha$, $\sin(-\alpha) = -\sin \alpha$, $\tan(-\alpha) = -\tan \alpha$
    *   d'axe $Oy$ : $\cos(\pi - \alpha) = -\cos \alpha$, $\sin(\pi - \alpha) = \sin \alpha$, $\tan(\pi - \alpha) = -\tan \alpha$
    *   de centre $O$ : $\cos(\pi + \alpha) = -\cos \alpha$, $\sin(\pi + \alpha) = -\sin \alpha$, $\tan(\pi + \alpha) = \tan \alpha$
    *   d'axe $y=x$ : $\cos \left(\frac{\pi}{2} - \alpha\right) = \sin \alpha$, $\sin \left(\frac{\pi}{2} - \alpha\right) = \cos \alpha$, $\tan \left(\frac{\pi}{2} - \alpha\right) = \cot \alpha$
*   Quelques valeurs dans le premier quadrant :

| $\alpha$ | $0$ | $\pi/6$ | $\pi/4$ | $\pi/3$ | $\pi/2$ |
| :---: | :---: | :---: | :---: | :---: | :---: |
| | $0^\circ$ | $30^\circ$ | $45^\circ$ | $60^\circ$ | $90^\circ$ |
| $\sin \alpha$ | $0$ | $1/2$ | $\sqrt{2}/2$ | $\sqrt{3}/2$ | $1$ |
| $\cos \alpha$ | $1$ | $\sqrt{3}/2$ | $\sqrt{2}/2$ | $1/2$ | $0$ |
| $\tan \alpha$ | $0$ | $\sqrt{3}/3$ | $1$ | $\sqrt{3}$ | --- |

#### 2.3 Les fonctions trigonométriques et leurs inverses

*   Graphes des fonctions sinus, cosinus et tangente :
    *(Graphique omis)*
*   Pour une longueur $x \in [-1, 1]$, l'unique angle $\alpha \in [0, \pi]$ tel que $\cos \alpha = x$ est appelé l'arc cosinus de $x$, noté $\alpha = \arccos x$.
*   Pour une longueur $y \in [-1, 1]$, l'unique angle $\alpha \in [-\frac{\pi}{2}, \frac{\pi}{2}]$ tel que $\sin \alpha = y$ est appelé l'arc sinus de $y$, noté $\alpha = \arcsin y$.
*   Pour une longueur $t \in \mathbb{R}$, l'unique angle $\alpha \in ]-\frac{\pi}{2}, \frac{\pi}{2}[$ tel que $\tan \alpha = t$ est appelé l'arc tangente de $t$, noté $\alpha = \arctan t$.
*   Graphes des fonctions arc sinus, arc cosinus et arc tangente :
    *(Graphique omis)*
*   Résolution d'équations trigonométriques :
    *   $\cos \alpha = \cos \beta \Longleftrightarrow \alpha = \pm \beta + k \cdot 2\pi, \, k \in \mathbb{Z}$.
    *   $\sin \alpha = \sin \beta \Longleftrightarrow (\alpha = \beta + k \cdot 2\pi, \, k \in \mathbb{Z} \text{ ou } \alpha = \pi - \beta + k \cdot 2\pi, \, k \in \mathbb{Z})$.
    *   $\sin \alpha = \cos \beta \Longleftrightarrow \cos \left(\frac{\pi}{2} - \alpha\right) = \cos \beta \Longleftrightarrow \sin \alpha = \sin \left(\frac{\pi}{2} - \beta\right)$
        (et on retrouve une des deux lignes précédentes)
    *   $\tan \alpha = \tan \beta \Longleftrightarrow \alpha = \beta + k \cdot \pi, \, k \in \mathbb{Z}$.

#### 2.4 Triangles rectangles

*   Notations standard pour des triangles (rectangles ou non) :
    *   Sommets : $A, B, C$.
    *   Angles : $\alpha = \angle(BAC)$, $\beta = \angle(ABC)$, $\gamma = \angle(ACB)$.
    *   Longueurs des côtés : $a = \text{dist}(B, C)$, $b = \text{dist}(A, C)$, $c = \text{dist}(A, B)$.
*   Si le triangle $ABC$ est rectangle, disons en $B$, alors on peut le "poser sur l'axe $Ox$" de sorte que $A$ soit à l'origine $(0,0)$ et que $B$ soit sur le point $(c,0)$. Dans ce cas, l'angle à l'origine est $\alpha$, et le triangle $ABC$ est semblable au triangle de sommets $(0,0)$, $(\cos \alpha, 0)$, $(\cos \alpha, \sin \alpha)$.

    On peut alors déduire les relations
    $$\cos \alpha = \frac{a}{b} = \frac{\text{adjacent}}{\text{hypothénuse}}, \quad \sin \alpha = \frac{c}{b} = \frac{\text{opposé}}{\text{hypothénuse}}, \quad \tan \alpha = \frac{a}{c} = \frac{\text{opposé}}{\text{adjacent}}$$

#### 2.5 Triangles quelconques

On considère un triangle $\Delta = \Delta(ABC)$ quelconque, c'est-à-dire que ses angles et ses côtés sont de mesure arbitraire.

*   **Théorème :** L'aire du triangle $\Delta = \Delta(ABC)$ est donnée par
    $$\text{aire}(\Delta) = \frac{1}{2} ab \sin \gamma = \frac{1}{2} ac \sin \beta = \frac{1}{2} bc \sin \alpha.$$
*   **Théorème du sinus :**
    $$\frac{a}{\sin \alpha} = \frac{b}{\sin \beta} = \frac{c}{\sin \gamma}.$$
*   **Théorème du cosinus :**
    $$a^2 = b^2 + c^2 - 2bc \cos \alpha \quad , \quad b^2 = a^2 + c^2 - 2ac \cos \beta \quad , \quad c^2 = a^2 + b^2 - 2ab \cos \gamma.$$
*   **Théorème de la bissectrice :** On dénote par $u$ (resp. $v$) la longueur du segment déterminé par la bissectrice de l'angle $\alpha$ sur le côté $a$ et qui est adjacent au côté $b$ (resp. $c$).
    Alors
    $$\frac{u}{v} = \frac{b}{c}.$$

#### 2.6 Autres formules trigonométriques

*   **Théorème (addition) :**
    *   $\sin(\alpha \pm \beta) = \sin \alpha \cos \beta \pm \cos \alpha \sin \beta$
    *   $\cos(\alpha \pm \beta) = \cos \alpha \cos \beta \mp \sin \alpha \sin \beta$
    *   $\tan(\alpha \pm \beta) = \frac{\tan \alpha \pm \tan \beta}{1 \mp \tan \alpha \tan \beta}$
*   **Théorème (duplication) :**
    *   $\sin(2\alpha) = 2 \sin \alpha \cos \alpha$
    *   $\cos(2\alpha) = \cos^2 \alpha - \sin^2 \alpha = 1 - 2\sin^2 \alpha = 2\cos^2 \alpha - 1$
*   **Théorème (bissection) :**
    *   $2\sin^2 \frac{\alpha}{2} = 1 - \cos \alpha$
    *   $2\cos^2 \frac{\alpha}{2} = 1 + \cos \alpha$
*   **Théorème (somme $\to$ produit) :**
    *   $\sin \alpha \pm \sin \beta = 2 \sin \frac{\alpha \pm \beta}{2} \cdot \cos \frac{\alpha \mp \beta}{2}$
    *   $\cos \alpha + \cos \beta = 2 \cos \frac{\alpha + \beta}{2} \cdot \cos \frac{\alpha - \beta}{2}$
    *   $\cos \alpha - \cos \beta = -2 \sin \frac{\alpha + \beta}{2} \cdot \sin \frac{\alpha - \beta}{2}$
*   **Théorème (produit $\to$ somme) :**
    *   $\sin \alpha \cdot \sin \beta = \frac{1}{2} (\cos(\alpha - \beta) - \cos(\alpha + \beta))$
    *   $\sin \alpha \cdot \cos \beta = \frac{1}{2} (\sin(\alpha - \beta) + \sin(\alpha + \beta))$
    *   $\cos \alpha \cdot \cos \beta = \frac{1}{2} (\cos(\alpha - \beta) + \cos(\alpha + \beta))$

### 3 Géométrie vectorielle

Dans ce qui suit, on se place dans l'espace $\mathbb{R}^3$. Cependant, la discussion reste valide si on est dans le plan $\mathbb{R}^2$, en "supprimant la dernière coordonnée".

#### 3.1 Vecteurs

*   Pour $A, B \in \mathbb{R}^3$, le vecteur $\vec{AB}$ est l'ensemble des flèches qui sont
    *   parallèles à la droite $(AB)$ (la direction de $\vec{AB}$),
    *   de sens $A \to B$, et
    *   de longueur $||\vec{AB}|| := \text{dist}(A, B)$ (la norme de $\vec{AB}$).
*   Remarque : la norme de $\vec{AB}$ est parfois aussi notée $|\vec{AB}|$.
*   Le vecteur $\vec{v}$ est dit normé si $||\vec{v}|| = 1$.
*   Si $O(0,0,0)$ désigne l'origine de $\mathbb{R}^3$, il existe un unique point $C(c_1, c_2, c_3) \in \mathbb{R}^3$ tel que $\vec{OC} = \vec{AB}$. Dans ce cas, le vecteur $\vec{AB}$ est appelé le vecteur-lieu du point $C$.
    Cette procédure donne une manière standardisée de décrire un vecteur. Dans ce cas, on écrit $\vec{AB} = \begin{pmatrix} c_1 \\ c_2 \\ c_3 \end{pmatrix}$. Les nombres $c_1$, $c_2$, et $c_3$ (les coordonnées du point $C$) sont appelées les composantes du vecteur $\vec{AB}$. La notation verticale permet de distinguer le vecteur $\vec{OC}$ du point $C$.
*   **Théorème :** La norme de $\vec{v} = \begin{pmatrix} v_1 \\ v_2 \\ v_3 \end{pmatrix}$ est donnée par $||\vec{v}|| = \sqrt{v_1^2 + v_2^2 + v_3^2}$.
*   Le vecteur nul est le vecteur $\vec{o} := \vec{OO} = \begin{pmatrix} 0 \\ 0 \\ 0 \end{pmatrix}$.
*   Le vecteur opposé au vecteur $\vec{v}$ est le vecteur $-\vec{v}$ qui a la même direction et la même norme que $\vec{v}$, mais qui est de sens opposé : si $\vec{v} = \begin{pmatrix} v_1 \\ v_2 \\ v_3 \end{pmatrix}$, alors son vecteur opposé est $-\vec{v} = \begin{pmatrix} -v_1 \\ -v_2 \\ -v_3 \end{pmatrix}$.
*   Pour $\vec{u} = \vec{AB}$ et $\vec{v} = \vec{CD}$, la somme $\vec{u} + \vec{v}$ est le vecteur $\vec{AE}$, où $E \in \mathbb{R}^3$ est l'unique point tel que $\vec{CD} = \vec{BE}$.
*   **Propriétés :**
    *   $\vec{u} + \vec{v} = \vec{v} + \vec{u}$
    *   $(\vec{u} + \vec{v}) + \vec{w} = \vec{u} + (\vec{v} + \vec{w})$
    *   $\vec{u} + \vec{o} = \vec{o} + \vec{u} = \vec{u}$
    *   $\vec{v} + (-\vec{v}) = \vec{o}$
    *   Si $\vec{u} = \begin{pmatrix} u_1 \\ u_2 \\ u_3 \end{pmatrix}$ et $\vec{v} = \begin{pmatrix} v_1 \\ v_2 \\ v_3 \end{pmatrix}$, alors $\vec{u} + \vec{v} = \begin{pmatrix} u_1 + v_1 \\ u_2 + v_2 \\ u_3 + v_3 \end{pmatrix}$.
*   La différence de $\vec{u}$ et $\vec{v}$ est le vecteur $\vec{u} - \vec{v} := \vec{u} + (-\vec{v})$.
*   **Théorème :** Si $A(a_1, a_2, a_3)$ et $B(b_1, b_2, b_3)$, alors $\vec{AB} = \vec{OB} - \vec{OA} = \begin{pmatrix} b_1 - a_1 \\ b_2 - a_2 \\ b_3 - a_3 \end{pmatrix}$.
*   La multiplication du vecteur $\vec{v}$ par le scalaire $\lambda \in \mathbb{R}$ est le vecteur $\lambda \cdot \vec{v} =: \lambda \vec{v}$ qui a
    *   la même direction que $\vec{v}$,
    *   le même sens que $\vec{v}$ si $\lambda \geq 0$, et le sens opposé si $\lambda < 0$, et
    *   la norme $||\lambda \vec{v}|| = |\lambda| \cdot ||\vec{v}||$.
*   **Propriétés :**
    *   $(\lambda + \mu) \cdot \vec{u} = \lambda \vec{u} + \mu \vec{u}$
    *   $\lambda \cdot (\vec{u} + \vec{v}) = \lambda \vec{u} + \lambda \vec{v}$
    *   $(\lambda \cdot \mu) \vec{v} = \lambda \cdot (\mu \vec{v})$
    *   Si $\vec{v} = \begin{pmatrix} v_1 \\ v_2 \\ v_3 \end{pmatrix}$, alors $\lambda \vec{v} = \begin{pmatrix} \lambda v_1 \\ \lambda v_2 \\ \lambda v_3 \end{pmatrix}$.
*   Le point $C$ divise le segment $[A, B]$ selon une proportion $\alpha : \beta$ (dans cet ordre) si $\frac{||\vec{AC}||}{||\vec{CB}||} = \frac{\alpha}{\beta}$. Dans ce cas, $||\vec{AC}|| = \frac{\alpha}{\alpha + \beta} \cdot ||\vec{AB}||$ et $||\vec{CB}|| = \frac{\beta}{\alpha + \beta} \cdot ||\vec{AB}||$.

#### 3.2 Combinaisons linéaires

*   Le vecteur $\vec{v}$ est combinaison linéaire de $\vec{u_1}, ..., \vec{u_k}$ s'il existe $\lambda_1, ..., \lambda_k \in \mathbb{R}$ tels que
    $$\vec{v} = \lambda_1 \vec{u_1} + ... + \lambda_k \vec{u_k} = \sum_{j=1}^k \lambda_j \vec{u_j}.$$
*   Des vecteurs $\vec{v_1}, ..., \vec{v_k}$ sont linéairement indépendants si aucun d'entre eux n'est combinaison linéaire des autres. Sinon, ils sont dits linéairement dépendants.
*   **Théorème :** Les vecteurs $\vec{v_1}, ..., \vec{v_k}$ sont linéairement indépendants si
    $$\lambda_1 \vec{v_1} + ... + \lambda_k \vec{v_k} = \vec{o} \quad \Longrightarrow \quad \lambda_1 = ... = \lambda_k = 0,$$
    c'est-à-dire si seule la combinaison linéaire triviale de ces vecteurs permet d'obtenir le vecteur nul.
*   Deux vecteurs sont dits colinéaires s'ils ont la même direction, c'est-à-dire s'ils sont multiples l'un de l'autre.
*   Une base de $\mathbb{R}^3$ est une famille de trois vecteurs linéairement indépendants.
*   **Théorème :** Si $\{\vec{v_1}, \vec{v_2}, \vec{v_3}\}$ est une base de $\mathbb{R}^3$, alors tout vecteur de $\mathbb{R}^3$ s'écrit comme combinaison linéaire unique des vecteurs de cette base. Plus précisément :
    *   $\forall \vec{x} \in \mathbb{R}^3, \exists \lambda_1, \lambda_2, \lambda_3 \in \mathbb{R}$ tels que $\vec{x} = \lambda_1 \vec{v_1} + \lambda_2 \vec{v_2} + \lambda_3 \vec{v_3}$, et
    *   $\lambda_1 \vec{v_1} + \lambda_2 \vec{v_2} + \lambda_3 \vec{v_3} = \mu_1 \vec{v_1} + \mu_2 \vec{v_2} + \mu_3 \vec{v_3} \quad \Longrightarrow \quad \lambda_1 = \mu_1, \lambda_2 = \mu_2, \lambda_3 = \mu_3$.

#### 3.3 Droites

*   Une droite $d$ par le point $A \in \mathbb{R}^3$ et de vecteur directeur $\vec{d}$ est l'ensemble
    $$d = \{ P \in \mathbb{R}^3 \, | \, \vec{AP} \parallel \vec{d} \}.$$
*   L'horaire d'un point matériel situé au temps $t=0$ au point $A$ et de vecteur-vitesse $\vec{d}$ est donné par
    $$\vec{r(t)} = \vec{OA} + t \cdot \vec{d}, \quad t \in \mathbb{R}.$$
    La vitesse du point est alors donnée par $||\vec{d}||$.
*   Positions relatives de deux droites $d_1$ et $d_2$ données par $\vec{r_1(t)} = \vec{OA_1} + t \cdot \vec{d_1}$ et $\vec{r_2(t)} = \vec{OA_2} + t \cdot \vec{d_2}$, $t \in \mathbb{R}$, respectivement :
    (1) Si $\vec{d_1} \parallel \vec{d_2}$, alors
        (1.1) si $A_1 \in d_2$ (ou $A_2 \in d_1$, ou $\vec{A_1A_2} \parallel \vec{d_1}$, ou $\vec{A_1A_2} \parallel \vec{d_2}$), alors $d_1 = d_2$ (elles sont confondues).
        (1.2) sinon, $d_1 \parallel d_2$ et $d_1 \neq d_2$ (elles sont (strictement) parallèles)
    (2) sinon, alors
        (2.1) si l'équation $\vec{r_1(t)} = \vec{r_2(s)}$ possède une (unique) solution $(t_{\cap}, s_{\cap}) \in \mathbb{R}^2$, alors $d_1 \cap d_2 = \{P\}$ (elles sont sécantes).
        (2.2) sinon, les droites sont gauches.
*   Remarque : si $\vec{r_1}$ et $\vec{r_2}$ sont les horaires de deux points matériels et que dans la condition (2.1) ci-dessus on a $t_{\cap} = s_{\cap}$, alors les deux points matériels entrent en collision. Sinon, leurs trajectoires se croisent (sans collision).

#### 3.4 Produit scalaire

*   Si $\varphi \in [0, \pi]$ désigne l'angle entre les vecteurs $\vec{u}$ et $\vec{v}$, alors le produit scalaire de $\vec{u}$ et $\vec{v}$ est donné par
    $$\vec{u} \bullet \vec{v} := ||\vec{u}|| \cdot ||\vec{v}|| \cdot \cos \varphi.$$
*   Remarque : le produit scalaire de $\vec{u}$ et $\vec{v}$ est parfois noté $\vec{u} \cdot \vec{v}$.
*   **Théorème :** Si $\vec{u} = \begin{pmatrix} u_1 \\ u_2 \\ u_3 \end{pmatrix}$ et $\vec{v} = \begin{pmatrix} v_1 \\ v_2 \\ v_3 \end{pmatrix}$, alors
    $$\vec{u} \bullet \vec{v} = u_1 v_1 + u_2 v_2 + u_3 v_3 = \sum_{k=1}^3 u_k v_k.$$
*   **Propriétés :** Si $\vec{u}, \vec{v} \neq \vec{o}$, alors
    *   $\vec{u} \bullet \vec{v} \left\{ \begin{matrix} > \\ = \\ < \end{matrix} \right\} 0 \Longleftrightarrow \varphi \left\{ \begin{matrix} \text{aigu} \\ \text{droit} \\ \text{obtus} \end{matrix} \right\}$
    *   $\vec{u} \bullet \vec{u} = ||\vec{u}||^2$
    *   $\varphi = \arccos \frac{\vec{u} \bullet \vec{v}}{||\vec{u}|| \cdot ||\vec{v}||}$
    *   $\vec{u} \bullet \vec{v} = \vec{v} \bullet \vec{u}$
    *   $\vec{u} \bullet (\vec{v} + \vec{w}) = \vec{u} \bullet \vec{v} + \vec{u} \bullet \vec{w}$
    *   $(\lambda \vec{u}) \bullet (\mu \vec{v}) = \lambda \mu (\vec{u} \bullet \vec{v})$
*   Les vecteurs $\{\vec{v_1}, \vec{v_2}, \vec{v_3}\}$ forment une base orthonormée de $\mathbb{R}^3$ si les vecteurs sont tous de norme 1 et sont deux à deux orthogonaux, c'est-à-dire si $\vec{v_i} \bullet \vec{v_j} = \begin{cases} 0 & \text{si } i \neq j \\ 1 & \text{si } i = j \end{cases}$
*   **Théorème :** Si $\{\vec{v_1}, \vec{v_2}, \vec{v_3}\}$ est une base orthonormée de $\mathbb{R}^3$ et que $\vec{x}$ est un vecteur quelconque de $\mathbb{R}^3$, alors $\vec{x} = \sum_{k=1}^3 (\vec{x} \bullet \vec{v_k}) \vec{v_k}$.
*   La projection orthogonale de $\vec{u}$ sur $\vec{v}$ est le vecteur $\vec{u}_{\vec{v}} = \frac{\vec{u} \bullet \vec{v}}{\vec{v} \bullet \vec{v}} \cdot \vec{v}$

#### 3.5 Plans

*   Pour $A \in \mathbb{R}^3$ et $\vec{v_1}$ et $\vec{v_2}$ deux vecteurs linéairement indépendants, un plan $\Pi \subset \mathbb{R}^3$ est un ensemble de la forme
    $$\Pi = \{ P \in \mathbb{R}^3 \, | \, \vec{OP} = \vec{OA} + \lambda \cdot \vec{v_1} + \mu \cdot \vec{v_2}, \, \lambda, \mu \in \mathbb{R} \}.$$
    En pratique, il est avantageux de décrire $\Pi$ à l'aide d'un vecteur normal $\vec{n} \perp \vec{v_1}, \vec{v_2}$.
    Dans ce cas, on peut écrire
    $$\Pi = \{ P \in \mathbb{R}^3 \, | \, \vec{AP} \bullet \vec{n} = 0 \}.$$
    Si $\vec{n} = \begin{pmatrix} a \\ b \\ c \end{pmatrix}$, alors $\Pi$ possède l'équation
    $$\Pi : \quad ax + by + cz = d,$$
    où $d = \vec{OA} \bullet \vec{n}$.
*   **Conséquences :**
    *   La projection orthogonale $Q$ du point $P \in \mathbb{R}^3$ sur le plan $\Pi$ contenant le point $A$ et de vecteur normal $\vec{n}$ est donnée par $\vec{OQ} = \vec{OP} - \frac{\vec{AP} \bullet \vec{n}}{\vec{n} \bullet \vec{n}} \cdot \vec{n}$.
    *   Dans le même contexte, la distance entre le point $P$ et le plan $\Pi$ est donnée par $\text{dist}(P, \Pi) = \frac{|\vec{AP} \bullet \vec{n}|}{||\vec{n}||}$.
    *   L'angle entre les plans $\Pi_1$ et $\Pi_2$ de vecteurs normaux respectifs $\vec{n_1}$ et $\vec{n_2}$ est donné par $\angle(\Pi_1, \Pi_2) = \angle(\vec{n_1}, \vec{n_2}) = \arccos \frac{\vec{n_1} \bullet \vec{n_2}}{||\vec{n_1}|| \cdot ||\vec{n_2}||}$.
    *   L'angle entre la droite $d$ de vecteur directeur $\vec{d}$ et le plan $\Pi$ de vecteur normal $\vec{n}$ est donné par $\angle(d, \Pi) = \frac{\pi}{2} - \angle(\vec{d}, \vec{n}) = \frac{\pi}{2} - \arccos \frac{\vec{d} \bullet \vec{n}}{||\vec{d}|| \cdot ||\vec{n}||}$.
    *   Les plans bissecteurs $\beta_1$ et $\beta_2$ des plans $\Pi_1 : a_1 x + b_1 y + c_1 z = d_1$ et $\Pi_2 : a_2 x + b_2 y + c_2 z = d_2$ sont donnés par
        $$\beta_{1,2} : ||\vec{n_2}|| \cdot (a_1 x + b_1 y + c_1 z - d_1) = \pm ||\vec{n_1}|| \cdot (a_2 x + b_2 y + c_2 z - d_2).$$

#### 3.6 Produit vectoriel

Remarque : cette section n'est définie que pour $\mathbb{R}^3$ (et pas $\mathbb{R}^2$).

*   Pour $\vec{u} = \begin{pmatrix} u_1 \\ u_2 \\ u_3 \end{pmatrix}$ et $\vec{v} = \begin{pmatrix} v_1 \\ v_2 \\ v_3 \end{pmatrix}$, le produit vectoriel de $\vec{u}$ par $\vec{v}$ (dans cet ordre) est le vecteur $\vec{u} \times \vec{v} := \begin{pmatrix} u_2 v_3 - u_3 v_2 \\ -(u_1 v_3 - u_3 v_1) \\ u_1 v_2 - u_2 v_1 \end{pmatrix}$.
*   **Propriétés :**
    *   $\vec{u} \times \vec{v} = \vec{o} \Longleftrightarrow \vec{u} \parallel \vec{v}$
    *   $\vec{v} \times \vec{u} = - (\vec{u} \times \vec{v})$
    *   $\alpha (\vec{u} \times \vec{v}) = (\alpha \vec{u}) \times \vec{v} = \vec{u} \times (\alpha \vec{v})$
    *   $\vec{u} \times (\vec{v} + \vec{w}) = \vec{u} \times \vec{v} + \vec{u} \times \vec{w}$
    *   $(\vec{u} + \vec{v}) \times \vec{w} = \vec{u} \times \vec{w} + \vec{v} \times \vec{w}$
*   **Théorème :** (Interprétation géométrique du produit vectoriel)
    Le vecteur $\vec{u} \times \vec{v}$ est...
    *   perpendiculaire à $\vec{u}$ et à $\vec{v}$ (direction),
    *   de sens donné par la règle de la main droite (pouce $\leftrightarrow \vec{u}$, index $\leftrightarrow \vec{v} \leadsto$ majeur $\leftrightarrow \vec{u} \times \vec{v}$),
    *   de norme $||\vec{u} \times \vec{v}|| = ||\vec{u}|| \cdot ||\vec{v}|| \cdot \sin \angle(\vec{u}, \vec{v})$ (l'aire du parallélogramme de côtés $\vec{u}$ et $\vec{v}$).
*   La distance du point $P$ à la droite $d$ passant par $A$ et de vecteur directeur $\vec{d}$ est donnée par $\text{dist}(P, d) = \frac{||\vec{AP} \times \vec{d}||}{||\vec{d}||}$.

### 4 Systèmes d'équations linéaires

*   Un système de $m$ équations linéaires à $n$ inconnues (aussi appelé système $m \times n$) est un système d'équations de la forme
    $$
    \left\{
    \begin{matrix}
    a_{11}x_1 + a_{12}x_2 + ... + a_{1n}x_n &=& b_1 \\
    a_{21}x_1 + a_{22}x_2 + ... + a_{2n}x_n &=& b_2 \\
    \vdots &=& \vdots \\
    a_{m1}x_1 + a_{m2}x_2 + ... + a_{mn}x_n &=& b_m
    \end{matrix}
    \right.
    \longleftrightarrow
    \left(
    \begin{array}{cccc|c}
    a_{11} & a_{12} & ... & a_{1n} & b_1 \\
    a_{21} & a_{22} & ... & a_{2n} & b_2 \\
    \vdots & \vdots & \ddots & \vdots & \vdots \\
    a_{m1} & a_{m2} & ... & a_{mn} & b_m
    \end{array}
    \right)
    $$
    Les nombres $a_{ij}$ et $b_i$, $1 \leq i \leq m$, $1 \leq j \leq n$, sont les coefficients du système.
*   **Algorithme du pivot de Gauss pour la résolution d'un système $m \times n$ :**
    *   On commence par échelonner le système :
        *   On commence par l'inconnue $x_1$. Si le coefficient $a_{11} = 0$, permuter la ligne 1 avec une ligne $i$ telle que $a_{i1} \neq 0$ (le premier pivot).
        *   Ajouter successivement des multiples de la ligne du pivot aux lignes suivantes afin d'en éliminer l'inconnue $x_1$. Après cette étape, seule la ligne du premier pivot contient l'inconnue $x_1$.
        *   Considérer le sous-système composé des lignes restantes, et recommencer le processus pour l'inconnue suivante ($x_2$, ou une autre si $x_2$ a aussi été éliminée lors de l'élimination de $x_1$) : choisir un pivot non-nul, puis éliminer l'inconnue dans les lignes restantes, passer au sous-système suivant, etc.
        *   L'algorithme s'arrête lorsqu'on a parcouru toutes les inconnues. Le nouveau système ainsi obtenu est dit échelonné.
        *   Remarque : les coefficients constants $b_i$, $1 \leq i \leq n$ sont combinés entre eux selon les combinaisons de lignes pour les éliminations des inconnues, mais ils n'influencent pas le déroulement de l'algorithme.
    *   A l'issue de l'échelonnement, on peut caractériser les solutions du système :
        *   On élimine toutes les lignes de la forme $0=0$, qui sont surnuméraires.
        *   Si le système échelonné contient une ligne de la forme $0 = \star$, avec $\star \neq 0$, alors le système est impossible et son ensemble des solutions est vide.
        *   Sinon, le système admet des solutions. Le rang du système est le nombre $r$ de lignes restantes dans le système à ce moment-là. En particulier, on a $r \leq n$, car on a éliminé au moins une inconnue à chaque étape de l'échelonnement.
        *   Si $r = n$ (le rang est maximal), alors le système a une solution unique.
        *   Si $r < n$, alors le système a une infinité de solutions. Plus précisément, on peut choisir $n - r$ variables librement (à chaque fois qu'on a éliminé plus d'une variable lors d'une même étape de l'échelonnement) et exprimer les autres en fonction de ces dernières.
*   En particulier, si $m < n$ alors le système a soit une infinité de solutions, soit il n'en a pas.
*   Un système est dit homogène si $b_i = 0$ pour tout $i \in \{1, ..., m\}$. Un tel système possède toujours la solution triviale $(0, ..., 0)$. Ainsi, il a soit une unique solution, soit une infinité de solutions.