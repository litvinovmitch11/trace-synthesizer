#include <iostream>
#include <vector>
#include <algorithm>
#include <random>
#include <string>
#include <cmath>

int processNumber(int x) {
    if (x <= 0) {
        return -1;
    }
    
    int result = 0;
    for (int i = 1; i <= x; i++) {
        if (i % 2 == 0) {
            result += i * 2;
            if (i % 4 == 0) {
                result -= 1;
            }
        } else {
            result += i;
            if (i % 3 == 0) {
                result *= 2;
            }
        }
        
        if (result > 1000) {
            result %= 1000;
            break;
        }
    }
    
    return result;
}

char classifyValue(int val) {
    char category;
    
    switch (val % 5) {
        case 0:
            category = 'A';
            if (val > 50) category = 'a';
            break;
        case 1:
            category = 'B';
            for (int i = 0; i < 3; i++) {
                if ((val + i) % 2 == 0) {
                    category += 32; // lowercase
                    break;
                }
            }
            break;
        case 2:
            category = 'C';
            do {
                val /= 2;
            } while (val > 10);
            if (val < 5) category = 'c';
            break;
        case 3:
            category = 'D';
            while (val > 0) {
                if (val % 10 == 0) {
                    category = 'd';
                    break;
                }
                val /= 10;
            }
            break;
        default:
            category = 'E';
            if (val < 0) category = 'e';
    }
    
    return category;
}

int fibonacci(int n) {
    if (n <= 0) return 0;
    if (n == 1) return 1;
    return fibonacci(n - 1) + fibonacci(n - 2);
}

std::string processString(const std::string& str) {
    if (str.empty()) return "empty";
    
    std::string result;
    
    for (size_t i = 0; i < str.length(); i++) {
        char c = str[i];
        
        if (std::isdigit(c)) {
            int num = c - '0';
            if (num % 2 == 0) {
                result += "EVEN";
            } else {
                result += "ODD";
            }
        } else if (std::isalpha(c)) {
            if (std::isupper(c)) {
                result += std::tolower(c);
            } else {
                result += std::toupper(c);
                if (c == 'a' || c == 'e' || c == 'i' || c == 'o' || c == 'u') {
                    result += "_VOWEL";
                }
            }
        } else {
            result += "_SYMBOL";
        }
        
        if (result.length() > 50) {
            result = result.substr(0, 50) + "...";
            break;
        }
    }
    
    return result;
}

int main(int argc, char* argv[]) {
    std::vector<int> numbers;
    std::mt19937 rng(std::random_device{}());
    std::uniform_int_distribution<int> dist(1, 100);
    
    for (int i = 0; i < 20; i++) {
        numbers.push_back(dist(rng));
    }

    if (argc > 1) {
        std::string arg = argv[1];
        
        if (arg == "process") {
            std::vector<int> processed;
            for (int num : numbers) {
                int res = processNumber(num);
                processed.push_back(res);                
                if (res > 0) {
                    char cls = classifyValue(res);
                    std::cout << "Number: " << num 
                              << " -> " << res 
                              << " [" << cls << "]" << std::endl;
                } else {
                    std::cout << "Number: " << num 
                              << " -> invalid" << std::endl;
                }
            }
            
            int sum = 0;
            int positive_count = 0;
            
            for (int val : processed) {
                if (val > 0) {
                    sum += val;
                    positive_count++;
                }
            }
            
            if (positive_count > 0) {
                std::cout << "Average: " << (sum / positive_count) << std::endl;
            } else {
                std::cout << "No positive results" << std::endl;
            }
            
        } else if (arg == "fibonacci") {
            std::cout << "Fibonacci sequence:" << std::endl;
            for (int i = 0; i < 10; i++) {
                int fib = fibonacci(i);
                std::cout << "F(" << i << ") = " << fib << std::endl;
                if (fib % 2 == 0) {
                    std::cout << "  (even)" << std::endl;
                } else {
                    std::cout << "  (odd)" << std::endl;
                }
            }
            
        } else if (arg == "string") {
            std::string input = (argc > 2) ? argv[2] : "Test123!String";
            std::string output = processString(input);
            std::cout << "Input: " << input << std::endl;
            std::cout << "Output: " << output << std::endl;
        } else {
            std::sort(numbers.begin(), numbers.end());
            
            int search_value = std::stoi(arg);
            bool found = std::binary_search(numbers.begin(), numbers.end(), search_value);
            
            if (found) {
                std::cout << "Value " << search_value << " found in array" << std::endl;
                
                auto range = std::equal_range(numbers.begin(), numbers.end(), search_value);
                int count = std::distance(range.first, range.second);
                std::cout << "Count: " << count << std::endl;
            } else {
                std::cout << "Value " << search_value << " not found" << std::endl;
                
                auto lower = std::lower_bound(numbers.begin(), numbers.end(), search_value);
                if (lower != numbers.end()) {
                    std::cout << "Closest value: " << *lower << std::endl;
                }
            }
            
            std::cout << "Sorted array: ";
            for (int num : numbers) {
                std::cout << num << " ";
            }
            std::cout << std::endl;
        }
        
    } else {
        std::cout << "No arguments provided. Performing basic calculations:" << std::endl;
        
        int total = 0;
        for (int i = 0; i < 100; i++) {
            if (i % 3 == 0) {
                total += i * 2;
            } else if (i % 3 == 1) {
                total += i;
            } else {
                total -= i / 2;
            }
            
            if (total > 1000 && i > 50 && i % 7 == 0) {
                total = total % 1000;
                break;
            }
        }
        
        std::cout << "Total: " << total << std::endl;
        
        for (int i = 0; i < 5; i++) {
            for (int j = 0; j < 5; j++) {
                if (i == j) {
                    std::cout << "X ";
                } else if (i > j) {
                    std::cout << "> ";
                } else {
                    std::cout << "< ";
                }
            }
            std::cout << std::endl;
        }
    }
    
    if (numbers.size() > 10) {
        std::cout << "Large dataset processed (" << numbers.size() << " elements)" << std::endl;
    } else if (numbers.size() > 0) {
        std::cout << "Small dataset processed" << std::endl;
    } else {
        std::cout << "No data processed" << std::endl;
    }
    
    return 0;
}
