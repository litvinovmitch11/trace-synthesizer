#include <iostream>
#include <vector>
#include <random>
#include <stdexcept>

// Генератор случайных чисел
int get_random(int min, int max) {
    static std::random_device rd;
    static std::mt19937 gen(rd());
    std::uniform_int_distribution<> distrib(min, max);
    return distrib(gen);
}

void complex_logic(int depth) {
    if (depth <= 0) return;

    // Ветвление с разной вероятностью (PGO это увидит)
    int action = get_random(0, 100);

    if (action < 10) { 
        // Редкий путь (10%)
        throw std::runtime_error("Rare failure!");
    } 
    else if (action < 50) {
        // Средний путь (40%) - Switch Case
        int mode = get_random(0, 3);
        switch (mode) {
            case 0: std::cout << "Mode A\n"; break;
            case 1: std::cout << "Mode B\n"; complex_logic(depth - 1); break; // Рекурсия
            case 2: std::cout << "Mode C\n"; break;
            default: break;
        }
    } 
    else {
        // Частый путь (50%) - Цикл
        int loops = get_random(1, 5);
        for (int i = 0; i < loops; ++i) {
            // Внутренний горячий код
            volatile int dummy = 0;
            dummy += i * i;
        }
    }
}

int main(int argc, char* argv[]) {
    std::cout << "Starting simulation...\n";
    
    int successes = 0;
    int failures = 0;

    // Главный цикл событий
    for (int i = 0; i < 50; ++i) {
        try {
            complex_logic(get_random(1, 3));
            successes++;
        } catch (const std::exception& e) {
            failures++; // Catch блок создаст landing pad в CFG
        }
    }

    std::cout << "Success: " << successes << ", Failures: " << failures << "\n";
    return 0;
}
