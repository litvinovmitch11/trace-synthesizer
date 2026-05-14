__attribute__((optnone))
void sort_array(int* arr, int n) {
    for (int i = 0; i < n - 1; ++i) {
        for (int j = 0; j < n - i - 1; ++j) {
            if (arr[j] > arr[j + 1]) {
                int temp = arr[j];
                arr[j] = arr[j + 1];
                arr[j + 1] = temp;
            }
        }
    }
}

__attribute__((optnone))
int main() {
    int arr[50];
    for (int i = 0; i < 50; ++i) {
        arr[i] = 50 - i;
    }
    sort_array(arr, 50);
    
    int sum = 0;
    for (int i = 0; i < 50; ++i) {
        sum += arr[i];
    }
    return 0;
}
