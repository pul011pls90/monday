"""Standalone "All Trigonometry" block & pages for Monday formulas.

Independent from the test/compilation formula cards: own data file, own
templates, nothing here reads or writes the SAT / CSCA / test formula data.
"""
import json
import re
from pathlib import Path

from flask import Blueprint, abort, current_app, jsonify, render_template, request, url_for
from flask_login import login_required

_BASE = Path(__file__).resolve().parent
_DATA_FILE = _BASE / "data" / "trigonometry_formulas.json"
_PHOTO_SUBDIR = "img/trig"

_raw_cache = None

trig_bp = Blueprint("trig_block", __name__)

_EXAMPLES = {
    "deg-rad": {
        "q": r"Convert $135^\circ$ to radians.",
        "goal": r"Multiply degrees by $\frac{\pi}{180}$ and reduce the fraction.",
        "use": r"$\text{rad} = 135 \cdot \frac{\pi}{180}$",
        "steps": [r"Divide numerator and denominator by $45$: $\frac{135}{180} = \frac{3}{4}$.", r"Multiply by $\pi$: $\frac{3\pi}{4}$."],
        "answer": r"$\frac{3\pi}{4}\text{ rad}$",
    },
    "arc-sector": {
        "q": r"A circle has radius $r = 6$ and central angle $\theta = \frac{\pi}{3}$. Find the arc length $s$ and sector area $A$.",
        "goal": r"Substitute $r$ and $\theta$ (in radians) directly into both formulas.",
        "use": r"$s = r\theta,\quad A = \frac{1}{2}r^2\theta$",
        "steps": [r"Arc length: $s = 6 \cdot \frac{\pi}{3} = 2\pi$.", r"Sector area: $A = \frac{1}{2} \cdot 6^2 \cdot \frac{\pi}{3} = 18 \cdot \frac{\pi}{3} = 6\pi$."],
        "answer": r"$s = 2\pi,\; A = 6\pi$",
    },
    "right-triangle": {
        "q": r"In a right triangle with legs $3$ and $4$ and hypotenuse $5$, angle $\theta$ is opposite the leg of length $3$. Find $\sin\theta$, $\cos\theta$, and $\tan\theta$.",
        "goal": r"Identify opposite ($3$), adjacent ($4$), and hypotenuse ($5$) relative to $\theta$.",
        "use": r"$\sin\theta = \frac{\text{opp}}{\text{hyp}},\; \cos\theta = \frac{\text{adj}}{\text{hyp}},\; \tan\theta = \frac{\text{opp}}{\text{adj}}$",
        "steps": [r"$\sin\theta = \frac{3}{5}$ and $\cos\theta = \frac{4}{5}$.", r"$\tan\theta = \frac{3}{4}$."],
        "answer": r"$\sin\theta = \frac{3}{5},\; \cos\theta = \frac{4}{5},\; \tan\theta = \frac{3}{4}$",
    },
    "reciprocal-quotient": {
        "q": r"Given $\cos\theta = \frac{5}{13}$, find $\sec\theta$.",
        "goal": r"Secant is the reciprocal of cosine.",
        "use": r"$\sec\theta = \frac{1}{\cos\theta}$",
        "steps": [r"Flip the fraction: $\sec\theta = \frac{1}{5/13} = \frac{13}{5}$."],
        "answer": r"$\frac{13}{5}$",
    },
    "special-values": {
        "q": r"Evaluate $\sin 60^\circ \cdot \cos 30^\circ$.",
        "goal": r"Substitute exact values from the $30^\circ\text{–}60^\circ\text{–}90^\circ$ triangle.",
        "use": r"$\sin 60^\circ = \frac{\sqrt{3}}{2},\quad \cos 30^\circ = \frac{\sqrt{3}}{2}$",
        "steps": [r"Multiply: $\frac{\sqrt{3}}{2} \cdot \frac{\sqrt{3}}{2} = \frac{3}{4}$."],
        "answer": r"$\frac{3}{4}$",
    },
    "unit-circle": {
        "q": r"Find the exact values of $\sin\frac{5\pi}{6}$ and $\cos\frac{5\pi}{6}$.",
        "goal": r"Find the quadrant of $\frac{5\pi}{6}$ and its reference angle.",
        "use": r"$\frac{5\pi}{6} = \pi - \frac{\pi}{6}$ (Quadrant II: $\sin > 0$, $\cos < 0$)",
        "steps": [r"Reference angle is $\frac{\pi}{6}$, where $\sin\frac{\pi}{6}=\frac{1}{2}$ and $\cos\frac{\pi}{6}=\frac{\sqrt{3}}{2}$.", r"Apply Quadrant II signs: $\sin = +\frac{1}{2}$, $\cos = -\frac{\sqrt{3}}{2}$."],
        "answer": r"$\sin\frac{5\pi}{6} = \frac{1}{2},\; \cos\frac{5\pi}{6} = -\frac{\sqrt{3}}{2}$",
    },
    "periodicity": {
        "q": r"Evaluate $\sin 405^\circ$.",
        "goal": r"Subtract full $360^\circ$ rotations to bring the angle inside $[0^\circ, 360^\circ)$.",
        "use": r"$\sin(\theta + 360^\circ k) = \sin\theta$",
        "steps": [r"Write $405^\circ = 360^\circ + 45^\circ$.", r"Thus $\sin 405^\circ = \sin 45^\circ = \frac{\sqrt{2}}{2}$."],
        "answer": r"$\frac{\sqrt{2}}{2}$",
    },
    "even-odd": {
        "q": r"Evaluate $\cos\!\left(-\frac{\pi}{3}\right)$ and $\tan\!\left(-\frac{\pi}{4}\right)$.",
        "goal": r"Use even symmetry for cosine and odd symmetry for tangent.",
        "use": r"$\cos(-\theta) = \cos\theta,\quad \tan(-\theta) = -\tan\theta$",
        "steps": [r"$\cos(-\frac{\pi}{3}) = \cos\frac{\pi}{3} = \frac{1}{2}$.", r"$\tan(-\frac{\pi}{4}) = -\tan\frac{\pi}{4} = -1$."],
        "answer": r"$\frac{1}{2}$ and $-1$",
    },
    "pythagorean": {
        "q": r"If $\sin\theta = \frac{3}{5}$ and $\theta$ is in Quadrant II, find $\cos\theta$.",
        "goal": r"Use the Pythagorean identity and pick the sign for Quadrant II ($\cos < 0$).",
        "use": r"$\sin^2\theta + \cos^2\theta = 1$",
        "steps": [r"$\cos^2\theta = 1 - \left(\frac{3}{5}\right)^2 = 1 - \frac{9}{25} = \frac{16}{25}$.", r"Take the negative root in Quadrant II: $\cos\theta = -\frac{4}{5}$."],
        "answer": r"$-\frac{4}{5}$",
    },
    "cofunction": {
        "q": r"Express $\sin 70^\circ$ in terms of cosine.",
        "goal": r"Replace the angle with its complement $90^\circ - \theta$.",
        "use": r"$\sin(90^\circ - \theta) = \cos\theta$",
        "steps": [r"$70^\circ = 90^\circ - 20^\circ$, so $\sin 70^\circ = \cos 20^\circ$."],
        "answer": r"$\cos 20^\circ$",
    },
    "reduction": {
        "q": r"Evaluate $\cos 120^\circ$.",
        "goal": r"Rewrite $120^\circ$ as $180^\circ - 60^\circ$ (Quadrant II).",
        "use": r"$\cos(180^\circ - \theta) = -\cos\theta$",
        "steps": [r"$\cos 120^\circ = \cos(180^\circ - 60^\circ) = -\cos 60^\circ = -\frac{1}{2}$."],
        "answer": r"$-\frac{1}{2}$",
    },
    "sum-difference": {
        "q": r"Find the exact value of $\sin 75^\circ$.",
        "goal": r"Split $75^\circ$ into two special angles: $45^\circ + 30^\circ$.",
        "use": r"$\sin(A + B) = \sin A\cos B + \cos A\sin B$",
        "steps": [r"$\sin(45^\circ + 30^\circ) = \sin 45^\circ\cos 30^\circ + \cos 45^\circ\sin 30^\circ$.", r"$= \frac{\sqrt{2}}{2}\cdot\frac{\sqrt{3}}{2} + \frac{\sqrt{2}}{2}\cdot\frac{1}{2} = \frac{\sqrt{6}+\sqrt{2}}{4}$."],
        "answer": r"$\frac{\sqrt{6}+\sqrt{2}}{4}$",
    },
    "auxiliary-angle": {
        "q": r"Write $\sin x + \cos x$ as a single sine and find its maximum value.",
        "goal": r"Compute $R = \sqrt{a^2 + b^2}$ with $a = 1$, $b = 1$.",
        "use": r"$a\sin x + b\cos x = R\sin(x + \varphi)$",
        "steps": [r"$R = \sqrt{1^2 + 1^2} = \sqrt{2}$, and $\cos\varphi = \sin\varphi = \frac{1}{\sqrt{2}} \Rightarrow \varphi = \frac{\pi}{4}$.", r"So $\sin x + \cos x = \sqrt{2}\sin\!\left(x + \frac{\pi}{4}\right)$, whose maximum is $R = \sqrt{2}$."],
        "answer": r"$\sqrt{2}\sin\!\left(x + \frac{\pi}{4}\right)$, maximum $\sqrt{2}$",
    },
    "double-angle": {
        "q": r"Given $\sin\theta = \frac{3}{5}$ and $\cos\theta = \frac{4}{5}$, find $\sin 2\theta$ and $\cos 2\theta$.",
        "goal": r"Plug $\sin\theta$ and $\cos\theta$ into the double-angle formulas.",
        "use": r"$\sin 2\theta = 2\sin\theta\cos\theta,\quad \cos 2\theta = 1 - 2\sin^2\theta$",
        "steps": [r"$\sin 2\theta = 2 \cdot \frac{3}{5} \cdot \frac{4}{5} = \frac{24}{25}$.", r"$\cos 2\theta = 1 - 2\left(\frac{3}{5}\right)^2 = 1 - \frac{18}{25} = \frac{7}{25}$."],
        "answer": r"$\sin 2\theta = \frac{24}{25},\; \cos 2\theta = \frac{7}{25}$",
    },
    "half-angle": {
        "q": r"Find the exact value of $\cos 15^\circ$.",
        "goal": r"Write $15^\circ = \frac{30^\circ}{2}$ (Quadrant I, positive root).",
        "use": r"$\cos\frac{\theta}{2} = +\sqrt{\frac{1 + \cos\theta}{2}}$",
        "steps": [r"$\cos 15^\circ = \sqrt{\frac{1 + \cos 30^\circ}{2}} = \sqrt{\frac{1 + \sqrt{3}/2}{2}} = \sqrt{\frac{2+\sqrt{3}}{4}}$.", r"Simplify radical: $\frac{\sqrt{6}+\sqrt{2}}{4}$."],
        "answer": r"$\frac{\sqrt{6}+\sqrt{2}}{4}$",
    },
    "power-reducing": {
        "q": r"Evaluate $\cos^2\frac{\pi}{8}$.",
        "goal": r"Replace $\cos^2\theta$ with a first-power expression in $\cos 2\theta$.",
        "use": r"$\cos^2\theta = \frac{1 + \cos 2\theta}{2}$",
        "steps": [r"With $\theta = \frac{\pi}{8}$, $2\theta = \frac{\pi}{4}$: $\frac{1 + \cos(\pi/4)}{2} = \frac{1 + \sqrt{2}/2}{2} = \frac{2+\sqrt{2}}{4}$."],
        "answer": r"$\frac{2+\sqrt{2}}{4}$",
    },
    "triple-angle": {
        "q": r"If $\sin\theta = \frac{1}{2}$, find $\sin 3\theta$.",
        "goal": r"Substitute $\sin\theta = \frac{1}{2}$ directly into the triple-angle formula.",
        "use": r"$\sin 3\theta = 3\sin\theta - 4\sin^3\theta$",
        "steps": [r"$\sin 3\theta = 3\left(\frac{1}{2}\right) - 4\left(\frac{1}{2}\right)^3 = \frac{3}{2} - \frac{4}{8} = 1$."],
        "answer": r"$1$",
    },
    "product-to-sum": {
        "q": r"Evaluate $\sin 75^\circ \cos 15^\circ$.",
        "goal": r"Convert the product into a sum of sines of $75^\circ \pm 15^\circ$.",
        "use": r"$\sin A\cos B = \frac{1}{2}[\sin(A+B) + \sin(A-B)]$",
        "steps": [r"$\frac{1}{2}[\sin 90^\circ + \sin 60^\circ] = \frac{1}{2}\left(1 + \frac{\sqrt{3}}{2}\right) = \frac{2+\sqrt{3}}{4}$."],
        "answer": r"$\frac{2+\sqrt{3}}{4}$",
    },
    "sum-to-product": {
        "q": r"Evaluate $\sin 75^\circ + \sin 15^\circ$.",
        "goal": r"Use half-sum $\frac{75^\circ+15^\circ}{2}=45^\circ$ and half-difference $\frac{75^\circ-15^\circ}{2}=30^\circ$.",
        "use": r"$\sin A + \sin B = 2\sin\frac{A+B}{2}\cos\frac{A-B}{2}$",
        "steps": [r"$2\sin 45^\circ \cos 30^\circ = 2 \cdot \frac{\sqrt{2}}{2} \cdot \frac{\sqrt{3}}{2} = \frac{\sqrt{6}}{2}$."],
        "answer": r"$\frac{\sqrt{6}}{2}$",
    },
    "graph-transformations": {
        "q": r"Find the amplitude, period, phase shift, midline, and range of $y = 3\sin(2x - \pi) + 1$.",
        "goal": r"Factor out $B = 2$ inside the sine to read $C$ directly.",
        "use": r"$y = A\sin(B(x - C)) + D \;\Rightarrow\; y = 3\sin\!\left(2\left(x - \frac{\pi}{2}\right)\right) + 1$",
        "steps": [r"Amplitude $|A| = 3$, period $\frac{2\pi}{2} = \pi$.", r"Phase shift $C = \frac{\pi}{2}$ right, midline $y = 1$, range $[1 - 3, 1 + 3] = [-2, 4]$."],
        "answer": r"Amplitude $3$, period $\pi$, shift $\frac{\pi}{2}$ right, midline $y = 1$, range $[-2, 4]$",
    },
    "inverse-trig": {
        "q": r"Evaluate $\arcsin\!\left(-\frac{1}{2}\right)$ and $\arccos\!\left(-\frac{1}{2}\right)$.",
        "goal": r"Use odd/reflection identities within the restricted ranges.",
        "use": r"$\arcsin(-x) = -\arcsin x,\quad \arccos(-x) = \pi - \arccos x$",
        "steps": [r"$\arcsin(-\frac{1}{2}) = -\arcsin\frac{1}{2} = -\frac{\pi}{6}$.", r"$\arccos(-\frac{1}{2}) = \pi - \arccos\frac{1}{2} = \pi - \frac{\pi}{3} = \frac{2\pi}{3}$."],
        "answer": r"$-\frac{\pi}{6}$ and $\frac{2\pi}{3}$",
    },
    "trig-equations": {
        "q": r"Solve the equation $2\sin x = 1$ for all real $x$.",
        "goal": r"Isolate $\sin x$ and apply the general sine solution.",
        "use": r"$\sin x = a \;\Rightarrow\; x = (-1)^n \arcsin a + \pi n \quad (n \in \mathbb{Z})$",
        "steps": [r"$\sin x = \frac{1}{2}$, and $\arcsin\frac{1}{2} = \frac{\pi}{6}$.", r"Write the general form: $x = (-1)^n\frac{\pi}{6} + \pi n$ (or $\frac{\pi}{6}+2\pi n$, $\frac{5\pi}{6}+2\pi n$)."],
        "answer": r"$x = (-1)^n\frac{\pi}{6} + \pi n,\; n \in \mathbb{Z}$",
    },
    "sine-rule": {
        "q": r"In $\triangle ABC$, $A = 30^\circ$, $a = 5$, and $B = 45^\circ$. Find side $b$.",
        "goal": r"Relate sides $a, b$ with their opposite angles $A, B$.",
        "use": r"$\frac{a}{\sin A} = \frac{b}{\sin B}$",
        "steps": [r"$b = \frac{a\sin B}{\sin A} = \frac{5 \cdot \sin 45^\circ}{\sin 30^\circ} = \frac{5 \cdot \sqrt{2}/2}{1/2} = 5\sqrt{2}$."],
        "answer": r"$5\sqrt{2}$",
    },
    "cosine-rule": {
        "q": r"In $\triangle ABC$, $a = 3$, $b = 4$, and included angle $C = 60^\circ$. Find side $c$.",
        "goal": r"Apply the Law of Cosines with the two given sides and included angle.",
        "use": r"$c^2 = a^2 + b^2 - 2ab\cos C$",
        "steps": [r"$c^2 = 3^2 + 4^2 - 2(3)(4)\cos 60^\circ = 9 + 16 - 24\cdot\frac{1}{2} = 13$.", r"Take the positive square root: $c = \sqrt{13}$."],
        "answer": r"$\sqrt{13}$",
    },
    "triangle-area": {
        "q": r"Find the area of a triangle with sides $a = 6$, $b = 8$, and included angle $C = 30^\circ$.",
        "goal": r"Multiply half the product of the two sides by $\sin C$.",
        "use": r"$\text{Area} = \frac{1}{2}ab\sin C$",
        "steps": [r"$\text{Area} = \frac{1}{2} \cdot 6 \cdot 8 \cdot \sin 30^\circ = 24 \cdot \frac{1}{2} = 12$."],
        "answer": r"$12$",
    },
    "trig-limits": {
        "task": r"Вычислите $\lim\limits_{x\to0}\frac{\sin5x}{2x}$.",
        "goal": r"Найти предел при $x\to0$.",
        "rule": {
            "id": "first_remarkable_limit",
            "title": "Первый замечательный предел",
            "latex": r"\lim_{u\to0}\frac{\sin u}{u}=1",
            "card_id": "trig-limits",
        },
        "steps": [
            {
                "action": "Определить тип предела",
                "math": r"\frac{\sin5x}{2x}\;\xrightarrow{x\to0}\;\frac{0}{0}",
                "why": r"Подстановка $x=0$ даёт $\frac00$, значит выражение нужно преобразовать.",
                "visual_focus": "hole",
            },
            {
                "action": r"Привести знаменатель к виду $5x$",
                "math": r"\frac{\sin5x}{2x}=\htmlClass{hl}{\frac52}\cdot\frac{\sin5x}{\htmlClass{hl}{5x}}",
                "why": "Умножаем и делим на 5. Значение выражения не меняется.",
                "visual_focus": "same_curve",
            },
            {
                "action": r"Ввести замену $u=5x$",
                "math": r"\frac52\cdot\lim_{u\to0}\frac{\sin u}{u}",
                "why": r"Если $x\to0$, то и $u=5x\to0$.",
                "visual_focus": "none",
            },
            {
                "action": "Применить правило",
                "math": r"\frac52\cdot\htmlClass{hl}{1}=\frac52",
                "why": r"По первому замечательному пределу $\lim_{u\to0}\frac{\sin u}{u}=1$.",
                "rule_id": "first_remarkable_limit",
                "visual_focus": "point",
            },
        ],
        "check": {
            "type": "table",
            "label": r"Проверка: значения при $x\to0$",
            "rows": [["0{,}1", "2{,}3971"], ["0{,}01", "2{,}4990"], ["0{,}001", "2{,}5000"]],
            "conclusion": r"Значения приближаются к $2{,}5=\frac52$.",
        },
        "pitfall": r"Нельзя «сократить» $x$ и записать $\frac{\sin5}{2}$. Синус берётся от всего произведения $5x$.",
        "answer": {"exact": r"\frac52", "approx": "2{,}5"},
        "visual": {
            "type": "limit_graph",
            "function": "sin(5*x)/(2*x)",
            "x_range": [-1.5, 1.5],
            "hole": {"x": 0, "y": 2.5, "label": "(0; 5/2)"},
        },
    },
    "trig-derivatives": {
        "q": r"Differentiate $f(x) = x\sin x$.",
        "goal": r"Because $x$ and $\sin x$ are multiplied together, we cannot differentiate them separately — we use the product rule $(uv)' = u'v + uv'$.",
        "use": r"$(x)' = 1,\quad (\sin x)' = \cos x$",
        "steps": [
            r"Split the product into two parts: let $u = x$ and $v = \sin x$.",
            r"Find the derivative of each part separately: $u' = (x)' = 1$ and $v' = (\sin x)' = \cos x$.",
            r"Plug into the product rule $u'v + uv'$: differentiate the first factor and keep the second, then keep the first and differentiate the second: $f'(x) = 1\cdot\sin x + x\cdot\cos x$.",
        ],
        "answer": r"$\sin x + x\cos x$",
    },
    "inverse-trig-derivatives": {
        "q": r"Differentiate $f(x) = \arctan(2x)$.",
        "goal": r"Because the inside of $\arctan$ is $2x$ (not just $x$), we combine the $\arctan$ rule with the chain rule.",
        "use": r"$(\arctan u)' = \frac{u'}{1 + u^2}$",
        "steps": [
            r"Identify the inner function $u = 2x$, whose derivative is $u' = 2$.",
            r"Square the inner function for the denominator: $1 + u^2 = 1 + (2x)^2 = 1 + 4x^2$.",
            r"Place $u' = 2$ in the numerator and $1 + 4x^2$ in the denominator: $f'(x) = \frac{2}{1 + 4x^2}$.",
        ],
        "answer": r"$\frac{2}{1 + 4x^2}$",
    },
    "trig-integrals-basic": {
        "q": r"Evaluate $\int (3\cos x - \sec^2 x)\,dx$.",
        "goal": r"Split the integral into two separate terms, pull out the constant $3$, and use basic antiderivatives.",
        "use": r"$\int \cos x\,dx = \sin x + C,\quad \int \sec^2 x\,dx = \tan x + C$",
        "steps": [
            r"Separate into two simpler integrals: $3\int\cos x\,dx - \int\sec^2 x\,dx$.",
            r"Integrate each part: the antiderivative of $\cos x$ is $\sin x$, and the antiderivative of $\sec^2 x$ is $\tan x$.",
            r"Combine the results and add the integration constant $+ C$: $3\sin x - \tan x + C$.",
        ],
        "answer": r"$3\sin x - \tan x + C$",
    },
    "trig-integrals-log": {
        "q": r"Evaluate the definite integral $\int_0^{\pi/4} \tan x\,dx$.",
        "goal": r"Find the antiderivative of $\tan x$ first, then plug in the upper limit $\frac{\pi}{4}$ and subtract the lower limit $0$.",
        "use": r"$\int \tan x\,dx = -\ln|\cos x| + C$",
        "steps": [
            r"Use the antiderivative $[-\ln|\cos x|]_0^{\pi/4}$ and evaluate at both endpoints: $-\ln\left(\cos\frac{\pi}{4}\right) - \bigl(-\ln(\cos 0)\bigr)$.",
            r"Substitute the known cosine values $\cos\frac{\pi}{4} = \frac{\sqrt{2}}{2}$ and $\cos 0 = 1$ (since $\ln 1 = 0$, the second term disappears): $-\ln\frac{\sqrt{2}}{2}$.",
            r"Rewrite $\frac{\sqrt{2}}{2} = 2^{-1/2}$ so the minus signs cancel: $-\ln(2^{-1/2}) = \frac{1}{2}\ln 2$.",
        ],
        "answer": r"$\frac{1}{2}\ln 2$",
    },
    "inverse-trig-integrals": {
        "q": r"Evaluate $\int \frac{dx}{9 + x^2}$.",
        "goal": r"Match the denominator $9 + x^2$ to the standard $a^2 + x^2$ form for the $\arctan$ integral.",
        "use": r"$\int \frac{dx}{a^2 + x^2} = \frac{1}{a}\arctan\frac{x}{a} + C$",
        "steps": [
            r"Rewrite $9$ as $3^2$, so we can clearly see that $a^2 = 9$ and $a = 3$.",
            r"Plug $a = 3$ into the formula $\frac{1}{a}\arctan\frac{x}{a} + C$ to get $\frac{1}{3}\arctan\frac{x}{3} + C$.",
        ],
        "answer": r"$\frac{1}{3}\arctan\frac{x}{3} + C$",
    },
    "trig-integrals-powers": {
        "q": r"Evaluate $\int_0^{\pi} \cos^2 x\,dx$.",
        "goal": r"Use the antiderivative of $\cos^2 x$ (from the power-reducing identity), then evaluate from $0$ to $\pi$.",
        "use": r"$\int \cos^2 x\,dx = \frac{x}{2} + \frac{\sin 2x}{4} + C$",
        "steps": [
            r"Plug in the upper limit $x = \pi$: $\frac{\pi}{2} + \frac{\sin(2\pi)}{4} = \frac{\pi}{2} + 0 = \frac{\pi}{2}$.",
            r"Plug in the lower limit $x = 0$: $\frac{0}{2} + \frac{\sin(0)}{4} = 0$.",
            r"Subtract lower from upper: $\frac{\pi}{2} - 0 = \frac{\pi}{2}$.",
        ],
        "answer": r"$\frac{\pi}{2}$",
    },
}


def _load_raw():
    global _raw_cache
    if _raw_cache is None:
        _raw_cache = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    return _raw_cache


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _photo_url(app_static_folder, card_id):
    for ext in ("svg", "png"):
        path = Path(app_static_folder) / _PHOTO_SUBDIR / f"{card_id}.{ext}"
        if path.exists():
            return url_for("static", filename=f"{_PHOTO_SUBDIR}/{card_id}.{ext}")
    return None


def _math_tex(s):
    """Convert Unicode trig notation to clean KaTeX LaTeX."""
    t = str(s or "")
    for a, b in (
        ("½", r"\frac{1}{2}"),
        ("²", "^2"),
        ("³", "^3"),
        ("ⁿ", "^n"),
        ("′", "'"),
        ("−", "-"),
        ("·", r"\cdot "),
        ("×", r"\times "),
        ("±", r"\pm "),
        ("∓", r"\mp "),
        ("≤", r"\le "),
        ("≥", r"\ge "),
        ("≠", r"\neq "),
        ("⇒", r"\Rightarrow "),
        ("→", r"\to "),
        ("ℝ", r"\mathbb{R}"),
        ("∞", r"\infty "),
        ("π", r"\pi "),
        ("θ", r"\theta "),
        ("φ", r"\varphi "),
        ("°", r"^\circ "),
        ("∫", r"\int "),
        ("lim(x->0)", r"\lim_{x\to 0}"),
    ):
        t = t.replace(a, b)
    t = t.replace("lim(x\\to 0)", r"\lim_{x\to 0}")
    t = re.sub(r"\b(arcsin|arccos|arctan|arccot|sin|cos|tan|cot|sec|csc|ln)\b", r"\\\1 ", t)
    for phrase in (
        "Point on unit circle", "Quadrant I", "Quadrant II", "Quadrant III", "Quadrant IV",
        "all positive", "sin positive", "tan positive", "cos positive",
        "k is an integer", "n is an integer", "for sin and cos", "R is the circumradius",
        "Phase shift", "Amplitude", "Period", "Midline", "tangent", "undefined",
        "opposite", "adjacent", "hypotenuse", "Area",
    ):
        t = t.replace(phrase, rf"\text{{{phrase}}}")
    t = re.sub(r"√\(([^()]+)\)", r"\\sqrt{\1}", t)
    t = re.sub(r"√([A-Za-z0-9]+)", r"\\sqrt{\1}", t)
    return t.strip()


def validate_structured_example(ex):
    """Ensure every new-format example (dict steps) has task, goal, steps(action, math, why), and answer."""
    steps = ex.get("steps")
    if not (isinstance(steps, list) and steps and isinstance(steps[0], dict)):
        return
    for key in ("task", "goal", "answer"):
        if not ex.get(key):
            raise ValueError(f"Structured example missing '{key}'")
    for idx, st in enumerate(steps):
        for sk in ("action", "math", "why"):
            if not st.get(sk):
                raise ValueError(f"Structured example step {idx} missing '{sk}'")


def build_trig_block(static_folder):
    """Return {'levels': [...], 'groups': [{'level': {...}, 'branches': [{'id', 'name', 'cards'}]}]}."""
    raw = _load_raw()
    branch_order = raw["branches"]
    groups = []
    for level in raw["levels"]:
        level_cards = [c for c in raw["cards"] if c["level"] == level["id"]]
        branches = []
        for name in branch_order:
            cards = []
            for c in level_cards:
                if c["branch"] == name:
                    card = dict(c)
                    card["photo_url"] = _photo_url(static_folder, c["id"])
                    card["ex_photo_url"] = _photo_url(static_folder, f"ex/{c['id']}")
                    card["tex_lines"] = [_math_tex(f) for f in c["formulas"]]
                    card["ex_view"] = _EXAMPLES.get(c["id"]) or {
                        "q": c["example"]["problem"],
                        "goal": c["description"],
                        "use": f"${card['tex_lines'][0]}$" if card["tex_lines"] else "",
                        "steps": [c["example"]["solution"]],
                        "answer": c["example"]["solution"],
                    }
                    ex_svg_path = Path(static_folder) / "img" / "examples" / f"{c['id'].replace('-', '_')}_0.svg"
                    if isinstance(card["ex_view"], dict) and isinstance(card["ex_view"].get("visual"), dict) and ex_svg_path.exists():
                        card["ex_view"] = dict(card["ex_view"])
                        card["ex_view"]["visual"] = dict(card["ex_view"]["visual"], svg_html=ex_svg_path.read_text(encoding="utf-8"), caption=card["ex_view"]["visual"].get("caption") or "График y = sin(5x)/(2x) с выколотой точкой (0; 5/2).")
                    cards.append(card)
            if cards:
                branches.append({"id": _slug(name), "name": name, "cards": cards})
        groups.append({
            "level": level,
            "branches": branches,
            "cards_count": sum(len(b["cards"]) for b in branches),
        })
    return {
        "levels": raw["levels"],
        "groups": groups,
        "levels_count": len(raw["levels"]),
        "branches_count": len(raw["branches"]),
        "cards_count": len(raw["cards"]),
    }


@trig_bp.route("/formulas/trigonometry")
@login_required
def trig_sections():
    """Subtopic cards for All Trigonometry (Basic, Intermediate, Calculus 1)."""
    tb = build_trig_block(current_app.static_folder)
    return render_template("student/trig_sections.html", tb=tb)


@trig_bp.route("/formulas/trigonometry/<level_id>")
@login_required
def trig_level(level_id):
    """Topic formulas, diagram, and examples for one trigonometry section."""
    tb = build_trig_block(current_app.static_folder)
    group = next((g for g in tb["groups"] if g["level"]["id"] == level_id), None) or abort(404)
    topic_id = request.args.get("topic")
    branch = next((b for b in group["branches"] if b["id"] == topic_id), group["branches"][0])
    return render_template("student/trig_topic.html", group=group, branch=branch)


@trig_bp.route("/api/trigonometry-formulas")
def trig_api():
    """JSON endpoint."""
    return jsonify(_load_raw())


@trig_bp.route("/dev/visuals")
def dev_visuals():
    """QA contact sheet for all generated example and formula SVGs."""
    ex_dir = Path(current_app.static_folder) / "img" / "examples"
    fm_dir = Path(current_app.static_folder) / "img" / "formulas"
    examples = [{"id": p.stem, "svg": p.read_text(encoding="utf-8")} for p in sorted(ex_dir.glob("*.svg"))] if ex_dir.exists() else []
    formulas = [{"id": p.stem, "svg": p.read_text(encoding="utf-8")} for p in sorted(fm_dir.glob("*.svg"))] if fm_dir.exists() else []
    return render_template("dev/visuals.html", examples=examples, formulas=formulas)


def init_trig_block(app):
    """Register the blueprint and the `trig_block()` template helper."""
    app.register_blueprint(trig_bp)

    @app.context_processor
    def _inject():
        return {"trig_block": lambda: build_trig_block(app.static_folder)}
