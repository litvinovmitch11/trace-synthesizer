#include <iostream>

int main(int argc, char* argv[]) {
    int x = 5;
    if (argc > 1) {
        std::string arg = argv[1];
        if (arg == "second") {
            x = 12;
        }
    }

    int result = x;
    if (x > 10) {
        result *= 2;
    } else {
        result /= 2;
    }

    for (int i = 0; i < 3; i++) {
        result += i;
    }

    std::cout << result;
    
    return 0;
}
