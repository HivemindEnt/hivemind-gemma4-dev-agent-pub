"""Sample sizes for the paper's noise section: tasks needed to detect a resolve-rate difference.

Two designs, alpha 0.05 two-sided, power 0.80 (normal approximations, so treat as order-of-magnitude):
  * unpaired: two independent runs on different task draws (two-proportion z test), tasks per arm;
  * paired: both configurations on the same tasks (McNemar), with a discordant-pair rate p_disc >= |delta|.
"""
import math
import sys

Z_A, Z_B = 1.959964, 0.841621


def unpaired_n(p1, p2):
    return math.ceil((Z_A + Z_B) ** 2 * (p1 * (1 - p1) + p2 * (1 - p2)) / (p1 - p2) ** 2)


def paired_n(delta, p_disc):
    if p_disc < abs(delta):
        raise ValueError('discordant rate must be at least |delta|')
    return math.ceil((Z_A * math.sqrt(p_disc) + Z_B * math.sqrt(p_disc - delta ** 2)) ** 2 / delta ** 2)


def main():
    base = 16 / 90   # A0 pooled over three repeats
    for d in (0.05, 0.10):
        print(f"unpaired: {base:.3f} vs {base + d:.3f}: {unpaired_n(base, base + d)} tasks per arm")
    # observed discordance: A0 vs itself 1-3 of 30 (mean 2/30); arm vs A0 about 2/30 to 4/30
    for d, pd in ((0.05, 0.10), (0.05, 0.15), (0.10, 0.15), (0.10, 0.20)):
        print(f"paired: delta {d:.2f}, discordant {pd:.2f}: {paired_n(d, pd)} tasks")
    return 0


if __name__ == '__main__':
    sys.exit(main())
