#include <iostream>
#include <vector>
#include <algorithm>
#include <cstdlib>

void generateData(std::vector<int>& data, int size) {
    for (int i = 0; i < size; ++i) {
        if (i % 2 == 0) {
            data.push_back(std::rand() % 1000);
        } else {
            data.push_back(std::rand() % 500);
        }
    }
}

int main(int argc, char** argv) {
    int size = 100;
    if (argc > 1) {
        size = std::atoi(argv[1]);
    }
    std::vector<int> data;
    generateData(data, size);
    std::sort(data.begin(), data.end());
    
    return 0;
}