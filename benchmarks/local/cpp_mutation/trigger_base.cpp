#include <iostream>

__attribute__((optnone))
int main() {
    int state = 0;
    int sum = 0;
    
    for (int i = 0; i < 200; ++i) {
        if (state == 0) {
            if (i % 3 == 0) {
                state = 1;
                sum += 1;
            } else {
                sum += 2;
            }
        } else if (state == 1) {
            if (i % 5 == 0) {
                state = 2;
                sum += 3;
            } else {
                sum += 4;
            }
        } else {
            if (i % 2 == 0) {
                state = 0; 
                sum += 5;
            } else {
                sum += 6;
            }
        }
    }
    
    std::cout << sum << "\n";
    return 0;
}
