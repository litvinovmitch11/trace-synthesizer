#include <cstdint>
#include <iostream>
#include <vector>

static inline int mix_step(int x, int i) {
  if ((x ^ i) & 1) {
    x = (x * 3 + i) ^ (x >> 1);
  } else {
    x = (x + i * 7) ^ (x << 1);
  }
  if (x % 5 == 0) {
    x += i * 13;
  } else if (x % 7 == 0) {
    x -= i * 3;
  } else {
    x ^= (i << 2);
  }
  return x;
}

int main() {
  std::vector<int> v(8000, 0);
  for (int i = 0; i < static_cast<int>(v.size()); ++i) {
    v[i] = (i * 17) ^ (i >> 2);
  }
  int acc = 0;
  for (int r = 0; r < 300; ++r) {
    for (int i = 0; i < static_cast<int>(v.size()); ++i) {
      acc ^= mix_step(v[i] + acc, i);
    }
  }
  std::cout << (acc & 0xFFFF) << "\n";
  return 0;
}
