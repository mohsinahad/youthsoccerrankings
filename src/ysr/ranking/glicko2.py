from __future__ import annotations

import math
from dataclasses import dataclass

_SCALE = 173.7178
_DEFAULT_RATING = 1500.0
_DEFAULT_RD = 350.0
_DEFAULT_VOL = 0.06
_EPSILON = 1e-6


@dataclass(frozen=True)
class Glicko:
    rating: float = _DEFAULT_RATING
    rd: float = _DEFAULT_RD
    vol: float = _DEFAULT_VOL


def _g(phi: float) -> float:
    return 1.0 / math.sqrt(1.0 + 3.0 * phi**2 / math.pi**2)


def _expected(mu: float, mu_j: float, phi_j: float) -> float:
    return 1.0 / (1.0 + math.exp(-_g(phi_j) * (mu - mu_j)))


def rate(player: Glicko, results: list[tuple[Glicko, float]], *, tau: float = 0.5) -> Glicko:
    mu = (player.rating - _DEFAULT_RATING) / _SCALE
    phi = player.rd / _SCALE
    sigma = player.vol

    if not results:
        phi_star = math.sqrt(phi**2 + sigma**2)
        return Glicko(rating=player.rating, rd=_SCALE * phi_star, vol=sigma)

    opponents = [((o.rating - _DEFAULT_RATING) / _SCALE, o.rd / _SCALE, s) for o, s in results]

    v_inv = 0.0
    delta_sum = 0.0
    for mu_j, phi_j, score in opponents:
        e = _expected(mu, mu_j, phi_j)
        v_inv += _g(phi_j) ** 2 * e * (1.0 - e)
        delta_sum += _g(phi_j) * (score - e)
    v = 1.0 / v_inv
    delta = v * delta_sum

    a = math.log(sigma**2)

    def f(x: float) -> float:
        ex = math.exp(x)
        numerator = ex * (delta**2 - phi**2 - v - ex)
        denominator = 2.0 * (phi**2 + v + ex) ** 2
        return numerator / denominator - (x - a) / tau**2

    big_a = a
    if delta**2 > phi**2 + v:
        big_b = math.log(delta**2 - phi**2 - v)
    else:
        k = 1
        while f(a - k * tau) < 0.0:
            k += 1
        big_b = a - k * tau

    f_a = f(big_a)
    f_b = f(big_b)
    while abs(big_b - big_a) > _EPSILON:
        c = big_a + (big_a - big_b) * f_a / (f_b - f_a)
        f_c = f(c)
        if f_c * f_b <= 0.0:
            big_a = big_b
            f_a = f_b
        else:
            f_a = f_a / 2.0
        big_b = c
        f_b = f_c

    sigma_prime = math.exp(big_a / 2.0)
    phi_star = math.sqrt(phi**2 + sigma_prime**2)
    phi_prime = 1.0 / math.sqrt(1.0 / phi_star**2 + 1.0 / v)
    mu_prime = mu + phi_prime**2 * delta_sum

    return Glicko(
        rating=_SCALE * mu_prime + _DEFAULT_RATING,
        rd=_SCALE * phi_prime,
        vol=sigma_prime,
    )
