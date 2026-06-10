#include <iostream>

__attribute__((optnone))
int main() {
  int v = 0;
  int sum = 0;
  for (int i = 0; i < 100; ++i) {
    if (i % 2 == 0) {
      v = 1;
    } else {
      v = 2;
    }

    if (v == 1) { // Implicitly depends on i % 2 == 0
      sum += 1;
    } else {
      sum += 2;
    }
  }
  std::cout << sum << "\n";
  return sum % 2;
}
