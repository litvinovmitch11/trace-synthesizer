#include <iostream>

// We add dummy control flow and volatile memory operations to simulate 
// RegAlloc spills/fills and Block Placement passes that mutate the CFG.
// This shifts the Basic Block IDs and changes the topology.
__attribute__((optnone))
int main() {
    int state = 0;
    int sum = 0;
    volatile int spill_slot_1 = 0;
    volatile int spill_slot_2 = 0;
    
    // DUMMY BRANCH to shift all BB IDs and change the entry topology
    if (sum < 0) {
        sum += 1000;
        std::cout << "never";
    }

    for (int i = 0; i < 200; ++i) {
        spill_slot_1 = state; // simulate spill
        
        // ANOTHER DUMMY BRANCH to split the loop body block!
        if (spill_slot_1 == -1) {
            sum -= 1;
        }

        if (spill_slot_1 == 0) {
            spill_slot_2 = i; // simulate spill
            if (spill_slot_2 % 3 == 0) {
                state = 1;
                sum += 1;
            } else {
                sum += 2;
            }
        } else if (spill_slot_1 == 1) {
            if (i % 5 == 0) {
                state = 2;
                sum += 3;
            } else {
                sum += 4;
            }
        } else {
            spill_slot_2 = i; // simulate spill
            if (spill_slot_2 % 2 == 0) {
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
