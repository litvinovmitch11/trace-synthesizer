#include <iostream>
#include <vector>

int main() {
  const int n = 256;
  std::vector<double> a(n * n, 0.0);
  std::vector<double> b(n * n, 0.0);
  std::vector<double> c(n * n, 0.0);
  for (int i = 0; i < n * n; ++i) {
    a[i] = (i % 97) * 0.1;
    b[i] = (i % 71) * 0.2;
  }
  for (int t = 0; t < 20; ++t) {
    for (int i = 0; i < n; ++i) {
      for (int j = 0; j < n; ++j) {
        double s = 0.0;
        for (int k = 0; k < n; ++k) {
          s += a[i * n + k] * b[k * n + j];
        }
        c[i * n + j] = s;
      }
    }
    a.swap(c);
  }
  std::cout << static_cast<long long>(a[(n / 2) * n + (n / 2)]) << "\n";
  return 0;
}
