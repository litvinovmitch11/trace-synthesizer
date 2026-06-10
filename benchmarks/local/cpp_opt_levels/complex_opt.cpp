#include <vector>

__attribute__((noinline))
int complex_algorithm(int n) {
    int data[100];
    if (n > 100) n = 100;
    
    for (int i = 0; i < n; ++i) {
        data[i] = i * 3 - 5;
    }

    int result = 0;
    int state = 0;
    
    // State machine loop: dynamic context dependency that PGO cannot capture
    for (int i = 0; i < n; ++i) {
        if (state == 0) {
            for (int j = 0; j < 3; ++j) {
                result += data[i] * j;
            }
            state = 1;
        } else if (state == 1) {
            if (data[i] > 10) {
                result -= data[i];
            } else {
                result += 1;
            }
            state = 2;
        } else {
            result += data[i] % 2;
            state = 0;
        }
    }
    
    // Bubble sort a small window to introduce another loop type
    int limit = n > 20 ? 20 : n;
    for (int i = 0; i < limit; ++i) {
        for (int j = 0; j < limit - i - 1; ++j) {
            if (data[j] > data[j+1]) {
                int tmp = data[j];
                data[j] = data[j+1];
                data[j+1] = tmp;
            }
        }
    }

    return result;
}

int main() {
    volatile int input = 60;
    int out = complex_algorithm(input);
    
    // prevent optimization away
    volatile int sink = out;
    return 0;
}