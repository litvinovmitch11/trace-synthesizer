__attribute__((optnone))
int process(int limit) {
    int sum = 0;
    int state = 0;
    volatile int dummy = 0;

    for (int i = 0; i < limit; ++i) {
        if (state == 0) {
            sum += 1;
            state = 1;
            dummy = 1; // 1 volatile store -> distinguishable
        } else {
            sum += 2;
            state = 0;
            dummy = 2;
            dummy = 3; // 2 volatile stores -> distinguishable
        }
    }
    return sum;
}

__attribute__((optnone))
int main() {
    int res = process(200);
    return 0;
}
