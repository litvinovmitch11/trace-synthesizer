__attribute__((optnone))
int process(int limit) {
    int sum = 0;
    int state = 0;
    volatile int dummy = 0;
    
    // Compiler Mutation 1: Loop peeling (Unroll first iteration)
    if (limit > 0) {
        // state = 0 logic
        sum += 1;
        state = 1;
        dummy = 1;
    } else {
        return sum;
    }

    // Compiler Mutation 2: Loop boundary changed
    for (int i = 1; i < limit; ++i) {
        // Compiler Mutation 3: Branch inversion (state != 0 instead of state == 0)
        // This swaps the True/False edge indices in LLVM IR
        if (state != 0) {
            // state == 1 logic
            sum += 2;
            state = 0;
            
            // Compiler Mutation 4: Block Splitting inside the hot path
            // The 2 volatile stores are now in a separate block!
            volatile int condition = dummy;
            if (condition > -100) { // always true
                dummy = 2;
                dummy = 3;
            }
        } else {
            // state == 0 logic
            sum += 1;
            state = 1;
            dummy = 1;
        }
    }
    return sum;
}

__attribute__((optnone))
int main() {
    int res = process(200);
    return 0;
}
