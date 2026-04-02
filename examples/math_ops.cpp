#include <iostream>
#include <cstdlib>
#include <cmath>

double computeMath(double x, int iters) {
    double res = x;
    for (int i = 0; i < iters; ++i) {
        if (i % 2 == 0) {
            res = std::sin(res) * 2.0;
        } else if (i % 3 == 0) {
            res = std::tan(res);
        } else {
            res = std::cos(res) / 1.5;
        }
    }
    return res;
}

int main(int argc, char** argv) {
    int iters = 1000;
    if (argc > 1) {
        iters = std::atoi(argv[1]);
    }
    
    double val = computeMath(3.1415, iters);
    return 0;
}