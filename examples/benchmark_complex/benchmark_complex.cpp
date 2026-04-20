/**
 * benchmark_complex — non-trivial control flow for the end-to-end pipeline:
 * PGO → CFGDumper (llc) → binary with .llvm_bb_addr_map → DynamoRIO InstrTracer → compress.
 * Logic is intentionally branchy (loops, early exits) to stress trace analysis.
 */
#include <algorithm>
#include <cstdint>
#include <functional>
#include <iostream>
#include <random>
#include <string>
#include <vector>

namespace {

std::uint32_t rotl(std::uint32_t x, unsigned r) {
    return (x << r) | (x >> (32U - r));
}

int dispatch_hub(int seed, int bias) {
    const int x = (seed ^ bias) & 0x7f;
    if (x < 40) {
        int a = 0;
        for (int i = 0; i < 8; ++i) {
            a += (x + i) * (i % 3 + 1);
            if (a > 200) {
                a -= 50;
                break;
            }
        }
        return a + (x % 7);
    }
    if (x < 70) {
        int b = x;
        for (int j = 0; j < 5; ++j) {
            b = (b * 3 + 11) % 251;
            if ((b & 3) == 0) {
                b ^= rotl(static_cast<std::uint32_t>(seed), j);
            }
        }
        return b;
    }
    if (x < 100) {
        int c = 1;
        for (int k = 1; k <= 12; ++k) {
            c += (x ^ k) % (k + 3);
            if (c > 400) {
                c /= 2;
                break;
            }
        }
        return c;
    }
    int h = x;
    for (int r = 0; r < 24; ++r) {
        if ((h & 1) == 0) {
            h = h / 2 + r;
        } else {
            h = 3 * h + 1;
        }
        if (h > 5000) {
            h %= 997;
            break;
        }
    }
    return h;
}

int merge_before_return(int a, int b, int c) {
    const int t = (a + 2 * b + 3 * c) % 1021;
    if (t < 300) {
        return t ^ 0x5a5a;
    }
    if (t < 700) {
        return (t * 7 + 13) % 4099;
    }
    return static_cast<int>(rotl(static_cast<std::uint32_t>(t), 11));
}

}  // namespace

int main(int argc, char** argv) {
    int seed = 0x3c6ef35f;
    if (argc > 1) {
        seed ^= static_cast<int>(std::hash<std::string>{}(argv[1]) & 0x7fffffff);
    }

    std::vector<int> buf;
    buf.reserve(64);
    for (int i = 0; i < 48; ++i) {
        buf.push_back((seed + i * 17) % 199);
    }

    int acc = 0;
    for (std::size_t i = 0; i < buf.size(); ++i) {
        const int bias = static_cast<int>(i) ^ (seed & 0xff);
        acc += dispatch_hub(buf[i], bias);
        if ((acc & 0x3ff) == 0x200) {
            acc = merge_before_return(static_cast<int>(i), buf[i], acc);
        }
    }

    std::mt19937 rng(static_cast<std::mt19937::result_type>(seed ^ acc));
    std::uniform_int_distribution<int> dist(-50, 50);
    for (int round = 0; round < 6; ++round) {
        int v = dist(rng);
        acc += dispatch_hub(v, round * 31 + 3);
        if (acc < -10000) {
            acc = -acc % 7777;
            break;
        }
    }

    const int out = merge_before_return(acc, seed % 91, argc);
    std::cout << out << '\n';
    return (out == 0) ? 0 : (out & 1);
}
